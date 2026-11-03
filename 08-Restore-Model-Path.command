#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$HOME/CarrotMacHUD/carrot/.mac-hud-venv/bin/python" "$ROOT/scripts/install_model_path.py" "$@"
