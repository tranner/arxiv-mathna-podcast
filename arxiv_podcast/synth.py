"""Turn a dialogue script into a single mp3 using Piper TTS."""

import logging
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment

from arxiv_podcast import config
from arxiv_podcast.models import DialogueLine

log = logging.getLogger(__name__)

SPEAKER_VOICES = {
    "HOST_A": config.HOST_A_VOICE,
    "HOST_B": config.HOST_B_VOICE,
}


class SynthesisError(RuntimeError):
    pass


def _voice_paths(voice_name: str) -> tuple[Path, Path]:
    model_path = config.PIPER_VOICES_DIR / f"{voice_name}.onnx"
    config_path = config.PIPER_VOICES_DIR / f"{voice_name}.onnx.json"
    if not model_path.exists() or not config_path.exists():
        raise SynthesisError(
            f"Voice model '{voice_name}' not found in {config.PIPER_VOICES_DIR}. "
            f"Run scripts/setup_piper.sh first."
        )
    return model_path, config_path


def check_piper_available() -> None:
    if not config.PIPER_BIN.exists():
        raise SynthesisError(
            f"Piper binary not found at {config.PIPER_BIN}. Run scripts/setup_piper.sh first."
        )


def synthesize_line(text: str, voice_name: str, out_wav: Path) -> None:
    model_path, config_path = _voice_paths(voice_name)
    cmd = [
        str(config.PIPER_BIN),
        "--model",
        str(model_path),
        "--config",
        str(config_path),
        "--output_file",
        str(out_wav),
    ]
    proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0 or not out_wav.exists():
        raise SynthesisError(
            f"Piper failed synthesizing line (voice={voice_name}): {proc.stderr.strip()[:1000]}"
        )


def synthesize_episode(lines: list[DialogueLine], out_mp3: Path) -> float:
    """Synthesize each dialogue line, concatenate with turn-gap silence, and
    export a single mp3. Returns the episode duration in seconds."""
    check_piper_available()
    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.empty()
    gap = AudioSegment.silent(duration=config.TURN_GAP_MS)

    with tempfile.TemporaryDirectory(prefix="arxiv_podcast_synth_") as tmp:
        tmp_dir = Path(tmp)
        for i, line in enumerate(lines):
            voice_name = SPEAKER_VOICES.get(line.speaker)
            if voice_name is None:
                raise SynthesisError(f"No voice configured for speaker {line.speaker!r}")

            wav_path = tmp_dir / f"line_{i:04d}.wav"
            synthesize_line(line.text, voice_name, wav_path)
            segment = AudioSegment.from_wav(wav_path)

            combined += segment
            if i < len(lines) - 1:
                combined += gap

            if (i + 1) % 10 == 0 or i == len(lines) - 1:
                log.info("Synthesized %d/%d lines", i + 1, len(lines))

    duration_seconds = len(combined) / 1000.0
    log.info(
        "Exporting episode audio to %s (%.1f minutes, bitrate=%s)",
        out_mp3,
        duration_seconds / 60,
        config.AUDIO_BITRATE,
    )
    combined.export(
        out_mp3,
        format="mp3",
        bitrate=config.AUDIO_BITRATE,
        parameters=["-ac", "1"],  # mono, keeps file size down
    )
    return duration_seconds


if __name__ == "__main__":
    import sys
    from datetime import date as date_cls

    from arxiv_podcast.fetch import fetch_recent_papers
    from arxiv_podcast.script import generate_dialogue
    from arxiv_podcast.select import select_papers

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        # Quick check without calling the LLM: synthesize a two-line sample.
        lines = [
            DialogueLine("HOST_A", "Welcome to the numerical analysis daily digest."),
            DialogueLine("HOST_B", "Today we've got some great papers to talk about."),
        ]
    else:
        papers = fetch_recent_papers()
        deep, roundup = select_papers(papers)
        lines = generate_dialogue(deep, roundup, date_cls.today().isoformat())

    out_path = config.EPISODES_DIR / "smoke_test.mp3"
    duration = synthesize_episode(lines, out_path)
    print(f"\nWrote {out_path} ({duration / 60:.1f} minutes)")
