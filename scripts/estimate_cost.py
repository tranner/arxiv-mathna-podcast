"""Estimate the API cost of interest-based scoring and full-text deep dives,
against today's real arXiv listing.

    ANTHROPIC_API_KEY=... uv run python scripts/estimate_cost.py [--live]

Default (no --live): only token *counting* (messages.count_tokens - free) on
the actual prompts the pipeline would send, plus estimated output sizes. The
deep-dive split is random since there are no real scores without a call.

--live: also makes the real (billed) scoring call and one full-text script
generation through the configured SCRIPT_BACKEND, and prints the logged
usage so you can compare it with the estimate.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from arxiv_podcast import config  # noqa: E402
from arxiv_podcast.fetch import fetch_recent_papers  # noqa: E402
from arxiv_podcast.fulltext import fetch_full_texts  # noqa: E402
from arxiv_podcast.score import build_scoring_prompt, load_interests, score_papers  # noqa: E402
from arxiv_podcast.script import USAGE_LOG, build_prompt, generate_dialogue  # noqa: E402
from arxiv_podcast.select import select_papers  # noqa: E402

WEEKDAY_EPISODES_PER_MONTH = 21

# Output-size estimates. Scoring: one short JSON row per paper. Script: ~1.3
# tokens per English word, plus JSON wrapping per dialogue line (~30 words
# per line, ~15 tokens of {"speaker": ..., "text": ...} overhead).
SCORING_OUTPUT_TOKENS_PER_PAPER = 35  # no reasons in the daily run
SCRIPT_OUTPUT_TOKENS = int(
    config.TARGET_WORD_COUNT * 1.3 + (config.TARGET_WORD_COUNT / 30) * 15
)

PLACEHOLDER_INTERESTS = (
    "Finite element methods for PDEs on surfaces and evolving domains; a "
    "posteriori error estimation; numerical methods for slender-body mechanics."
)


def count_tokens(client: anthropic.Anthropic, prompt: str) -> int:
    return client.messages.count_tokens(
        model=config.ANTHROPIC_MODEL,
        messages=[{"role": "user", "content": prompt}],
    ).input_tokens


def dollars(input_tokens: int, output_tokens: int) -> float:
    cost = config.model_cost_usd(input_tokens, output_tokens)
    if cost is None:
        raise SystemExit(
            f"No price for {config.ANTHROPIC_MODEL} in config.MODEL_PRICES_PER_MTOK - add one."
        )
    return cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="Also make the real (billed) calls.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY (token counting uses the API, free of charge).")
    client = anthropic.Anthropic()

    papers = fetch_recent_papers()
    if not papers:
        raise SystemExit("No papers in today's feed.")

    interests = load_interests()
    if not interests:
        logging.warning("interests.md is empty - estimating with a placeholder interests text.")
        interests = PLACEHOLDER_INTERESTS

    scores = score_papers(papers, interests) if args.live else None
    deep, roundup, wildcard = select_papers(papers, scores)
    full_texts = fetch_full_texts(deep)

    date = "2026-01-01"
    scoring_in = count_tokens(client, build_scoring_prompt(papers, interests))
    scoring_out = SCORING_OUTPUT_TOKENS_PER_PAPER * len(papers)
    base_in = count_tokens(client, build_prompt(deep, roundup, date, wildcard=wildcard))
    full_in = count_tokens(
        client, build_prompt(deep, roundup, date, wildcard=wildcard, full_texts=full_texts)
    )

    # A retry (script too short / bad JSON) resends the whole conversation:
    # original prompt + the previous response, then generates a new response.
    def with_one_retry(prompt_in: int) -> tuple[int, int]:
        return 2 * prompt_in + SCRIPT_OUTPUT_TOKENS + 150, 2 * SCRIPT_OUTPUT_TOKENS

    rows = [
        ("Scoring (new)", scoring_in, scoring_out),
        ("Script, abstracts only (current)", base_in, SCRIPT_OUTPUT_TOKENS),
        ("Script, full-text deep dives", full_in, SCRIPT_OUTPUT_TOKENS),
        ("  ...abstracts only, with 1 retry", *with_one_retry(base_in)),
        ("  ...full text, with 1 retry", *with_one_retry(full_in)),
    ]

    print(f"\nModel: {config.ANTHROPIC_MODEL}   papers today: {len(papers)}   "
          f"deep dives: {len(deep)}   full texts fetched: {len(full_texts)}/{len(deep)}")
    for p in deep:
        n = len(full_texts.get(p.arxiv_id, ""))
        print(f"  - {p.title[:80]}  ({n:,} chars of full text)")
    print(f"\n{'':36} {'input tok':>10} {'output tok':>10} {'$/episode':>10}")
    for label, i, o in rows:
        print(f"{label:36} {i:>10,} {o:>10,} {dollars(i, o):>10.4f}")

    current = dollars(base_in, SCRIPT_OUTPUT_TOKENS)
    scoring = dollars(scoring_in, scoring_out)
    full_extra = dollars(full_in, SCRIPT_OUTPUT_TOKENS) - current
    print("\nExtra cost vs. today's pipeline (no retries):")
    for label, extra in [
        ("scoring only", scoring),
        ("full-text deep dives only", full_extra),
        ("both", scoring + full_extra),
    ]:
        print(f"  {label:28} ${extra:.4f}/episode   ${extra * WEEKDAY_EPISODES_PER_MONTH:.2f}/month")
    print(f"  (current script call alone: ${current:.4f}/episode, "
          f"${current * WEEKDAY_EPISODES_PER_MONTH:.2f}/month)")

    if args.live:
        print("\nRunning one real full-text script generation (billed)...")
        generate_dialogue(deep, roundup, date, wildcard=wildcard, full_texts=full_texts)
        print(f"\n{'Actual usage':36} {'input tok':>10} {'output tok':>10} {'$':>10}")
        for label, i, o, cost in USAGE_LOG:
            print(f"{label:36} {i:>10,} {o:>10,} {cost if cost is not None else float('nan'):>10.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
