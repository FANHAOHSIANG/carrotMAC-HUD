#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo '請在 Mac 執行。' >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HOME/CarrotMacHUD/carrot/.mac-hud-venv/bin/python"
[[ -x "$PYTHON" ]] || { echo '找不到既有 Mac HUD Python 環境。' >&2; exit 1; }
"$PYTHON" "$ROOT/scripts/install_nav_preview.py" "$@"
