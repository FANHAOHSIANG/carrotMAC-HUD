#!/usr/bin/env bash
set -euo pipefail
BASE="$HOME/CarrotMacHUD"
export PYTHONPATH="$BASE/carrot"
"$BASE/carrot/.mac-hud-venv/bin/python" "$(dirname "$0")/check_hud.py"
read -r -p '按 Enter 關閉'
