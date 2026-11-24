#!/bin/bash
set -euo pipefail
trap 'echo "測試停止：請保留上方錯誤訊息。"; read -r -p "按 Enter 關閉" _ || true' ERR
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/Library/Application Support/CarrotMacHUD/VLA-Offline"
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo "需要 Apple Silicon Mac"; exit 1; }
echo "請先退出 Jetlink、HUD，並拔除 C4 USB。"
read -r -p "確認已離線，按 Enter 繼續（Ctrl-C 取消）" _
if pgrep -x Jetlink >/dev/null; then echo "Jetlink 尚未退出，請退出後重開工具。"; exit 1; fi
MODE="$(osascript -e 'choose from list {"C4 原始紀錄資料夾", "已轉換的 frames.jsonl"} with prompt "選擇離線資料來源" default items {"C4 原始紀錄資料夾"}' -e 'result as text')"
[[ "$MODE" != false ]] || exit 0
if [[ "$MODE" == "C4 原始紀錄資料夾" ]]; then
  INPUT="$(osascript -e 'POSIX path of (choose folder with prompt "選擇含 rlog 與 fcamera.hevc 的單段資料夾")')" || exit 0
  [[ -f "$INPUT/fcamera.hevc" ]] || { echo "找不到 fcamera.hevc"; exit 1; }
  [[ -f "$INPUT/rlog" || -f "$INPUT/rlog.zst" || -f "$INPUT/rlog.bz2" ]] || { echo "找不到 rlog"; exit 1; }
else
  INPUT="$(osascript -e 'POSIX path of (choose file with prompt "選擇 frames.jsonl")')" || exit 0
fi
mkdir -p "$BASE"
RUN="$(mktemp -d "$BASE/run.XXXXXX")"
echo "結果資料夾：$RUN"
if [[ ! -x "$BASE/venv/bin/python" ]]; then python3 -m venv "$BASE/venv"; fi
PY="$BASE/venv/bin/python"
"$PY" -m pip install numpy opencv-python pycapnp zstandard
"$PY" -m unittest discover -s "$HERE" -p test_replay.py -v
if [[ "$MODE" == "C4 原始紀錄資料夾" ]]; then
  SCHEMA="$BASE/schema-b0ba1f13"
  PIN=b0ba1f13db3fbed94ea88c8b93cec488ef3c2b7f
  if [[ ! -d "$SCHEMA/.git" ]]; then
    git init "$SCHEMA"
    git -C "$SCHEMA" remote add origin https://github.com/TonyBinheWu/sunnypilot.git
  fi
  if [[ "$(git -C "$SCHEMA" rev-parse HEAD 2>/dev/null || true)" != "$PIN" ]]; then
    git -C "$SCHEMA" fetch --depth 1 origin "$PIN"
    git -C "$SCHEMA" sparse-checkout init --cone
    git -C "$SCHEMA" sparse-checkout set openpilot/cereal opendbc_repo
    git -C "$SCHEMA" checkout --detach FETCH_HEAD
  fi
  if [[ ! -f "$SCHEMA/opendbc_repo/opendbc/car/car.capnp" ]]; then
    git -C "$SCHEMA" submodule update --init --depth 1 opendbc_repo
  fi
  "$PY" "$HERE/export_segment.py" --segment "$INPUT" --schema-root "$SCHEMA" --output "$RUN/frames"
  INPUT="$RUN/frames/frames.jsonl"
fi
LLAMA="$BASE/llama-b12676"
SERVER="$LLAMA/build/bin/llama-server"
if [[ ! -x "$SERVER" ]]; then
  command -v cmake >/dev/null || { echo "缺少 CMake；請先執行 brew install cmake，再重開工具。"; exit 1; }
  if [[ ! -d "$LLAMA/.git" ]]; then
    git clone --depth 1 --branch b12676 https://github.com/ggml-org/llama.cpp.git "$LLAMA"
  fi
  git -C "$LLAMA" describe --tags --exact-match HEAD | grep -qx b12676
  cmake -S "$LLAMA" -B "$LLAMA/build" -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LLAMA/build" --target llama-server -j 4
fi
"$SERVER" --list-devices
echo "開始模型檢查／下載及離線推理（最多 13 張）..."
"$PY" -u "$HERE/replay.py" --offline-bench --server "$SERVER" --weights "$BASE/weights" --fetch --manifest "$INPUT" --max-frames 13 | tee "$RUN/results.partial.jsonl"
mv "$RUN/results.partial.jsonl" "$RUN/results.jsonl"
echo "完成：$RUN/results.jsonl"
open -R "$RUN/results.jsonl"
read -r -p "按 Enter 關閉" _
