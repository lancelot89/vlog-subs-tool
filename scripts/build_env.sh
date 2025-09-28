#!/usr/bin/env bash
# Build a relocatable Python runtime for distribution.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${1:-$ROOT_DIR/dist/AppRoot}"
ENV_DIR="$TARGET_DIR/env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
USE_UV="${USE_UV:-0}"

mkdir -p "$TARGET_DIR"

if [[ -d "$ENV_DIR" && "${FORCE_REBUILD:-0}" != "1" ]]; then
  echo "[INFO] Reusing existing environment at $ENV_DIR"
else
  echo "[INFO] Creating virtual environment at $ENV_DIR"
  rm -rf "$ENV_DIR"
  if [[ "$USE_UV" == "1" ]] && command -v uv >/dev/null 2>&1; then
    uv venv "$ENV_DIR"
  else
    "$PYTHON_BIN" -m venv "$ENV_DIR"
  fi
fi

# shellcheck disable=SC1091
source "$ENV_DIR/bin/activate"

pip install --upgrade pip wheel setuptools
pip install -r "$ROOT_DIR/requirements.txt"

python -m compileall "$ROOT_DIR/app" >/dev/null

deactivate

echo "[INFO] Environment ready at $ENV_DIR"
