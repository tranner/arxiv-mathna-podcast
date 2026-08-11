"""Central configuration for the arXiv podcast pipeline.

Every value can be overridden with an environment variable of the same name
(useful for CI, testing with a different category, etc.) without editing code.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- arXiv source -----------------------------------------------------------
ARXIV_CATEGORY = os.environ.get("ARXIV_CATEGORY", "math.NA")
ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_MAX_RESULTS = int(os.environ.get("ARXIV_MAX_RESULTS", "60"))
# How far back to look for "new today" papers, in hours. arXiv's daily
# announcement cadence means a 24-36h window reliably catches the latest batch.
ARXIV_LOOKBACK_HOURS = int(os.environ.get("ARXIV_LOOKBACK_HOURS", "36"))
ARXIV_USER_AGENT = os.environ.get(
    "ARXIV_USER_AGENT",
    "arxiv-podcast/0.1 (personal project; generates a daily podcast digest)",
)

# --- Episode selection --------------------------------------------------------
DEEP_DIVE_MIN = int(os.environ.get("DEEP_DIVE_MIN", "1"))
DEEP_DIVE_MAX = int(os.environ.get("DEEP_DIVE_MAX", "3"))
# Cap how many papers get a roundup mention, to keep the episode near the
# target runtime even on days with a large arXiv batch.
ROUNDUP_MAX = int(os.environ.get("ROUNDUP_MAX", "12"))

# --- Script generation --------------------------------------------------------
TARGET_MINUTES = int(os.environ.get("TARGET_MINUTES", "15"))
# ~150 spoken words per minute is a reasonable conversational pace for two
# hosts trading lines.
WORDS_PER_MINUTE = int(os.environ.get("WORDS_PER_MINUTE", "150"))
TARGET_WORD_COUNT = TARGET_MINUTES * WORDS_PER_MINUTE

HOST_A_NAME = os.environ.get("HOST_A_NAME", "Alex")
HOST_B_NAME = os.environ.get("HOST_B_NAME", "Sam")

# Which model-calling backend script.py uses. "cli" shells out to the Claude
# Code CLI (`claude -p`) using the operator's logged-in subscription - no API
# key required, but only works on a machine that's already authenticated.
# "api" uses the Anthropic SDK with ANTHROPIC_API_KEY (for CI automation).
SCRIPT_BACKEND = os.environ.get("SCRIPT_BACKEND", "cli")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

# --- Text-to-speech (Piper) ---------------------------------------------------
PIPER_DIR = REPO_ROOT / "piper"
PIPER_BIN = Path(os.environ.get("PIPER_BIN", str(PIPER_DIR / "piper" / "piper")))
PIPER_VOICES_DIR = Path(os.environ.get("PIPER_VOICES_DIR", str(PIPER_DIR / "voices")))

# Piper voice model names (without file extension); setup_piper.sh downloads
# the matching .onnx + .onnx.json pair for each into PIPER_VOICES_DIR.
HOST_A_VOICE = os.environ.get("HOST_A_VOICE", "en_GB-jenny_dioco-medium")
HOST_B_VOICE = os.environ.get("HOST_B_VOICE", "en_GB-cori-high")

# Silence inserted between speaker turns, in milliseconds.
TURN_GAP_MS = int(os.environ.get("TURN_GAP_MS", "350"))
AUDIO_BITRATE = os.environ.get("AUDIO_BITRATE", "64k")

# --- Publishing / feed ---------------------------------------------------------
DOCS_DIR = REPO_ROOT / "docs"
EPISODES_DIR = DOCS_DIR / "episodes"
FEED_PATH = DOCS_DIR / "podcast.xml"

# Static assets (currently just cover.jpg) that get copied into docs/ on
# every publish. Tracked on `main` (unlike docs/ itself) since docs/ is
# rebuilt from the `pages` branch each run - this is the actual source of
# truth for the cover image, recoverable even if the pages branch is ever
# lost or corrupted.
ASSETS_DIR = REPO_ROOT / "assets"

# Base URL the published files are served from (GitHub Pages). Must be set
# correctly before publishing for real - the RSS <enclosure> URLs are built
# from this. Format: https://<user>.github.io/<repo>
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://tranner.github.io/arxiv-mathna-podcast")

# "(Beta)" in the title + a beta note in the description is the standard way
# indie podcasts signal early-stage status - there's no dedicated beta field
# in podcast RSS/Spotify. Drop "(Beta)" from the title once you're ready to
# call it stable; remove the beta sentence from the description at the same
# time. Renaming the title later is fine - podcast apps key subscriptions off
# the feed URL, not the title.
PODCAST_TITLE = os.environ.get("PODCAST_TITLE", "arXiv Numerical Analysis Daily (Beta)")
# Includes a non-affiliation disclaimer and arXiv's suggested acknowledgment
# line, per arXiv's API Terms of Use (https://info.arxiv.org/help/api/tou.html)
# - which prohibits implying arXiv's endorsement/backing of a project built
# on their API - plus voice attribution for HOST_A_VOICE/HOST_B_VOICE's
# source datasets (required for the Jenny/Dioco voice; see README "Licensing
# & attribution"). If you change the default host voices, update this text
# to match - it isn't generated automatically from the voice names.
PODCAST_DESCRIPTION = os.environ.get(
    "PODCAST_DESCRIPTION",
    "A daily podcast where two AI hosts talk through the newest papers "
    "posted to the arXiv math.NA (Numerical Analysis) listing - a deep dive "
    "on a few randomly chosen papers, plus a rapid-fire rundown of "
    "everything else posted that day. Every script and voice is "
    "AI-generated: text by Claude, voices by Piper text-to-speech (Jenny, "
    "from the Jenny/Dioco dataset, and Cori, trained on public-domain "
    "LibriVox.org recordings). "
    "This show is in beta while the format, voices, and episode length get "
    "dialed in - expect some rough edges and the occasional gap in the "
    "schedule. "
    "This is an independent project, not "
    "affiliated with, sponsored by, or endorsed by arXiv or Cornell "
    "University. Thank you to arXiv for use of its open access "
    "interoperability.",
)
PODCAST_AUTHOR = os.environ.get("PODCAST_AUTHOR", "Tom Ranner")
# Spotify emails a verification code here during RSS submission.
PODCAST_EMAIL = os.environ.get("PODCAST_EMAIL", "T.Ranner@leeds.ac.uk")
PODCAST_LANGUAGE = os.environ.get("PODCAST_LANGUAGE", "en-us")
PODCAST_IMAGE_URL = os.environ.get("PODCAST_IMAGE_URL", f"{SITE_BASE_URL}/cover.jpg")

# How many days of episodes to keep committed in docs/episodes/ (older ones
# are pruned by publish.py to keep the repo/Pages site small).
EPISODE_RETENTION_DAYS = int(os.environ.get("EPISODE_RETENTION_DAYS", "90"))


def ensure_dirs() -> None:
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
