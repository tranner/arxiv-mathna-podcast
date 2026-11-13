"""Fetch and extract the full text of a paper from its arXiv PDF.

Used (optionally - config.DEEP_DIVE_FULL_TEXT) to give the script model the
whole paper for the deep dives rather than just the abstract. Plain extracted
text rather than a PDF document block: it works with both script backends
(`claude -p` can't take one) and costs far fewer tokens, since PDF blocks
also bill every page as an image. Best-effort: any failure returns None and
that deep dive falls back to the abstract.
"""

import io
import logging
import re

from pypdf import PdfReader

from arxiv_podcast import config
from arxiv_podcast.fetch import _get_with_retries
from arxiv_podcast.models import Paper

log = logging.getLogger(__name__)
# pypdf warns about every font it can't fully decode (e.g. without fontTools);
# harmless for text extraction, and very noisy on LaTeX PDFs.
logging.getLogger("pypdf").setLevel(logging.ERROR)

PDF_URL_TEMPLATE = "https://arxiv.org/pdf/{arxiv_id}"
_BLANK_LINES_RE = re.compile(r"\n{3,}")
TRUNCATION_MARKER = "\n[... full text truncated for length ...]"


def fetch_full_text(paper: Paper, max_chars: int = config.FULL_TEXT_MAX_CHARS) -> "str | None":
    url = PDF_URL_TEMPLATE.format(arxiv_id=paper.arxiv_id)
    try:
        resp = _get_with_retries(
            url,
            {"User-Agent": config.ARXIV_USER_AGENT},
            config.ARXIV_MAX_RETRIES,
            config.ARXIV_RETRY_BACKOFF_SECONDS,
        )
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # network, HTTP, or PDF parsing - all non-fatal
        log.warning("Couldn't get full text for %s (%s) - using abstract only.", paper.arxiv_id, e)
        return None

    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    if not text:
        log.warning("No extractable text in PDF for %s - using abstract only.", paper.arxiv_id)
        return None

    log.info("Full text for %s: %d pages, %d chars", paper.arxiv_id, len(reader.pages), len(text))
    if len(text) > max_chars:
        log.warning(
            "Full text for %s truncated from %d to %d chars (FULL_TEXT_MAX_CHARS).",
            paper.arxiv_id,
            len(text),
            max_chars,
        )
        text = text[:max_chars] + TRUNCATION_MARKER
    return text


def fetch_full_texts(papers: list[Paper]) -> dict[str, str]:
    """{arxiv_id: text} for each paper whose full text could be fetched."""
    texts = {}
    for p in papers:
        text = fetch_full_text(p)
        if text:
            texts[p.arxiv_id] = text
    return texts
