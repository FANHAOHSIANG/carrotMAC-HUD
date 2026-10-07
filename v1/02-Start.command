#!/usr/bin/env bash
set -euo pipefail
BASE="$HOME/CarrotMacHUD"
APP="$BASE/jetlink/macos/build/Jetlink.app"
[[ -d "$APP" ]] || { echo '請先執行 01-Install.command'; read -r; exit 1; }
echo '請確認原本下載的 JetLink 已結束，避免兩個版本同時開啟。'
echo '這個視窗執行 HUD helper；Ctrl-C 停止 HUD，JetLink App 繼續執行。'
open "$APP"
exec bash "$BASE/carrot/tools/jetlink/run_mac_hud.sh"
