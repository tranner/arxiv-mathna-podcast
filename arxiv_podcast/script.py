"""Generate the two-host podcast dialogue script from selected papers.

Model access is isolated behind `_call_model()` / `_call_model_cli()` /
`_call_model_api()` so the rest of this module (prompt construction, JSON
parsing/validation) doesn't care how the text was produced or how retries
continue a conversation. Two backends:
- "cli" (default): Claude Code (`claude -p`), using the operator's logged-in
  subscription. Only works interactively logged-in, e.g. local/manual runs.
- "api": the Anthropic SDK with ANTHROPIC_API_KEY. Used for unattended CI
  automation (see .github/workflows/daily.yml).
"""

import json
import logging
import os
import re
import subprocess

import anthropic

from arxiv_podcast import config
from arxiv_podcast.models import DialogueLine, Paper

log = logging.getLogger(__name__)

VALID_SPEAKERS = {"HOST_A", "HOST_B"}



class ScriptGenerationError(RuntimeError):
    pass


# --- Usage / cost tracking --------------------------------------------------------

# One entry per model call this process has made: (label, input_tokens,
# output_tokens, cost_usd or None). main.py reads this for a per-run total.
USAGE_LOG: list[tuple[str, int, int, "float | None"]] = []


def _record_usage(label: str, input_tokens: int, output_tokens: int, cost: "float | None") -> None:
    USAGE_LOG.append((label, input_tokens, output_tokens, cost))
    log.info(
        "Model usage [%s]: %d input + %d output tokens, cost %s",
        label,
        input_tokens,
        output_tokens,
        f"${cost:.4f}" if cost is not None else "unknown",
    )


def total_cost_usd() -> float:
    return sum(c for *_, c in USAGE_LOG if c is not None)


# --- Model backends -----------------------------------------------------------


