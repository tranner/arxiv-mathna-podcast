"""Fetch recent papers from the arXiv API for a given category."""

import logging
import re
import time
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from arxiv_podcast import config
from arxiv_podcast.models import Paper

log = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")

# Status codes worth retrying: 429 (rate limited) and 5xx (transient server-
# side trouble). Other 4xx codes mean our request is wrong and won't succeed
# on retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def _get_with_retries(
    url: str,
    params: dict,
    headers: dict,
    max_retries: int,
    backoff_seconds: float,
) -> requests.Response:
    """GET with exponential backoff on rate limiting / transient errors.

    arXiv's export API throttles by source network rather than strictly by
    caller, so a 429 here can be caused by unrelated traffic sharing our
    egress IP (e.g. GitHub Actions' runner pool) - retrying after a pause
    is usually enough to get through.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
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
    authors = [_clean(a.get("name", "")) for a in getattr(entry, "authors", [])]
    authors = [a for a in authors if a]
    arxiv_id = entry.id.rsplit("/", 1)[-1]
    return Paper(
        arxiv_id=arxiv_id,
        title=_clean(entry.title),
        authors=authors,
        abstract=_clean(entry.summary),
        link=entry.link,
        published=entry.published,
    )


def fetch_recent_papers(
    category: str = config.ARXIV_CATEGORY,
    max_results: int = config.ARXIV_MAX_RESULTS,
    lookback_hours: int = config.ARXIV_LOOKBACK_HOURS,
) -> list[Paper]:
    """Fetch recent papers in `category`, newest first.

    Returns only papers published within `lookback_hours`. If that window is
    empty (e.g. a weekend with no new arXiv announcements), falls back to the
    most recent `max_results` papers regardless of age, so the pipeline always
    has something to talk about.
    """
    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    headers = {"User-Agent": config.ARXIV_USER_AGENT}

    log.info("Querying arXiv API for cat:%s (max_results=%d)", category, max_results)
    resp = _get_with_retries(
        config.ARXIV_API_URL,
        params,
        headers,
        config.ARXIV_MAX_RETRIES,
        config.ARXIV_RETRY_BACKOFF_SECONDS,
    )
    # Be a polite API citizen - arXiv asks for no more than one request every
    # few seconds; we only make one request per run so this is just a courtesy
    # pause in case this function is ever called in a loop.
    time.sleep(1)

    feed = feedparser.parse(resp.content)
    if feed.bozo:
        log.warning("feedparser reported a parse issue: %s", feed.bozo_exception)

    all_papers = [_entry_to_paper(e) for e in feed.entries]
    log.info("Fetched %d papers total from arXiv", len(all_papers))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    recent = []
    for entry, paper in zip(feed.entries, all_papers):
        published_struct = getattr(entry, "published_parsed", None)
        if published_struct is None:
            continue
        published_dt = datetime.fromtimestamp(timegm(published_struct), tz=timezone.utc)
        if published_dt >= cutoff:
            recent.append(paper)

    if recent:
        log.info(
            "%d papers published in the last %d hours", len(recent), lookback_hours
        )
        return recent

    log.warning(
        "No papers published in the last %d hours - falling back to the %d most "
        "recent papers regardless of age",
        lookback_hours,
        max_results,
    )
    return all_papers


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    papers = fetch_recent_papers()
    print(f"\n{len(papers)} papers:\n")
    for p in papers:
        print(f"- [{p.arxiv_id}] {p.title}")
        print(f"    {p.authors_str()}")
