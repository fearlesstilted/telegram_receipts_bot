#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

LOCK_DIR="data/bot.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Bot already looks running from this project."
  echo "Stop the old terminal with Ctrl+C, or remove data/bot.lock if it is stale."
  exit 1
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

PYTHON_BIN=".venv311/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing .venv. Create it and install requirements first:"
  echo "python3.11 -m venv .venv"
  echo ".venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

export PYTHONPATH=src
export FLAGS_use_mkldnn=0
export FLAGS_use_onednn=0
export FLAGS_enable_pir_api=0
"$PYTHON_BIN" -m telegram_receipts_bot.main
