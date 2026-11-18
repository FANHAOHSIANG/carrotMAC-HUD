#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash ./Update-HUD-Zh-TW.command
exec bash ./MacVision/Start-Mac-Vision.command
