#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo '請在 Mac 執行。' >&2; exit 1; }
BASE="$HOME/CarrotMacHUD"
PYTHON="$BASE/carrot/.mac-hud-venv/bin/python"
[[ -x "$PYTHON" ]] || { echo '找不到既有 Mac HUD Python 環境。' >&2; exit 1; }
mkdir -p "$BASE/overlay-releases"
RELEASE="$(mktemp -d "$BASE/overlay-releases/jetlink-0812.XXXXXX")"
git clone --depth 1 --branch fix/mac-nav-preview-20261102 https://github.com/FANHAOHSIANG/carrotMAC-HUD.git "$RELEASE/overlay"
"$PYTHON" "$RELEASE/overlay/scripts/update_mac.py"
