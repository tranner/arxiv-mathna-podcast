"""Email the day's relevance/quality scores via Resend.

Sent right after scoring + selection, so the scores still arrive even if a
later stage (script, synth) fails. Best-effort: it's skipped when
RESEND_API_KEY / EMAIL_TO aren't set, and any send failure is only logged -
the email never costs an episode.

Preview or test it on its own:
    python -m arxiv_podcast.email_report --dry-run > preview.html
    python -m arxiv_podcast.email_report          # sends for real if configured
"""

import argparse
import html
import logging
import sys

import requests

from arxiv_podcast import config
from arxiv_podcast.models import Paper
from arxiv_podcast.score import PaperScore

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def _episode_url(target_date: str) -> str:
    return f"{config.SITE_BASE_URL}/episodes/{target_date}.mp3"


def _ordered_with_roles(
    papers: list[Paper],
    scores: "dict[str, PaperScore] | None",
    deep_dive: list[Paper],
    roundup: list[Paper],
    wildcard: "Paper | None",
) -> list[tuple[Paper, str]]:
    """Deep dives first (in selection order), then everything else ranked by
    (relevance, quality) like select.py - or in fetch order without scores."""
    deep_ids = {p.arxiv_id for p in deep_dive}
    roundup_ids = {p.arxiv_id for p in roundup}
    wildcard_id = wildcard.arxiv_id if wildcard else None

    def role(p: Paper) -> str:
        if p.arxiv_id == wildcard_id:
            return "Wildcard"
        if p.arxiv_id in deep_ids:
            return "Deep dive"
        if p.arxiv_id in roundup_ids:
            return "Roundup"
        return "Not covered"

    rest = [p for p in papers if p.arxiv_id not in deep_ids]
    if scores:
        def key(p: Paper):
            s = scores.get(p.arxiv_id)
            return (s.relevance, s.quality) if s else (-1, -1)

        rest.sort(key=key, reverse=True)
    return [(p, role(p)) for p in deep_dive + rest]


_ROLE_COLOURS = {
    "Deep dive": "#1a7f37",
    "Wildcard": "#8250df",
    "Roundup": "#0969da",
    "Not covered": "#6e7781",
}


def build_email(
    papers: list[Paper],
    scores: "dict[str, PaperScore] | None",
    deep_dive: list[Paper],
    roundup: list[Paper],
    wildcard: "Paper | None",
    target_date: str,
) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body)."""
    subject = f"arXiv {config.ARXIV_CATEGORY} scores - {target_date} ({len(papers)} papers)"
    rows = _ordered_with_roles(papers, scores, deep_dive, roundup, wildcard)
    ep_url = _episode_url(target_date)
    e = html.escape

    if scores:
        note = (
            f"Relevance is against interests.md (on-interest at &ge; "
            f"{config.RELEVANCE_THRESHOLD}); quality ignores interests."
        )
        text_note = (
            f"Relevance is against interests.md (on-interest at >= "
            f"{config.RELEVANCE_THRESHOLD}); quality ignores interests."
        )
    else:
        note = (
            '<strong style="color:#cf222e">Scoring failed or interests.md is '
            "empty - papers were selected at random.</strong>"
        )
        text_note = "Scoring failed or interests.md is empty - papers were selected at random."

    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:760px;margin:0 auto;color:#1f2328;line-height:1.45">',
        f'<h2 style="margin-bottom:4px">arXiv {e(config.ARXIV_CATEGORY)} - {e(target_date)}</h2>',
        f'<p style="margin-top:0;color:#57606a">{len(papers)} papers. {note}<br>'
        f'Episode (once published): <a href="{e(ep_url)}">{e(ep_url)}</a></p>',
    ]
    text = [
        f"arXiv {config.ARXIV_CATEGORY} - {target_date}",
        f"{len(papers)} papers. {text_note}",
        f"Episode (once published): {ep_url}",
        "",
    ]

    for p, role in rows:
        s = scores.get(p.arxiv_id) if scores else None
        score_str = f"rel {s.relevance}/10 &middot; qual {s.quality}/10" if s else "unscored"
        score_txt = f"rel {s.relevance}/10 · qual {s.quality}/10" if s else "unscored"
        colour = _ROLE_COLOURS[role]
        parts.append(
            '<div style="border-top:1px solid #d0d7de;padding:14px 0">'
            f'<div style="font-size:13px"><strong>{score_str}</strong> '
            f'<span style="background:{colour};color:#fff;border-radius:10px;'
            f'padding:1px 8px;margin-left:6px;font-size:12px">{role}</span></div>'
            f'<div style="font-size:16px;font-weight:600;margin:4px 0">'
            f'<a href="{e(p.link)}" style="color:#0969da;text-decoration:none">{e(p.title)}</a></div>'
            f'<div style="font-size:13px;color:#57606a;margin-bottom:6px">'
            f"{e(', '.join(p.authors))} &middot; {e(p.arxiv_id)}</div>"
            f'<div style="font-size:14px">{e(p.abstract)}</div>'
            "</div>"
        )
        text += [
            f"[{score_txt}] [{role}] {p.title}",
            f"  {', '.join(p.authors)}",
            f"  {p.link}",
            f"  {p.abstract}",
            "",
        ]

    parts.append("</div>")
    return subject, "".join(parts), "\n".join(text)


def send_scores_email(
    papers: list[Paper],
    scores: "dict[str, PaperScore] | None",
    deep_dive: list[Paper],
    roundup: list[Paper],
    wildcard: "Paper | None",
    target_date: str,
) -> bool:
    """Send the scores email. Returns True on success; never raises."""
    recipients = [a.strip() for a in config.EMAIL_TO.split(",") if a.strip()]
    if not config.RESEND_API_KEY or not recipients:
        log.info("Scores email disabled (RESEND_API_KEY / EMAIL_TO not set).")
        return False
    try:
        subject, html_body, text_body = build_email(
            papers, scores, deep_dive, roundup, wildcard, target_date
        )
        resp = requests.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            json={
                "from": config.EMAIL_FROM,
                "to": recipients,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=30,
        )
        if resp.status_code >= 300:
            log.warning("Scores email failed: HTTP %d %s", resp.status_code, resp.text[:300])
            return False
    except Exception as exc:  # best-effort: never fail the pipeline
        log.warning("Scores email failed: %s", exc)
        return False
    log.info("Scores email sent to %d recipient(s).", len(recipients))
    return True


if __name__ == "__main__":
    from datetime import date as date_cls

    from arxiv_podcast.fetch import fetch_recent_papers
    from arxiv_podcast.score import load_interests, score_papers
    from arxiv_podcast.select import select_papers

    parser = argparse.ArgumentParser(description="Preview or send today's scores email.")
    parser.add_argument("--dry-run", action="store_true", help="Print the HTML instead of sending.")
    parser.add_argument("--date", default=date_cls.today().isoformat())
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    papers = fetch_recent_papers()
    if not papers:
        raise SystemExit("No papers fetched.")
    interests = load_interests()
    scores = score_papers(papers, interests) if interests else None
    deep, roundup, wildcard = select_papers(papers, scores)

    if args.dry_run or not config.RESEND_API_KEY:
        if not args.dry_run:
            log.info("RESEND_API_KEY not set - printing HTML instead of sending.")
        _, html_body, _ = build_email(papers, scores, deep, roundup, wildcard, args.date)
        print(html_body)
    else:
        sys.exit(0 if send_scores_email(papers, scores, deep, roundup, wildcard, args.date) else 1)
