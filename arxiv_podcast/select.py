"""Choose which papers get a deep dive vs. a roundup mention.

With relevance/quality scores (score.py): the deep dives are the papers most
relevant to the operator's interests plus one "wildcard" - the highest-
quality paper *outside* those interests - and the roundup is the next most
relevant papers. Without scores (no interests file, or scoring failed), it
falls back to a random pick.
"""

import logging
import random

from arxiv_podcast import config
from arxiv_podcast.models import Paper
from arxiv_podcast.score import PaperScore

log = logging.getLogger(__name__)


def _random_split(
    papers: list[Paper], n_deep: int, roundup_max: int
) -> tuple[list[Paper], list[Paper], None]:
    deep_dive = random.sample(papers, n_deep)
    deep_ids = {p.arxiv_id for p in deep_dive}
    # Preserve original (newest-first) ordering for the roundup.
    remaining = [p for p in papers if p.arxiv_id not in deep_ids]
    return deep_dive, remaining[:roundup_max], None


def select_papers(
    papers: list[Paper],
    scores: "dict[str, PaperScore] | None" = None,
    deep_dive_min: int = config.DEEP_DIVE_MIN,
    deep_dive_max: int = config.DEEP_DIVE_MAX,
    roundup_max: int = config.ROUNDUP_MAX,
    relevance_threshold: int = config.RELEVANCE_THRESHOLD,
) -> tuple[list[Paper], list[Paper], "Paper | None"]:
    """Split `papers` into (deep_dive, roundup, wildcard).

    `wildcard` is also the last element of `deep_dive` (or None when there's
    no off-topic pick, e.g. in the random fallback or with a single paper).
    The deep-dive count is genuinely random (`random.randint`).
    """
    if not papers:
        raise ValueError("select_papers() called with an empty paper list")

    n_deep = min(random.randint(deep_dive_min, deep_dive_max), len(papers))

    if not scores:
        log.warning("No relevance scores - falling back to random selection.")
        deep_dive, roundup, wildcard = _random_split(papers, n_deep, roundup_max)
    else:
        def score(p: Paper) -> PaperScore:
            return scores.get(p.arxiv_id) or PaperScore(0, 0, "")

        ranked = sorted(papers, key=lambda p: (score(p).relevance, score(p).quality), reverse=True)

        wildcard = None
        if n_deep >= 2:
            off_topic = [p for p in ranked if score(p).relevance < relevance_threshold]
            # If everything is on-interest, take the best-quality paper that
            # wouldn't already make the on-interest cut. Quality ties go to
            # the more relevant paper, so the de-prioritised areas only win
            # the wildcard on genuinely better quality.
            pool = off_topic or ranked[n_deep - 1 :]
            wildcard = max(pool, key=lambda p: (score(p).quality, score(p).relevance))

        others = [p for p in ranked if wildcard is None or p.arxiv_id != wildcard.arxiv_id]
        n_on_interest = n_deep - (1 if wildcard else 0)
        deep_dive = others[:n_on_interest] + ([wildcard] if wildcard else [])
        roundup = others[n_on_interest : n_on_interest + roundup_max]

        for p in deep_dive:
            s = score(p)
            log.info(
                "Deep dive%s: rel=%d qual=%d  %s",
                " (WILDCARD)" if p is wildcard else "",
                s.relevance,
                s.quality,
                p.title,
            )

    log.info(
        "Selected %d paper(s) for deep dive, %d for roundup (of %d fetched, "
        "%d left out)",
        len(deep_dive),
        len(roundup),
        len(papers),
        len(papers) - len(deep_dive) - len(roundup),
    )
    return deep_dive, roundup, wildcard


if __name__ == "__main__":
    from arxiv_podcast.fetch import fetch_recent_papers
    from arxiv_podcast.score import load_interests, score_papers

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    papers = fetch_recent_papers()
    interests = load_interests()
    scores = score_papers(papers, interests) if interests else None
    deep, round_, wildcard = select_papers(papers, scores)

    def fmt(p: Paper) -> str:
        s = scores.get(p.arxiv_id) if scores else None
        prefix = f"[rel {s.relevance:>2} qual {s.quality:>2}] " if s else ""
        return f"  - {prefix}{p.title}"

    print(f"\nDeep dive ({len(deep)}):")
    for p in deep:
        print(fmt(p) + ("   <- WILDCARD" if p is wildcard else ""))
    print(f"\nRoundup ({len(round_)}):")
    for p in round_:
        print(fmt(p))
