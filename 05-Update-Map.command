#!/usr/bin/env bash
set -euo pipefail
trap 'echo "更新停止，請保留錯誤訊息。"; read -r -p "按 Enter 關閉"' ERR
[[ "$(uname -s)" == Darwin ]]
echo '請退出 JetLink，停止舊 HUD helper；本次同時更新 App 與模式 7 renderer。'
read -r -p '完成後按 Enter 更新'
BASE="$HOME/CarrotMacHUD"
mkdir -p "$BASE/overlay-releases"
RELEASE="$(mktemp -d "$BASE/overlay-releases/map-update.XXXXXX")"
git clone --depth 1 --branch feature/nav-map-hud https://github.com/FANHAOHSIANG/carrotMAC-HUD.git "$RELEASE/overlay"
"$BASE/carrot/.mac-hud-venv/bin/python" "$RELEASE/overlay/scripts/update_mac.py"
read -r -p '按 Enter 關閉'
