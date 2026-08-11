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
HOST_A_VOICE = os.environ.get("HOST_A_VOICE", "en_US-hfc_female-medium")
HOST_B_VOICE = os.environ.get("HOST_B_VOICE", "en_US-ryan-high")

# Silence inserted between speaker turns, in milliseconds.
TURN_GAP_MS = int(os.environ.get("TURN_GAP_MS", "350"))
AUDIO_BITRATE = os.environ.get("AUDIO_BITRATE", "64k")

# --- Publishing / feed ---------------------------------------------------------
DOCS_DIR = REPO_ROOT / "docs"
EPISODES_DIR = DOCS_DIR / "episodes"
FEED_PATH = DOCS_DIR / "podcast.xml"

# Base URL the published files are served from (GitHub Pages). Must be set
# correctly before publishing for real - the RSS <enclosure> URLs are built
# from this. Format: https://<user>.github.io/<repo>
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://example.github.io/arxiv-podcast")

PODCAST_TITLE = os.environ.get("PODCAST_TITLE", "arXiv Numerical Analysis Daily")
PODCAST_DESCRIPTION = os.environ.get(
    "PODCAST_DESCRIPTION",
    "A daily AI-generated podcast digesting the newest papers from the arXiv "
    "math.NA (Numerical Analysis) listing - a deep dive on a few randomly "
    "chosen papers plus a rapid roundup of everything else that was posted.",
)
PODCAST_AUTHOR = os.environ.get("PODCAST_AUTHOR", "arxiv-podcast")
PODCAST_EMAIL = os.environ.get("PODCAST_EMAIL", "")
PODCAST_LANGUAGE = os.environ.get("PODCAST_LANGUAGE", "en-us")
PODCAST_IMAGE_URL = os.environ.get("PODCAST_IMAGE_URL", f"{SITE_BASE_URL}/cover.jpg")

# How many days of episodes to keep committed in docs/episodes/ (older ones
# are pruned by publish.py to keep the repo/Pages site small).
EPISODE_RETENTION_DAYS = int(os.environ.get("EPISODE_RETENTION_DAYS", "90"))


def ensure_dirs() -> None:
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
