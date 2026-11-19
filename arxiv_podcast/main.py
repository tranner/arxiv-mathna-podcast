"""Orchestrates the full daily pipeline: fetch -> select -> script -> synth -> publish.

Usage:
    python -m arxiv_podcast.main [--date YYYY-MM-DD] [--force]

Idempotent per day: if today's episode already exists, the run is skipped
unless --force is passed. Exits non-zero on any hard failure so CI surfaces
it clearly.
"""

import argparse
import logging
import sys
from datetime import date as date_cls

from arxiv_podcast import config, publish
from arxiv_podcast.email_report import send_scores_email
from arxiv_podcast.fetch import fetch_recent_papers
from arxiv_podcast.fulltext import fetch_full_texts
from arxiv_podcast.models import Episode
from arxiv_podcast.score import load_interests, score_papers
from arxiv_podcast.script import ScriptGenerationError, generate_dialogue, total_cost_usd
from arxiv_podcast.select import select_papers
from arxiv_podcast.synth import SynthesisError, synthesize_episode

log = logging.getLogger(__name__)


def run(target_date: str, force: bool = False) -> int:
    config.ensure_dirs()

    final_mp3 = config.EPISODES_DIR / f"{target_date}.mp3"
    if final_mp3.exists() and not force:
        log.info("Episode for %s already exists at %s - skipping (use --force to redo).", target_date, final_mp3)
        return 0

    log.info("=== Building episode for %s ===", target_date)

    log.info("[1/5] Fetching papers from arXiv (%s)...", config.ARXIV_CATEGORY)
    papers = fetch_recent_papers()
    if not papers:
        log.error("No papers fetched - aborting.")
        return 1

    covered = publish.most_recent_episode_arxiv_ids()
    if covered and all(p.arxiv_id in covered for p in papers):
        log.info(
            "All %d fetched papers were already covered by the most recent "
            "episode - arXiv's feed hasn't rebuilt since then (e.g. a "
            "weekend/holiday run). Skipping.",
            len(papers),
        )
        return 0

    log.info("[2/5] Scoring papers against research interests and selecting...")
    interests = load_interests()
    scores = score_papers(papers, interests) if interests else None
    deep_dive, roundup, wildcard = select_papers(papers, scores)
    # Best-effort (never raises); sent now so it arrives even if a later stage fails.
    send_scores_email(papers, scores, deep_dive, roundup, wildcard, target_date)

    full_texts = None
    if config.DEEP_DIVE_FULL_TEXT:
        log.info("Fetching full text for %d deep-dive paper(s)...", len(deep_dive))
        full_texts = fetch_full_texts(deep_dive)

    log.info("[3/5] Generating dialogue script...")
    try:
        lines = generate_dialogue(
            deep_dive, roundup, target_date, wildcard=wildcard, full_texts=full_texts
        )
    except ScriptGenerationError as e:
        log.error("Script generation failed: %s", e)
        return 1
    log.info("Model cost for this episode: $%.4f", total_cost_usd())

    episode = Episode(date=target_date, deep_dive=deep_dive, roundup=roundup, lines=lines)

    log.info("[4/5] Synthesizing audio with Piper...")
    tmp_mp3 = config.EPISODES_DIR / f"{target_date}.synth-tmp.mp3"
    try:
        duration = synthesize_episode(lines, tmp_mp3)
    except SynthesisError as e:
        log.error("Audio synthesis failed: %s", e)
        return 1
    episode.duration_seconds = duration

    log.info("[5/5] Publishing episode + rebuilding feed...")
    final_path = publish.publish_episode(episode, tmp_mp3)

    log.info(
        "=== Done: %s (%.1f minutes) -> %s ===",
        target_date,
        duration / 60,
        final_path,
    )
    log.info("Feed: %s", config.FEED_PATH)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate today's arXiv podcast episode.")
    parser.add_argument(
        "--date",
        default=date_cls.today().isoformat(),
        help="Episode date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if an episode for this date already exists.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args.date, force=args.force)
    except Exception:
        log.exception("Unhandled error in pipeline run")
        return 1


if __name__ == "__main__":
    sys.exit(main())
