"""Score each fetched paper for relevance to the operator's research
interests (interests.md) and for standalone quality, in one model call.

select.py uses relevance to pick on-interest deep dives and order the
roundup, and quality to pick the daily off-topic "wildcard" deep dive.
Scoring is best-effort: on any failure this returns None and selection falls
back to random, so a scoring hiccup never costs an episode.
"""

import json
import logging
import re
from dataclasses import dataclass

from arxiv_podcast import config
from arxiv_podcast.models import Paper
from arxiv_podcast.script import ScriptGenerationError, _call_model, _extract_json_object

log = logging.getLogger(__name__)

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


@dataclass
class PaperScore:
    relevance: int  # 0-10, against interests.md
    quality: int  # 0-10, independent of interests
    reason: str


def load_interests() -> "str | None":
    """Return the interests text, or None if the file is missing or has no
    real content (blank, or only comments/headings left from the template)."""
    path = config.INTERESTS_PATH
    if not path.exists():
        log.warning("Interests file %s not found.", path)
        return None
    text = path.read_text(encoding="utf-8")
    meaningful = [
        line
        for line in _HTML_COMMENT_RE.sub("", text).splitlines()
        if line.strip() and not line.lstrip().startswith("#") and line.strip() not in ("-", "*")
    ]
    if not meaningful:
        log.warning("Interests file %s has no content yet.", path)
        return None
    return text.strip()


def build_scoring_prompt(papers: list[Paper], interests: str, with_reasons: bool = False) -> str:
    blocks = "\n---\n".join(
        f"arXiv ID: {p.arxiv_id}\nTitle: {p.title}\nAuthors: {p.authors_str(max_authors=6)}\n"
        f"Abstract: {p.abstract}\n"
        for p in papers
    )
    # Reasons are only for tuning interests.md by hand; leaving them out of
    # the daily run cuts output tokens (the pricier side) by about 40%.
    reason_instruction = (
        '\nAlso give a short "reason" (at most 15 words) covering both scores.\n'
        if with_reasons
        else ""
    )
    reason_field = ', "reason": "..."' if with_reasons else ""
    return f"""You are helping curate a daily podcast about new arXiv
{config.ARXIV_CATEGORY} papers for a listener with specific research interests.

LISTENER'S RESEARCH INTERESTS:
<interests>
{interests}
</interests>

Score EVERY one of the {len(papers)} papers below on two independent 0-10 scales:

- "relevance": how closely the paper matches the listener's interests above.
  10 = squarely on a core interest; 6 = clearly related (shared methods or
  applications); 3 = loosely adjacent; 0 = unrelated. Respect anything the
  interests say to de-prioritise.
- "quality": how strong and significant the paper looks, judged ONLY from
  the abstract and IGNORING the listener's interests entirely: novelty and
  significance of the contribution, strength and clarity of the claimed
  results (theory and/or experiments), and likely interest to the wider
  numerical analysis community. Be discriminating - these scores are used
  to pick the single best paper of the day, so ties are unhelpful. Rank the
  papers against each other: give 8 or more to at most three papers (the
  day's genuine standouts), 7 to at most five more, and spread the rest
  across 2-6 (routine incremental work is 4-5).
{reason_instruction}
PAPERS:

{blocks}

OUTPUT FORMAT: return ONLY a single JSON object, no markdown fences, no other
text, with exactly one entry per paper, using the arXiv IDs exactly as given:

{{"scores": [{{"arxiv_id": "...", "relevance": 0, "quality": 0{reason_field}}}, ...]}}
"""


def _clamp(value) -> int:
    return max(0, min(10, int(round(float(value)))))


_VERSION_RE = re.compile(r"v\d+$")


def _base_id(arxiv_id: str) -> str:
    """'arXiv:2611.23321v1' -> '2611.23321' (for matching only)."""
    arxiv_id = arxiv_id.strip()
    if arxiv_id.lower().startswith("arxiv:"):
        arxiv_id = arxiv_id[6:]
    return _VERSION_RE.sub("", arxiv_id.strip())


