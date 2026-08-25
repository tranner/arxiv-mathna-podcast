# arXiv Numerical Analysis Daily

A daily podcast that keeps you up to date with new numerical analysis
research - written and voiced entirely by AI. Two hosts pick a couple of
papers posted that day to arXiv's `math.NA` listing and really dig into
them: what problem they're solving, how, and why it matters. Then they
run through everything else that was posted, so you don't miss a paper -
title, authors, and a quick sense of what it's about.

No humans pick the topics, write the script, or record the audio. It all
happens automatically, once a day.

> **This is an independent hobby project.** It isn't affiliated with,
> sponsored by, or endorsed by arXiv or Cornell University - it's just
> built on top of arXiv's public API. See [Licensing &
> attribution](#licensing--attribution) below for the details, and for
> credit to the voice datasets that make the episodes sound the way they do.

## Where to listen

**[Listen on Spotify](https://open.spotify.com/show/0345rjHw2wCOY6o5ILJCaC)** -
currently in beta (see the disclaimer at the top). Also available over RSS
at `https://tranner.github.io/arxiv-mathna-podcast/podcast.xml`, and
anywhere else that supports podcast RSS feeds. If you're setting up your
own copy, see "Publishing" below.

## How an episode gets made

```
fetch → select → script → synth → publish
```

1. **fetch** - checks arXiv for what's new in `math.NA` over the last day
   or so.
2. **select** - randomly picks one to three papers for the deep dive; the
   rest go in the roundup.
3. **script** - writes a natural back-and-forth conversation about them,
   using Claude.
4. **synth** - turns that script into audio, giving each host a distinct
   AI voice (via Piper text-to-speech).
5. **publish** - packages the finished episode with its show notes and
   updates the podcast feed.

---

Everything below this point is for people who want to run, customize, or
self-host this pipeline.

## One-time setup

### 1. Install dependencies

This project uses [`uv`](https://docs.astral.sh/uv/) for Python dependency
management (no manual venv/pip steps). Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repo root:

```bash
uv sync
```

This creates `.venv` and installs everything pinned in `uv.lock` -
reproducible, no `pip install` needed. Run any command in that environment
with `uv run ...` (see below) - no need to `source .venv/bin/activate`.

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

Downloads the Piper binary and the two voice models (`en_GB-northern_english_male-medium`
and `en_GB-cori-high` by default) into `./piper/` (gitignored - re-run this
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
uv run python -m arxiv_podcast.main
```

Produces `docs/episodes/<today>.mp3` + `docs/episodes/<today>.json` (show
notes sidecar) and rebuilds `docs/podcast.xml` + `docs/index.html`. Re-running
the same day is a no-op unless you pass `--force`:

```bash
uv run python -m arxiv_podcast.main --force
uv run python -m arxiv_podcast.main --date 2026-01-15   # backfill a specific date
```

`docs/` is a local build directory - it isn't tracked on `main` (see
"Publishing" below for where it actually ends up). Before running the
pipeline for real, pull in whatever's already published so today's episode
joins the existing feed instead of starting a new one:

```bash
bash scripts/fetch_pages_branch.sh   # populates docs/ from the published site, if any
uv run python -m arxiv_podcast.main
```

Each pipeline stage can also be run and inspected on its own for debugging:

```bash
uv run python -m arxiv_podcast.fetch     # just print today's fetched papers
uv run python -m arxiv_podcast.select    # fetch + show the deep-dive/roundup split
uv run python -m arxiv_podcast.script    # fetch + select + print the dialogue script
uv run python -m arxiv_podcast.synth --smoke   # audio pipeline only, no LLM call (fast)
uv run python -m arxiv_podcast.publish   # rebuild the feed/index from files already on disk
```

## Publishing: GitHub Pages + Spotify

Episodes live on a dedicated **`pages` branch**, kept deliberately separate
from `main`: `main` is source code only and never contains a single mp3;
`pages` holds the generated site (episodes, feed, show notes, cover art).
On top of keeping `main` clean, `pages` itself is kept small too - every
publish **replaces that branch's entire history with one fresh commit**
(`scripts/publish_pages_branch.sh`), so its size tracks the current episode
retention window (`EPISODE_RETENTION_DAYS`, 90 days by default) rather than
every episode the podcast has ever put out.

The show launches labeled **(Beta)** - there's no dedicated beta field in
podcast RSS/Spotify, so it's a title tag plus a note in the description
(`PODCAST_TITLE` / `PODCAST_DESCRIPTION` in `config.py`). Drop both once
you're happy calling it stable - podcast apps key subscriptions off the feed
URL, not the title, so renaming later is safe.

### Status: live

✅ Published - **[on Spotify](https://open.spotify.com/show/0345rjHw2wCOY6o5ILJCaC)**
and via RSS at `https://tranner.github.io/arxiv-mathna-podcast/podcast.xml`.
New episodes published to the `pages` branch are picked up by Spotify
automatically - no manual step per episode.

How it got there (kept here as reference - e.g. if Pages settings ever need
redoing, or you're setting up your own fork):
1. `git push origin main`.
2. Build and publish an episode:
   ```bash
   bash scripts/fetch_pages_branch.sh
   uv run python -m arxiv_podcast.main
   bash scripts/publish_pages_branch.sh --push
   ```
   `--push` force-pushes `pages` to `origin` (expected - see above; it's a
   squashed history by design, not a mistake).
3. Repo **Settings → Pages**: source set to the **`pages` branch, `/ (root)`
   folder** - not `main`.
4. **[Spotify for Podcasters](https://podcasters.spotify.com/)** → *Add your
   podcast* → *I have a podcast already* → the RSS URL above. Spotify emailed
   a verification code to `T.Ranner@leeds.ac.uk` (`PODCAST_EMAIL`, paired with
   `PODCAST_OWNER_NAME` in the feed's `itunes:owner` tag - backend-only
   metadata, not shown to listeners) to confirm ownership. The public byline
   listeners see is the separate `PODCAST_AUTHOR` (`itunes:author`).

## Automating the daily run

`.github/workflows/daily.yml` runs the whole pipeline on a cron (~07:00 UTC
daily) and publishes the result to the `pages` branch the same way the
manual steps above do - pushing with GitHub Actions' own built-in token, not
your personal credentials.

Script generation in CI uses the **Anthropic API** rather than `claude -p`
(which needs an interactive login a runner doesn't have) -
`script.py::_call_model_api()` calls the Anthropic SDK with
`config.ANTHROPIC_MODEL` (`claude-haiku-4-5` by default, ~$0.02/episode,
~$7/year). One-time setup:

1. Create an API key at [console.anthropic.com](https://console.anthropic.com/).
2. Repo **Settings → Secrets and variables → Actions → New repository
   secret** → name it `ANTHROPIC_API_KEY`.

That's it - `daily.yml` already has `SCRIPT_BACKEND=api` and reads the secret.

### Making sure it actually runs

- **Test it for real before trusting the schedule.** Actions tab → this
  workflow → *Run workflow* (that's what `workflow_dispatch` in the trigger
  is for). This catches anything environment-specific a local run wouldn't
  - Actions runners hitting arXiv/Piper's release servers, the secret being
  set correctly, etc.
- **Scheduled runs are best-effort, not exact.** GitHub can delay the
  `schedule` trigger under load, especially right at the top of the hour -
  don't be surprised by a 07:xx run landing at 07:20 sometimes.
- **GitHub auto-disables scheduled workflows after 60 days of repository
  inactivity** (public repos). A successfully-running daily workflow pushes
  to `pages` every day, which should count as activity and keep this from
  ever triggering - but if the workflow starts silently failing (e.g. an
  expired/revoked API key) there's no successful push, so a prolonged outage
  could compound into the schedule getting disabled on top of not working.
  If episodes stop appearing, check the **Actions** tab first - a disabled
  schedule shows a banner there with a one-click re-enable.
- **Failure notifications aren't on by default.** If you want an email when
  a scheduled run fails, enable it yourself:
  [github.com/settings/notifications](https://github.com/settings/notifications) →
  Actions → "Send notifications for failed workflows only" (or similar,
  under your notification preferences) - otherwise a silent failure is only
  visible if you check the Actions tab yourself.

## Configuration

Every setting lives in `arxiv_podcast/config.py` and can be overridden via
environment variable (see `.env.example` for the full list) - e.g. category,
target episode length, host names/voices, feed metadata, episode retention.

## Licensing & attribution

**arXiv content.** We only ever fetch metadata (title, authors, abstract) -
via arXiv's daily category RSS feed (`rss.arxiv.org`), one request per run -
and link back to the paper's `arxiv.org/abs/...` page, never the PDF or full
text. arXiv's [API Terms of Use](https://info.arxiv.org/help/api/tou.html)
place that metadata under CC0 (public domain), so there's no copyright
constraint there. One thing the ToU *does* require, already handled:

- **No implied endorsement** - the ToU prohibits "brand[ing] your project
  with arXiv's names... in a manner that implies arXiv's endorsement." Since
  the podcast is literally titled *"arXiv Numerical Analysis Daily,"* the
  feed description (`PODCAST_DESCRIPTION` in `config.py`) carries an explicit
  disclaimer - *"This is an independent project, not affiliated with,
  sponsored by, or endorsed by arXiv or Cornell University"* - plus arXiv's
  suggested courtesy line, *"Thank you to arXiv for use of its open access
  interoperability."* This shows up in the RSS feed and on the podcast site
  automatically; no per-episode action needed. If you rename or re-word
  things, keep some form of that disclaimer.

**Individual papers.** Authors set their own license per paper (arXiv's
default non-exclusive license, or CC BY/BY-SA/BY-NC-SA/CC0, etc.) - but since
we only discuss/summarize the publicly-posted abstract for commentary, not
reproduce the paper itself, this isn't a live concern regardless of the
per-paper license.

**Piper voices.** Piper itself is MIT-licensed. The two default voice
models have different underlying sources, and both are credited by name in
`PODCAST_DESCRIPTION` (so listeners see it too, not just this README):

- `en_GB-cori-high` ("Cori") - trained on LibriVox.org recordings, **public
  domain**. No constraint.
- `en_GB-northern_english_male-medium` - trained on [SLR83, "Open-source
  Multi-speaker Corpora of the English Accents in the British
  Isles"](https://www.openslr.org/83/) (© Google, Inc.), **CC BY-SA 4.0**.
  Commercial use is permitted, but the license requires attribution *in the
  project* (not per-episode, though welcome there too) crediting the SLR83
  dataset, and any redistribution of the voice model itself must be shared
  under the same CC BY-SA 4.0 license. If you
  swap in a different voice via `HOST_A_VOICE`/`HOST_B_VOICE`, check that
  voice's own `MODEL_CARD` on
  [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  for its source dataset and license, and update `PODCAST_DESCRIPTION` to
  match - it's a static string, not generated from the voice names.

**AI-generated content.** The scripts and audio are generated by an LLM
(Claude) and a TTS model (Piper), and `PODCAST_DESCRIPTION` says so plainly.
Worth keeping as podcast platforms increasingly expect AI-generated shows to
disclose it.

## Repo layout

```
arxiv_podcast/    the pipeline (fetch, select, script, synth, publish, main)
scripts/          setup_piper.sh, fetch_pages_branch.sh, publish_pages_branch.sh
assets/           static files copied into docs/ on every publish (cover.jpg)
docs/             local build dir - GitHub Pages root once published, but
                  gitignored on `main` (see "Publishing: GitHub Pages + Spotify")
pyproject.toml    dependencies (managed with uv)
uv.lock           pinned dependency versions - commit this, don't edit by hand
.github/workflows/daily.yml   the cron automation
```

Two branches, two purposes: `main` is source code, `pages` is the published
site (squashed history each publish - see "Publishing" above).
