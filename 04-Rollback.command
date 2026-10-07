#!/usr/bin/env bash
set -euo pipefail
trap 'echo "還原停止，請保留錯誤訊息。"; read -r -p "按 Enter 關閉"' ERR
HERE="$(cd "$(dirname "$0")" && pwd)"
read -r -p '退出 JetLink 後按 Enter，還原最近一次更新前的 App 與 helper'
"$HOME/CarrotMacHUD/carrot/.mac-hud-venv/bin/python" "$HERE/scripts/update_mac.py" --rollback
read -r -p '按 Enter 關閉'