def _parse_scores(raw_text: str, papers: list[Paper]) -> dict[str, PaperScore]:
    data = json.loads(_extract_json_object(raw_text))
    if not isinstance(data, dict) or not isinstance(data.get("scores"), list):
        raise ScriptGenerationError("JSON missing top-level 'scores' array")

    known_ids = {p.arxiv_id for p in papers}
    # Match loosely: the model sometimes drops the version ("2611.23321"
    # for "2611.23321v1") or adds an "arXiv:" prefix.
    by_base = {_base_id(i): i for i in known_ids}
    scores: dict[str, PaperScore] = {}
    for item in data["scores"]:
        if not isinstance(item, dict):
            continue
        arxiv_id = by_base.get(_base_id(str(item.get("arxiv_id", ""))))
        if arxiv_id is None:
            continue
        scores[arxiv_id] = PaperScore(
            relevance=_clamp(item.get("relevance", 0)),
            quality=_clamp(item.get("quality", 0)),
            reason=str(item.get("reason", "")).strip(),
        )

    if not scores:
        sample = [str(item.get("arxiv_id")) for item in data["scores"][:3] if isinstance(item, dict)]
        raise ScriptGenerationError(
            f"no scores matched any fetched arXiv ID ({len(data['scores'])} entries; "
            f"first IDs returned: {sample}; expected e.g. {sorted(known_ids)[:2]})"
        )

    missing = known_ids - scores.keys()
    if missing:
        log.warning("Scoring omitted %d paper(s); treating them as 0/0: %s", len(missing), sorted(missing))
        for arxiv_id in missing:
            scores[arxiv_id] = PaperScore(relevance=0, quality=0, reason="(not scored)")
    return scores


def score_papers(
    papers: list[Paper], interests: str, max_attempts: int = 2, with_reasons: bool = False
) -> "dict[str, PaperScore] | None":
    """Return {arxiv_id: PaperScore} for every paper, or None on failure."""
    if not papers:
        return None
    prompt = build_scoring_prompt(papers, interests, with_reasons=with_reasons)
    state = None
    for attempt in range(1, max_attempts + 1):
        try:
            if attempt == 1:
                raw_text, state = _call_model(
                    prompt, label="scoring", effort=config.SCORING_EFFORT
                )
            else:
                raw_text, state = _call_model(
                    "Your previous response could not be parsed as the required "
                    "JSON. Reply again with ONLY the corrected JSON object - no "
                    "markdown fences, no other text.",
                    state=state,
                    label="scoring retry",
                )
            scores = _parse_scores(raw_text, papers)
        except (json.JSONDecodeError, ValueError, TypeError, ScriptGenerationError) as e:
            log.warning("Scoring attempt %d/%d failed: %s", attempt, max_attempts, e)
            if state is not None:
                log.warning("Raw scoring output (first 500 chars): %r", raw_text[:500])
            if state is None:
                break  # the model call itself failed; nothing to continue from
            continue
        log.info("Scored %d papers for relevance/quality", len(scores))
        return scores

    log.warning("Paper scoring failed - selection will fall back to random.")
    return None


if __name__ == "__main__":
    from arxiv_podcast.fetch import fetch_recent_papers

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    interests = load_interests()
    if not interests:
        raise SystemExit(f"Fill in {config.INTERESTS_PATH} first.")
    papers = fetch_recent_papers()
    scores = score_papers(papers, interests, with_reasons=True)
    if not scores:
        raise SystemExit("Scoring failed.")

    by_id = {p.arxiv_id: p for p in papers}
    print(f"\n{'rel':>3} {'qual':>4}  title / reason   (threshold: relevance >= {config.RELEVANCE_THRESHOLD})")
    for arxiv_id, s in sorted(scores.items(), key=lambda kv: (-kv[1].relevance, -kv[1].quality)):
        print(f"{s.relevance:>3} {s.quality:>4}  {by_id[arxiv_id].title[:90]}")
        print(f"{'':>10}{s.reason}")
