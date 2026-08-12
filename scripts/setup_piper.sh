#!/usr/bin/env bash
# Downloads the Piper TTS binary and the two voice models used for the two
# podcast hosts into ./piper/. Safe to re-run - skips anything already present.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPER_DIR="$REPO_ROOT/piper"
VOICES_DIR="$PIPER_DIR/voices"
PIPER_VERSION="2023.11.14-2"

# Defaults must match HOST_A_VOICE/HOST_B_VOICE in arxiv_podcast/config.py.
HOST_A_VOICE="${HOST_A_VOICE:-en_GB-jenny_dioco-medium}"
HOST_B_VOICE="${HOST_B_VOICE:-en_GB-cori-high}"

mkdir -p "$PIPER_DIR" "$VOICES_DIR"

# --- Detect platform/arch and pick the matching Piper release asset --------
os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
  Linux)
    case "$arch" in
      x86_64) asset="piper_linux_x86_64.tar.gz" ;;
      aarch64|arm64) asset="piper_linux_aarch64.tar.gz" ;;
      armv7l) asset="piper_linux_armv7l.tar.gz" ;;
      *) echo "Unsupported Linux arch: $arch" >&2; exit 1 ;;
    esac
    ;;
  Darwin)
    case "$arch" in
      arm64) asset="piper_macos_aarch64.tar.gz" ;;
      x86_64) asset="piper_macos_x64.tar.gz" ;;
      *) echo "Unsupported macOS arch: $arch" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $os (Piper releases only cover Linux and macOS)" >&2
    exit 1
    ;;
esac

# --- Piper binary ------------------------------------------------------------
if [ -x "$PIPER_DIR/piper/piper" ]; then
  echo "Piper binary already present at $PIPER_DIR/piper/piper - skipping download."
else
  url="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/${asset}"
  echo "Downloading Piper ($asset) from $url ..."
  curl -fsSL "$url" -o "$PIPER_DIR/piper.tar.gz"
  tar -xzf "$PIPER_DIR/piper.tar.gz" -C "$PIPER_DIR"
  rm "$PIPER_DIR/piper.tar.gz"
  chmod +x "$PIPER_DIR/piper/piper"
  echo "Piper binary installed at $PIPER_DIR/piper/piper"
fi

# --- Voice models --------------------------------------------------------------
download_voice() {
  local voice="$1"
  local model_path="$VOICES_DIR/${voice}.onnx"
  local config_path="$VOICES_DIR/${voice}.onnx.json"

  if [ -f "$model_path" ] && [ -f "$config_path" ]; then
    echo "Voice '$voice' already present - skipping."
    return
  fi

  # Voice repo layout: en/<locale>/<name>/<quality>/<locale>-<name>-<quality>.onnx[.json]
  # e.g. en_GB-jenny_dioco-medium -> en/en_GB/jenny_dioco/medium/...
  local locale="${voice%%-*}"           # en_GB
  local rest="${voice#"$locale"-}"      # jenny_dioco-medium
  local quality="${rest##*-}"           # medium
  local name="${rest%-"$quality"}"      # jenny_dioco
  local base_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/${locale}/${name}/${quality}/${voice}"

  echo "Downloading voice '$voice' ..."
  curl -fsSL "${base_url}.onnx" -o "$model_path"
  curl -fsSL "${base_url}.onnx.json" -o "$config_path"
  echo "Voice '$voice' installed."
}

download_voice "$HOST_A_VOICE"
download_voice "$HOST_B_VOICE"

echo ""
echo "Piper setup complete."
echo "  Binary: $PIPER_DIR/piper/piper"
echo "  Voices: $VOICES_DIR"
