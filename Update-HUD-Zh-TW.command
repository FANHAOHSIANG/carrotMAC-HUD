#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HOME/CarrotMacHUD/carrot/.mac-hud-venv/bin/python"
if [[ "$(uname -s)" != Darwin || ! -x "$PYTHON" ]]; then
  echo '請在已安裝 CarrotMacHUD 的 Mac 執行。' >&2
  exit 1
fi
echo '請先退出 Jetlink App。若用 Terminal 啟動 HUD helper，也請將它停止。'
"$PYTHON" "$HERE/scripts/update_hud_locale.py" "$@"
