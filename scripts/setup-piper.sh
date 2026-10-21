#!/usr/bin/env bash
# Clean E-yAy — Piper Türkçe yerel ses kurulumu (Mac/Linux).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$ROOT/data/models/piper"
VOICE="tr_TR-dfki-medium"
VOICE_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"
mkdir -p "$MODEL_DIR"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

PIPER=""
if [ -x "$ROOT/.venv/bin/piper" ]; then
  PIPER="$ROOT/.venv/bin/piper"
elif command -v piper >/dev/null 2>&1; then
  PIPER="$(command -v piper)"
else
  "$PYTHON" -m pip install piper-tts
  PIPER="$ROOT/.venv/bin/piper"
fi

download_if_missing() {
  url="$1"
  path="$2"
  if [ -s "$path" ]; then
    echo "Mevcut: $path"
    return
  fi
  echo "İndiriliyor: $url"
  curl -fL --retry 3 "$url" -o "$path"
  test "$(wc -c < "$path")" -ge 1024
}

download_if_missing "$VOICE_BASE/$VOICE.onnx" "$MODEL_DIR/$VOICE.onnx"
download_if_missing "$VOICE_BASE/$VOICE.onnx.json" "$MODEL_DIR/$VOICE.onnx.json"

ENV_FILE="$ROOT/.env"
if [ ! -e "$ENV_FILE" ]; then
  if [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ENV_FILE"
  else
    : > "$ENV_FILE"
  fi
fi
set_env() {
  name="$1"
  value="$2"
  if grep -q "^${name}=" "$ENV_FILE"; then
    sed -i.bak "s|^${name}=.*|${name}=${value}|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    printf '\n%s=%s\n' "$name" "$value" >> "$ENV_FILE"
  fi
}
set_env TTS_PROVIDER piper
set_env PIPER_MODEL "data/models/piper/$VOICE.onnx"

echo "Piper hazır: $PIPER"
echo "Model hazır: $MODEL_DIR/$VOICE.onnx"