def _call_model_cli(
    prompt: str,
    resume_session: "str | None" = None,
    label: str = "model",
    effort: "str | None" = None,
) -> tuple[str, str]:
    """Call the Claude Code CLI in print mode. Returns (result_text, session_id)."""
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--allowedTools", ""]
    if resume_session:
        cmd += ["-r", resume_session]
    else:
        # Model is only pinned on the fresh call; -r continues in the same
        # session/model. The full model ID (not an alias like "haiku", which
        # drifts to newer models) keeps both backends on the same model.
        cmd += ["--model", config.ANTHROPIC_MODEL]
        if effort and config.model_supports_effort():
            cmd += ["--effort", effort]

    log.info("Invoking Claude Code CLI (%s)", "resume" if resume_session else "new session")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as e:
        raise ScriptGenerationError("claude -p timed out after 300s") from e
    except FileNotFoundError as e:
        raise ScriptGenerationError(
            "`claude` CLI not found on PATH. Install Claude Code and log in, or "
            "switch SCRIPT_BACKEND to 'api'."
        ) from e

    if proc.returncode != 0:
        raise ScriptGenerationError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:2000]}"
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ScriptGenerationError(
            f"claude -p did not return valid JSON envelope: {proc.stdout[:2000]}"
        ) from e

    if envelope.get("is_error"):
        raise ScriptGenerationError(f"claude -p reported an error: {envelope}")

    usage = envelope.get("usage") or {}
    input_tokens = (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
    # On a subscription this is notional (what the call would cost via the API).
    _record_usage(label, input_tokens, usage.get("output_tokens", 0), envelope.get("total_cost_usd"))

    result_text = envelope.get("result", "")
    session_id = envelope.get("session_id", "")
    if not result_text:
        raise ScriptGenerationError(f"claude -p returned an empty result: {envelope}")

    return result_text, session_id


def _call_model_api(
    prompt: str,
    history: "list[dict] | None" = None,
    label: str = "model",
    effort: "str | None" = None,
) -> tuple[str, list[dict]]:
    """Call the Anthropic API directly. `history` is the prior message list
    to continue from (for retries) - mirrors the CLI backend's session
    resume, just as an explicit message list instead of a session ID.
    Returns (result_text, updated_message_history)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ScriptGenerationError(
            "SCRIPT_BACKEND='api' requires the ANTHROPIC_API_KEY environment "
            "variable (a repository secret in CI)."
        )

    client = anthropic.Anthropic(api_key=api_key)
    messages = list(history) if history else []
    messages.append({"role": "user", "content": prompt})

    # Headroom over TARGET_WORD_COUNT for JSON structure overhead, the
    # occasional expanded-retry response (which runs longer than the
    # original), and - on models that think by default, like Haiku 5.5 -
    # thinking tokens, which count against max_tokens too. Kept under 64K so
    # a non-streaming request stays clear of SDK timeouts.
    max_tokens = min(64000, max(8000, int(config.TARGET_WORD_COUNT * 8)))
    extra = {}
    if effort and config.model_supports_effort():
        extra["output_config"] = {"effort": effort}

    log.info(
        "Invoking Anthropic API (%s, %s)",
        config.ANTHROPIC_MODEL,
        "resume" if history else "new conversation",
    )
    try:
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=messages,
            **extra,
        )
    except anthropic.APIError as e:
        raise ScriptGenerationError(f"Anthropic API call failed: {e}") from e

    _record_usage(
        label,
        response.usage.input_tokens,
        response.usage.output_tokens,
        config.model_cost_usd(response.usage.input_tokens, response.usage.output_tokens),
    )

    if response.stop_reason == "refusal":
        raise ScriptGenerationError(f"Model declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        log.warning(
            "Response hit max_tokens (%d) and may be truncated - consider "
            "raising TARGET_WORD_COUNT's headroom if this recurs.",
            max_tokens,
        )

    result_text = "".join(block.text for block in response.content if block.type == "text")
    if not result_text:
        raise ScriptGenerationError(f"Anthropic API returned an empty response: {response}")

    messages.append({"role": "assistant", "content": result_text})
    return result_text, messages


def _call_model(
    prompt: str, state: object = None, label: str = "model", effort: "str | None" = None
) -> tuple[str, object]:
    """Dispatch to the configured backend. `state` is an opaque continuation
    token from a previous call (session_id string for "cli", message history
    list for "api"), or None to start a fresh conversation."""
    if config.SCRIPT_BACKEND == "cli":
        return _call_model_cli(prompt, resume_session=state, label=label, effort=effort)
    elif config.SCRIPT_BACKEND == "api":
        return _call_model_api(prompt, history=state, label=label, effort=effort)
    raise ScriptGenerationError(
        f"Unsupported SCRIPT_BACKEND={config.SCRIPT_BACKEND!r} - expected 'cli' or 'api'."
    )


# --- Prompt construction --------------------------------------------------------


WILDCARD_NOTE = (
    "NOTE FOR THE HOSTS: this one is today's WILDCARD - a standout paper from "
    "outside the show's usual focus areas, picked for its quality. Introduce "
    "it as such (e.g. \"now for something a bit outside our usual beat...\").\n"
)


def _paper_block(
    p: Paper,
    include_full_abstract: bool = True,
    full_text: "str | None" = None,
    is_wildcard: bool = False,
) -> str:
    abstract = p.abstract if include_full_abstract else p.abstract[:280]
    block = (
        (WILDCARD_NOTE if is_wildcard else "")
        + f"arXiv ID: {p.arxiv_id}\n"
        f"Title: {p.title}\n"
        f"Authors: {p.authors_str(max_authors=6)}\n"
        f"Abstract: {abstract}\n"
    )
    if full_text:
        block += (
            "FULL TEXT (extracted from the PDF, for your reference - use it for "
            "accurate detail, but still explain at podcast level and never read "
            f"out equations):\n{full_text}\n"
        )
    return block


def build_prompt(
    deep_dive: list[Paper],
    roundup: list[Paper],
    date: str,
    wildcard: "Paper | None" = None,
    full_texts: "dict[str, str] | None" = None,
) -> str:
    full_texts = full_texts or {}
    wildcard_id = wildcard.arxiv_id if wildcard else None
    deep_blocks = "\n---\n".join(
        _paper_block(
            p,
            full_text=full_texts.get(p.arxiv_id),
            is_wildcard=p.arxiv_id == wildcard_id,
        )
        for p in deep_dive
    )
    wildcard_instruction = (
        "\n   One of these papers is marked as today's WILDCARD - a standout paper\n"
        "   from outside the show's usual focus, chosen for its quality. When you\n"
        "   reach it, have the hosts flag it to listeners as exactly that.\n"
        if wildcard
        else ""
    )
    roundup_blocks = "\n---\n".join(_paper_block(p, include_full_abstract=False) for p in roundup)

    # Rough per-segment word budget so the model doesn't undershoot the total.
    cold_open_words = 120
    sign_off_words = 100
    roundup_words = len(roundup) * 70
    deep_dive_words = max(
        config.TARGET_WORD_COUNT - cold_open_words - sign_off_words - roundup_words, 300
    )
    per_paper_deep_dive_words = deep_dive_words // max(len(deep_dive), 1)

    return f"""You are writing a script for a daily podcast called "{config.PODCAST_TITLE}".
It is a two-host conversational podcast about new papers in the arXiv
{config.ARXIV_CATEGORY} (Numerical Analysis) category, for the date {date}.

The two hosts are:
- {config.HOST_A_NAME} (speaker key "HOST_A")
- {config.HOST_B_NAME} (speaker key "HOST_B")

They are knowledgeable, curious, and enjoy explaining mathematical ideas in an
accessible way to an audience of applied mathematicians, engineers, and
scientifically literate listeners. They are NOT dumbing things down to a
general audience - the listeners know calculus and linear algebra - but they
avoid reading out dense equations, and instead explain the intuition, the
method, why it matters, and what's novel.

TARGET LENGTH: this is a {config.TARGET_MINUTES}-minute podcast episode. The
script MUST be approximately {config.TARGET_WORD_COUNT} words of spoken
dialogue in total (summed across all "text" fields). This is a firm target,
not a ceiling - a short, thin script is a failed script. If you are unsure
whether you've written enough, write more: add follow-up questions, ask for
a concrete example or an intuition-building analogy, have a host push back
or ask "wait, why does that work?", or connect the paper to related work or
practical applications. Do not pad with filler or repetition - add more real
substance.

STRUCTURE AND WORD BUDGET (these should sum to about {config.TARGET_WORD_COUNT}):
1. Cold open (~{cold_open_words} words): greet listeners, state today's date,
   and say this is the {config.ARXIV_CATEGORY} daily digest.
2. DEEP DIVE (~{deep_dive_words} words total, roughly {per_paper_deep_dive_words}
   words per paper): a substantial, back-and-forth conversation about EACH of
   the following {len(deep_dive)} paper(s), one at a time. When introducing
   each paper, a host must naturally say its title and author(s) out loud
   (first author plus "and colleagues" is fine for long author lists) before
   getting into the discussion - listeners should always know exactly which
   paper is being discussed, even if they're just listening and not looking
   at show notes. Then cover: the problem it addresses and why that problem
   matters, the core idea/method, what's new or surprising about the result,
   and what it enables going forward. Have the hosts riff off each other, ask
   each other questions, disagree a little, and react - not just alternate
   monologues. This is the heart of the episode - do not rush it.{wildcard_instruction}

{deep_blocks}

3. ROUNDUP (~{roundup_words} words total, roughly 60-80 words per paper): a
   faster-paced segment where the hosts go through the remaining
   {len(roundup)} papers from today's listing. For each, give the title, the
   authors (first author plus "and colleagues" is fine for long author
   lists), and a couple of sentences of plain-English gloss of what it's
   about and why it's interesting, based on the abstract below. Brisk, but
   not just a title readout - give each paper a real, if short, moment.

{roundup_blocks}

4. Sign-off (~{sign_off_words} words): a warm wrap-up.

OUTPUT FORMAT - THIS IS CRITICAL:
Return ONLY a single JSON object and nothing else - no markdown code fences,
no preamble, no explanation before or after. The JSON must match exactly this
shape:

{{"lines": [{{"speaker": "HOST_A", "text": "..."}}, {{"speaker": "HOST_B", "text": "..."}}, ...]}}

- "speaker" must be exactly "HOST_A" or "HOST_B" (no other values).
- "text" is what that host says in that turn - natural spoken dialogue, no
  stage directions, no asterisks, no markdown, no equations or LaTeX (this
  will be read aloud by a text-to-speech engine, so spell out any symbols in
  words, e.g. "order h squared" not "O(h^2)").
- Keep individual turns conversational length (roughly one to four sentences).
- Do not include the paper's arXiv ID in the spoken text.
"""


# --- Parsing / validation --------------------------------------------------------


def _extract_json_object(text: str) -> str:
    """Best-effort extraction of a JSON object from model output that may be
    wrapped in markdown code fences or have stray text around it."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first : last + 1]
    return text


def parse_dialogue(raw_text: str) -> list[DialogueLine]:
    candidate = _extract_json_object(raw_text)
    data = json.loads(candidate)  # raises json.JSONDecodeError on failure

    if not isinstance(data, dict) or "lines" not in data:
        raise ScriptGenerationError(f"JSON missing top-level 'lines' key: {candidate[:500]}")

    lines_raw = data["lines"]
    if not isinstance(lines_raw, list) or not lines_raw:
        raise ScriptGenerationError("'lines' must be a non-empty array")

    lines: list[DialogueLine] = []
    for i, item in enumerate(lines_raw):
        speaker = item.get("speaker")
        text = item.get("text", "").strip()
        if speaker not in VALID_SPEAKERS:
            raise ScriptGenerationError(
                f"line {i}: invalid speaker {speaker!r}, expected one of {VALID_SPEAKERS}"
            )
        if not text:
            raise ScriptGenerationError(f"line {i}: empty text")
        lines.append(DialogueLine(speaker=speaker, text=text))

    return lines


# --- Orchestration --------------------------------------------------------------


# Below this fraction of the target word count, ask the model to expand
# rather than accepting a thin episode.
MIN_WORD_COUNT_FRACTION = 0.75


def generate_dialogue(
    deep_dive: list[Paper],
    roundup: list[Paper],
    date: str,
    max_attempts: int = 4,
    wildcard: "Paper | None" = None,
    full_texts: "dict[str, str] | None" = None,
) -> list[DialogueLine]:
    prompt = build_prompt(deep_dive, roundup, date, wildcard=wildcard, full_texts=full_texts)
    state = None  # session_id (cli) or message history (api); None = fresh conversation
    last_error: "Exception | str | None" = None
    last_error_prompt = ""
    min_words = int(config.TARGET_WORD_COUNT * MIN_WORD_COUNT_FRACTION)

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            raw_text, state = _call_model(prompt, label="script")
        else:
            raw_text, state = _call_model(
                last_error_prompt, state=state, label=f"script retry {attempt - 1}"
            )

        try:
            lines = parse_dialogue(raw_text)
        except (json.JSONDecodeError, ScriptGenerationError) as e:
            last_error = e
            log.warning("Attempt %d/%d: failed to parse model output: %s", attempt, max_attempts, e)
            last_error_prompt = (
                f"Your previous response could not be parsed as valid JSON "
                f"matching the required schema. The parser error was:\n{e}\n\n"
                f"Reply again with ONLY the corrected JSON object - no markdown "
                f"fences, no other text."
            )
            continue

        word_count = sum(len(l.text.split()) for l in lines)
        log.info(
            "Parsed dialogue: %d lines, ~%d words (attempt %d/%d, target ~%d)",
            len(lines),
            word_count,
            attempt,
            max_attempts,
            config.TARGET_WORD_COUNT,
        )

        if word_count >= min_words or attempt == max_attempts:
            if word_count < min_words:
                log.warning(
                    "Final script is shorter than target (%d < %d words) after "
                    "%d attempts - using it anyway.",
                    word_count,
                    min_words,
                    max_attempts,
                )
            return lines

        last_error = f"only {word_count} words, target is ~{config.TARGET_WORD_COUNT}"
        log.warning(
            "Attempt %d/%d: script too short (%d words, need at least %d) - asking "
            "for an expanded version",
            attempt,
            max_attempts,
            word_count,
            min_words,
        )
        last_error_prompt = (
            f"That script was only about {word_count} words, but the target is "
            f"approximately {config.TARGET_WORD_COUNT} words. Please rewrite it, "
            f"substantially expanding the DEEP DIVE and ROUNDUP segments - more "
            f"back-and-forth between the hosts, more follow-up questions, more "
            f"concrete detail and examples, more discussion of implications - "
            f"while keeping the same papers and structure. Reply again with ONLY "
            f"the full corrected JSON object (not a diff or an excerpt) - no "
            f"markdown fences, no other text."
        )

    raise ScriptGenerationError(
        f"Failed to get an acceptable dialogue script after {max_attempts} attempts: {last_error}"
    )


if __name__ == "__main__":
    from datetime import date as date_cls

    from arxiv_podcast.fetch import fetch_recent_papers
    from arxiv_podcast.fulltext import fetch_full_texts
    from arxiv_podcast.score import load_interests, score_papers
    from arxiv_podcast.select import select_papers

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    papers = fetch_recent_papers()
    interests = load_interests()
    scores = score_papers(papers, interests) if interests else None
    deep, roundup, wildcard = select_papers(papers, scores)
    full_texts = fetch_full_texts(deep) if config.DEEP_DIVE_FULL_TEXT else None
    lines = generate_dialogue(
        deep, roundup, date_cls.today().isoformat(), wildcard=wildcard, full_texts=full_texts
    )

    print()
    for line in lines:
        who = config.HOST_A_NAME if line.speaker == "HOST_A" else config.HOST_B_NAME
        print(f"{who}: {line.text}\n")
    print(f"Total model cost this run: ${total_cost_usd():.4f}")
