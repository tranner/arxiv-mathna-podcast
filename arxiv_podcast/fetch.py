"""Fetch today's papers from arXiv's daily category RSS feed."""

import logging
import re
import time
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import requests

from arxiv_podcast import config
from arxiv_podcast.models import Paper

log = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")

# The feed's <description> is prefixed with boilerplate like
# "arXiv:2608.10217v1 Announce Type: new\nAbstract: " ahead of the actual
# abstract text.
_ABSTRACT_PREFIX_RE = re.compile(r"^arXiv:\S+\s+Announce Type:\s*\S+\s*\n*Abstract:\s*", re.S)

# "new" and "cross" are papers newly appearing in this category today;
# "replace"/"replace-cross" are revisions of papers an earlier episode
# would already have covered.
_INCLUDED_ANNOUNCE_TYPES = {"new", "cross"}

# Status codes worth retrying: 429 (rate limited) and 5xx (transient server-
# side trouble). Other 4xx codes mean our request is wrong and won't succeed
# on retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def _get_with_retries(
    url: str,
    headers: dict,
    max_retries: int,
    backoff_seconds: float,
) -> requests.Response:
    """GET with exponential backoff on rate limiting / transient errors."""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as exc:
            if attempt == max_retries:
                raise
            log.warning(
                "arXiv request failed (%s), retry %d/%d", exc, attempt + 1, max_retries
            )
        else:
            if resp.status_code not in _RETRYABLE_STATUS_CODES:
                resp.raise_for_status()
                return resp
            if attempt == max_retries:
                resp.raise_for_status()
            log.warning(
                "arXiv returned %d, retry %d/%d",
                resp.status_code,
                attempt + 1,
                max_retries,
            )

        delay = backoff_seconds * (2**attempt)
        time.sleep(delay)

    raise AssertionError("unreachable")  # loop always returns or raises


def _entry_to_paper(entry) -> Paper:
    authors = [_clean(a) for a in entry.get("author", "").split(",")]
    authors = [a for a in authors if a]
    # guid looks like "oai:arXiv.org:2608.10217v1".
    arxiv_id = entry.id.rsplit(":", 1)[-1]
    abstract = _ABSTRACT_PREFIX_RE.sub("", entry.summary, count=1)
    published_dt = datetime.fromtimestamp(timegm(entry.published_parsed), tz=timezone.utc)
    return Paper(
        arxiv_id=arxiv_id,
        title=_clean(entry.title),
        authors=authors,
        abstract=_clean(abstract),
        link=entry.link,
        published=published_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def fetch_recent_papers(
    category: str = config.ARXIV_CATEGORY,
    max_results: int = config.ARXIV_MAX_RESULTS,
) -> list[Paper]:
    """Fetch today's newly-announced papers in `category`, feed order.

    The feed already covers exactly one announcement batch (skipping
    weekends), so there's no date-window filtering to do - only trimming to
    `max_results` on an unusually large day.
    """
    url = config.ARXIV_RSS_URL_TEMPLATE.format(category=category)
    headers = {"User-Agent": config.ARXIV_USER_AGENT}

    log.info("Fetching arXiv RSS feed for cat:%s", category)
    resp = _get_with_retries(
        url, headers, config.ARXIV_MAX_RETRIES, config.ARXIV_RETRY_BACKOFF_SECONDS
    )

    feed = feedparser.parse(resp.content)
    if feed.bozo:
        log.warning("feedparser reported a parse issue: %s", feed.bozo_exception)

    papers = [
        _entry_to_paper(entry)
        for entry in feed.entries
        if entry.get("arxiv_announce_type") in _INCLUDED_ANNOUNCE_TYPES
    ]
    log.info("Fetched %d new/cross papers from arXiv RSS (category=%s)", len(papers), category)

    return papers[:max_results]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    papers = fetch_recent_papers()
    print(f"\n{len(papers)} papers:\n")
    for p in papers:
        print(f"- [{p.arxiv_id}] {p.title}")
        print(f"    {p.authors_str()}")
