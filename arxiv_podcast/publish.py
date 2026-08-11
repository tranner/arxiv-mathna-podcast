"""Write the episode audio + metadata, prune old episodes, and regenerate the
podcast RSS feed and a simple human-facing landing page.

Episode metadata (papers covered, title, duration) is persisted as a JSON
sidecar next to each mp3 (docs/episodes/YYYY-MM-DD.json) so the feed can be
rebuilt from scratch on every run just by scanning docs/episodes/, without
needing any external database.
"""

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from feedgen.feed import FeedGenerator

from arxiv_podcast import config
from arxiv_podcast.models import Episode, Paper

log = logging.getLogger(__name__)


def _episode_mp3_path(date: str) -> Path:
    return config.EPISODES_DIR / f"{date}.mp3"


def _episode_meta_path(date: str) -> Path:
    return config.EPISODES_DIR / f"{date}.json"


def _paper_to_dict(p: Paper) -> dict:
    return {
        "arxiv_id": p.arxiv_id,
        "title": p.title,
        "authors": p.authors,
        "link": p.link,
    }


def write_episode_files(episode: Episode, source_mp3: Path) -> Path:
    """Move/copy the synthesized mp3 into its final dated location and write
    the metadata sidecar. Returns the final mp3 path."""
    config.ensure_dirs()
    final_mp3 = _episode_mp3_path(episode.date)

    if source_mp3.resolve() != final_mp3.resolve():
        shutil.move(str(source_mp3), str(final_mp3))

    meta = {
        "date": episode.date,
        "title": f"{config.PODCAST_TITLE} — {episode.date}",
        "duration_seconds": episode.duration_seconds,
        "deep_dive": [_paper_to_dict(p) for p in episode.deep_dive],
        "roundup": [_paper_to_dict(p) for p in episode.roundup],
    }
    _episode_meta_path(episode.date).write_text(json.dumps(meta, indent=2))
    log.info("Wrote episode files: %s (+ metadata sidecar)", final_mp3)
    return final_mp3


def prune_old_episodes(retention_days: int = config.EPISODE_RETENTION_DAYS) -> None:
    """Delete mp3/json pairs older than `retention_days`. Keeps the repo and
    GitHub Pages site from growing unboundedly; already-ingested episodes
    remain available in Spotify/podcast apps regardless."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
    removed = 0
    for meta_path in sorted(config.EPISODES_DIR.glob("*.json")):
        date_str = meta_path.stem
        try:
            episode_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue  # not a dated episode file (e.g. leftover smoke_test.*)
        if episode_date < cutoff:
            mp3_path = _episode_mp3_path(date_str)
            meta_path.unlink(missing_ok=True)
            mp3_path.unlink(missing_ok=True)
            removed += 1
    if removed:
        log.info("Pruned %d episode(s) older than %d days", removed, retention_days)


def _load_all_episode_meta() -> list[dict]:
    episodes = []
    for meta_path in sorted(config.EPISODES_DIR.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Skipping unreadable episode metadata %s: %s", meta_path, e)
            continue
        mp3_path = _episode_mp3_path(meta["date"])
        if not mp3_path.exists():
            log.warning("Skipping %s: mp3 missing at %s", meta_path, mp3_path)
            continue
        meta["_mp3_path"] = mp3_path
        episodes.append(meta)
    episodes.sort(key=lambda m: m["date"], reverse=True)
    return episodes


def _format_duration(seconds: "float | None") -> str:
    if not seconds:
        return "00:00:00"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _show_notes(meta: dict) -> str:
    lines = ["<p><strong>Deep dive:</strong></p><ul>"]
    for p in meta["deep_dive"]:
        lines.append(f'<li><a href="{p["link"]}">{p["title"]}</a> — {", ".join(p["authors"])}</li>')
    lines.append("</ul><p><strong>Also covered today:</strong></p><ul>")
    for p in meta["roundup"]:
        lines.append(f'<li><a href="{p["link"]}">{p["title"]}</a> — {", ".join(p["authors"])}</li>')
    lines.append("</ul>")
    return "\n".join(lines)


def build_feed() -> Path:
    """Regenerate docs/podcast.xml from every episode currently on disk."""
    episodes = _load_all_episode_meta()

    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title(config.PODCAST_TITLE)
    fg.link(href=config.SITE_BASE_URL, rel="alternate")
    fg.link(href=f"{config.SITE_BASE_URL}/podcast.xml", rel="self")
    fg.description(config.PODCAST_DESCRIPTION)
    fg.language(config.PODCAST_LANGUAGE)
    fg.generator("arxiv_podcast")
    fg.podcast.itunes_author(config.PODCAST_AUTHOR)
    fg.podcast.itunes_summary(config.PODCAST_DESCRIPTION)
    fg.podcast.itunes_category(cat="Science")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_image(config.PODCAST_IMAGE_URL)
    if config.PODCAST_EMAIL:
        fg.podcast.itunes_owner(name=config.PODCAST_AUTHOR, email=config.PODCAST_EMAIL)

    for meta in episodes:
        mp3_path: Path = meta["_mp3_path"]
        mp3_url = f"{config.SITE_BASE_URL}/episodes/{mp3_path.name}"
        pub_dt = datetime.strptime(meta["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

        fe = fg.add_entry()
        fe.id(mp3_url)
        fe.guid(mp3_url, permalink=True)
        fe.title(meta["title"])
        fe.description(_show_notes(meta))
        fe.enclosure(mp3_url, str(mp3_path.stat().st_size), "audio/mpeg")
        fe.pubDate(format_datetime(pub_dt))
        fe.podcast.itunes_duration(_format_duration(meta.get("duration_seconds")))
        fe.podcast.itunes_summary(_show_notes(meta))

    config.FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(config.FEED_PATH), pretty=True)
    log.info("Wrote RSS feed with %d episode(s) to %s", len(episodes), config.FEED_PATH)
    return config.FEED_PATH


def build_index_html() -> Path:
    """A minimal human-facing landing page listing recent episodes."""
    episodes = _load_all_episode_meta()
    rows = []
    for meta in episodes[:30]:
        mp3_name = meta["_mp3_path"].name
        rows.append(
            f'<li><strong>{meta["date"]}</strong> — '
            f'<a href="episodes/{mp3_name}">{meta["title"]}</a> '
            f'({_format_duration(meta.get("duration_seconds"))})</li>'
        )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{config.PODCAST_TITLE}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem;">
<h1>{config.PODCAST_TITLE}</h1>
<p>{config.PODCAST_DESCRIPTION}</p>
<p>Subscribe: <a href="podcast.xml">RSS feed</a></p>
<h2>Episodes</h2>
<ul>
{chr(10).join(rows) if rows else "<li>No episodes published yet.</li>"}
</ul>
</body>
</html>
"""
    index_path = config.DOCS_DIR / "index.html"
    index_path.write_text(html)
    return index_path


def publish_episode(episode: Episode, source_mp3: Path) -> Path:
    """Full publish step: place files, prune old episodes, rebuild feed + index."""
    write_episode_files(episode, source_mp3)
    prune_old_episodes()
    build_feed()
    build_index_html()
    return _episode_mp3_path(episode.date)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_feed()
    build_index_html()
    print(f"Feed: {config.FEED_PATH}")
    print(f"Index: {config.DOCS_DIR / 'index.html'}")
