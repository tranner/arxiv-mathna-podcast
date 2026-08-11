"""Randomly select which papers get a deep dive vs. a roundup mention."""

import logging
import random

from arxiv_podcast import config
from arxiv_podcast.models import Paper

log = logging.getLogger(__name__)


def select_papers(
    papers: list[Paper],
    deep_dive_min: int = config.DEEP_DIVE_MIN,
    deep_dive_max: int = config.DEEP_DIVE_MAX,
    roundup_max: int = config.ROUNDUP_MAX,
) -> tuple[list[Paper], list[Paper]]:
    """Split `papers` into (deep_dive, roundup) picks.

    The deep-dive count is genuinely random (`random.randint`), not left to
    the model. The remaining papers form the roundup, capped at
    `roundup_max` so the episode doesn't run long on heavy arXiv days.
    """
    if not papers:
        raise ValueError("select_papers() called with an empty paper list")

    n_deep = random.randint(deep_dive_min, deep_dive_max)
    n_deep = min(n_deep, len(papers))

    deep_dive = random.sample(papers, n_deep)
    deep_ids = {p.arxiv_id for p in deep_dive}

    # Preserve original (newest-first) ordering for the roundup rather than
    # the shuffled leftovers from random.sample's bookkeeping.
    remaining = [p for p in papers if p.arxiv_id not in deep_ids]
    roundup = remaining[:roundup_max]

    log.info(
        "Selected %d paper(s) for deep dive, %d for roundup (of %d fetched, "
        "%d capped from roundup)",
        len(deep_dive),
        len(roundup),
        len(papers),
        max(0, len(remaining) - len(roundup)),
    )
    return deep_dive, roundup


if __name__ == "__main__":
    from arxiv_podcast.fetch import fetch_recent_papers

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    papers = fetch_recent_papers()
    deep, round_ = select_papers(papers)

    print(f"\nDeep dive ({len(deep)}):")
    for p in deep:
        print(f"  - {p.title}")
    print(f"\nRoundup ({len(round_)}):")
    for p in round_:
        print(f"  - {p.title}")
