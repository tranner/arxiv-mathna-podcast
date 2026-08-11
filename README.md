# arxiv-podcast

Automatically generates a daily podcast from the arXiv `math.NA` (Numerical
Analysis) listing: two AI hosts do a deep dive on 1-3 randomly chosen papers,
then rapid-fire through the rest of the day's listing (title, authors, and a
one-line gloss of the abstract for each). Runs manually today; designed to
run on a daily GitHub Actions cron and publish to Spotify via a self-hosted
RSS feed.

## How it works

```
fetch → select → script → synth → publish
```

1. **fetch** - pulls the last ~36h of `math.NA` papers from the arXiv API.
2. **select** - randomly picks 1-3 papers for the deep dive; the rest become
   the roundup.
3. **script** - writes a two-host dialogue script covering them, using the
   **Claude Code CLI** (`claude -p`) and your existing Claude subscription.
4. **synth** - voices each line with **Piper** (local, offline, free TTS),
   alternating two distinct voices per host, and stitches it into one mp3.
5. **publish** - writes the mp3 + show notes into `docs/episodes/`, and
   regenerates `docs/podcast.xml` (the podcast RSS feed) and `docs/index.html`.

`docs/` is a GitHub Pages site. Point Spotify for Podcasters at the RSS feed
URL once, and it auto-ingests every new episode from then on - **there is no
per-episode Spotify upload step**.

## One-time setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install `ffmpeg` (used by `pydub` to build the mp3):

```bash
# Debian/Ubuntu
sudo apt-get install ffmpeg
# macOS
brew install ffmpeg
```

### 2. Set up Piper (text-to-speech)

```bash
bash scripts/setup_piper.sh
```

Downloads the Piper binary and the two voice models (`en_US-hfc_female-medium`
and `en_US-ryan-high` by default) into `./piper/` (gitignored - re-run this
any time the directory is missing, e.g. after a fresh clone). Works on
Linux (x86_64/arm64) and macOS (Intel/Apple Silicon).

### 3. Make sure Claude Code is logged in

The script-writing step shells out to `claude -p`, using whatever Claude
subscription you're logged into - no API key needed for local/manual runs.
Sanity check:

```bash
claude -p "say hi in one word"
```

### 4. Set your site URL

Before publishing for real, set `SITE_BASE_URL` to where GitHub Pages will
serve this repo from - it's baked into the RSS `<enclosure>` URLs:

```bash
export SITE_BASE_URL="https://<your-github-username>.github.io/<repo-name>"
```

(See `.env.example` for this and other tunable settings - podcast title,
host names/voices, target episode length, etc.)

## Running it manually

```bash
python -m arxiv_podcast.main
```

Produces `docs/episodes/<today>.mp3` + `docs/episodes/<today>.json` (show
notes sidecar) and rebuilds `docs/podcast.xml` + `docs/index.html`. Re-running
the same day is a no-op unless you pass `--force`:

```bash
python -m arxiv_podcast.main --force
python -m arxiv_podcast.main --date 2026-01-15   # backfill a specific date
```

Each pipeline stage can also be run and inspected on its own for debugging:

```bash
python -m arxiv_podcast.fetch     # just print today's fetched papers
python -m arxiv_podcast.select    # fetch + show the deep-dive/roundup split
python -m arxiv_podcast.script    # fetch + select + print the dialogue script
python -m arxiv_podcast.synth --smoke   # audio pipeline only, no LLM call (fast)
python -m arxiv_podcast.publish   # rebuild the feed/index from files already on disk
```

## Publishing: GitHub Pages + Spotify

1. Push this repo to GitHub.
2. Repo **Settings → Pages**: set source to the `main` branch, `/docs` folder.
3. Run the pipeline (manually, or via the workflow below) and push - Pages
   will serve `docs/podcast.xml` at `https://<user>.github.io/<repo>/podcast.xml`.
4. Go to **[Spotify for Podcasters](https://podcasters.spotify.com/)** →
   *Add your podcast* → *I have a podcast already, I just need to add it here*
   → paste that RSS URL. Spotify verifies ownership (usually by emailing a
   code to the address in `PODCAST_EMAIL` / the feed's `itunes:owner`) and
   from then on **automatically pulls in every new episode** whenever the
   feed updates. No further manual step per episode.

Set `PODCAST_EMAIL` before submitting - Spotify's ownership verification
needs it.

## Automating the daily run

`.github/workflows/daily.yml` runs the pipeline on a cron (~07:00 UTC daily)
and commits the result, but **the script-writing step needs a decision
before it'll work unattended**: `claude -p` requires an interactive login,
which a GitHub Actions runner doesn't have. Once you've reviewed a few manual
episodes and are happy with them, pick one:

- **Anthropic API key (recommended)** - implement
  `arxiv_podcast/script.py::_call_model_api()` to call the Anthropic SDK
  (`claude-haiku-4-5` is plenty for this and costs about $0.02/episode,
  ~$7/year), add an `ANTHROPIC_API_KEY` repository secret, and set
  `SCRIPT_BACKEND=api` (uncomment the relevant lines in `daily.yml`).
- **Exported CLI credentials** - export Claude Code's auth as a CI secret and
  adapt `_call_model_cli()` to use it non-interactively.

Everything else in the workflow (fetch, Piper setup + caching, synth,
publish, git commit) is already wired up and doesn't need changes.

## Configuration

Every setting lives in `arxiv_podcast/config.py` and can be overridden via
environment variable (see `.env.example` for the full list) - e.g. category,
target episode length, host names/voices, feed metadata, episode retention.

## Repo layout

```
arxiv_podcast/    the pipeline (fetch, select, script, synth, publish, main)
scripts/          scripts/setup_piper.sh
docs/             GitHub Pages root: episodes/, podcast.xml, index.html
.github/workflows/daily.yml   the cron automation
```
