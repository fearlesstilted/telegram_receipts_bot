#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

target="${1:-telegram_receipts_bot_release.zip}"
rm -f "$target"

zip -r "$target" . \
  -x ".git/*" \
  -x ".codex" \
  -x ".codex/*" \
  -x ".agents" \
  -x ".agents/*" \
  -x ".venv/*" \
  -x ".venv*/*" \
  -x "venv/*" \
  -x "env/*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x ".pytest_cache/*" \
  -x "data/*" \
  -x ".env" \
  -x "*.zip" \
  -x "*.log"

echo "Created $target"
