#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then echo "需要 Apple Silicon Mac"; exit 1; fi
if pgrep -ix Jetlink >/dev/null || pgrep -ix CarrotMacHUD >/dev/null; then echo "請先退出 Jetlink/HUD"; exit 1; fi
echo "僅離線研究。請停車、拔除 C4 USB，並退出 Jetlink/HUD。"
read -r -p "已確認？輸入 OFFLINE 繼續: " confirm
[[ "$confirm" == OFFLINE ]] || exit 1
segment=""
if [[ $# -gt 0 ]]; then segment="$1"; fi
if [[ -z "$segment" ]]; then
  read -r -p "請輸入完整本機雙鏡頭 segment 資料夾（不要加引號）: " segment
fi
[[ -d "$segment" ]] || { echo "找不到資料夾"; exit 1; }
for f in rlog.zst fcamera.hevc ecamera.hevc; do
  [[ -f "$segment/$f" ]] || { echo "缺少 $f"; exit 1; }
done
base="$HOME/Library/Application Support/CarrotMacHUD/Alpamayo-MLX-Offline"
mkdir -p "$base"
if ! command -v python3.12 >/dev/null; then echo "請先安裝 Python 3.12"; exit 1; fi
venv="$base/venv"
if [[ ! -x "$venv/bin/python" ]]; then python3.12 -m venv "$venv"; fi
py="$venv/bin/python"
"$py" -m pip install numpy scipy av pycapnp zstandard huggingface_hub
"$py" -m pip install 'git+https://github.com/SMJD11/mlx-vla.git@43893667449fd5cdc621a8c8da3624ce014f202f'
"$py" -m unittest discover -s tools/alpamayo-mlx -p 'test_*.py' -v
tony="$base/tony-source"
if [[ ! -d "$tony/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/TonyBinheWu/sunnypilot.git "$tony"
  git -C "$tony" checkout --detach 980a186d4b63d6f0a62ab2b487dbdfe3f2939127
fi
if [[ ! -f "$tony/opendbc_repo/opendbc/car/car.capnp" ]]; then
  git -C "$tony" submodule update --init opendbc_repo
fi
run="$(mktemp -d "$base/run.XXXXXX")"
"$py" tools/alpamayo-mlx/export_segment.py --segment "$segment" --tony-root "$tony" --output "$run/samples"
"$py" tools/alpamayo-mlx/replay.py --offline-bench --samples "$run/samples" --output "$run/results"
echo "完成離線研究：$run/results"
open "$run/results"
