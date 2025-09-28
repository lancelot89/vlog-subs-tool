#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/env/bin/python"
LOG_DIR="${LOG_DIR_OVERRIDE:-$HOME/Library/Logs/vlog-subs-tool}"
if [[ "$(uname -s)" != "Darwin" ]]; then
  LOG_DIR="${LOG_DIR_OVERRIDE:-$HOME/.local/state/vlog-subs-tool/logs}"
fi
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/launch.log"
if [[ ! -x "$PY" ]]; then
  echo "[ERROR] 同梱Pythonが見つかりません: $PY" | tee -a "$LOG_FILE"
  echo "[HINT] README_start_here.md のトラブルシューティングを参照してください。" | tee -a "$LOG_FILE"
  exit 1
fi
{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Launching VLog Subs Tool"
  "$PY" -m app.main "$@"
} 2>&1 | tee -a "$LOG_FILE"
