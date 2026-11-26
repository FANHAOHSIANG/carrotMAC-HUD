#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 MacVision/login_agent.py --remove
