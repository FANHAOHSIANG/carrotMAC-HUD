#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
dest="$HOME/CarrotMacHUD/carrot/openpilot/selfdrive/carrot/cluster"
state="$HOME/Library/Application Support/CarrotMacVision"
mkdir -p "$state"
if [[ "${1:-}" == "--remove" ]]; then
  python3 login_agent.py --remove
  python3 install.py "$dest" --remove
  exit
fi
[[ -x "$state/env/bin/python" ]] || python3 -m venv "$state/env"
py="$state/env/bin/python"
if [[ ! -f "$state/deps-v1" ]]; then
  "$py" -m pip install 'ultralytics==8.4.114' onnxruntime
  touch "$state/deps-v1"
fi
src="$PWD"
cd "$state"
if ! echo '1d5f3cf69883e89ba6e2b3836a0b21623044e9a682f1f00dfbacac97b99baf94  cone.onnx' | shasum -a 256 -c - >/dev/null 2>&1; then
  curl -fL --retry 3 'https://raw.githubusercontent.com/FANHAOHSIANG/openpilot-carrot/e63ca079953b58bed02117914d060ac36e9a0f01/openpilot/selfdrive/carrot/web/vendor/road-detector/cone.onnx' -o cone.download
  echo '1d5f3cf69883e89ba6e2b3836a0b21623044e9a682f1f00dfbacac97b99baf94  cone.download' | shasum -a 256 -c -
  mv cone.download cone.onnx
fi
hash=9434014d541488e423e8b4d2f951d4151bf8ce24619a034e5ae988ad183f5ff7
if ! echo "$hash  crosswalk.onnx" | shasum -a 256 -c - >/dev/null 2>&1; then
  curl -fL --retry 3 'https://raw.githubusercontent.com/TonyBinheWu/sunnypilot/83b562a5f21596e81f7e2bd50b41aa7b75d2a796/openpilot/selfdrive/carrot/web/vendor/road-detector/crosswalk.onnx' -o crosswalk.download
  echo "$hash  crosswalk.download" | shasum -a 256 -c -
  mv crosswalk.download crosswalk.onnx
fi
if [[ "${1:-}" == "--autostart" ]]; then
  "$py" -c 'from ultralytics import YOLO; YOLO("yolo11n.pt")'
  "$py" "$src/install.py" "$dest"
  exec "$py" "$src/login_agent.py"
fi
if [[ $# == 0 ]]; then
  "$py" "$src/install.py" "$dest"
  echo '重新啟動 Jetlink／HUD helper，選擇有 3D 車道的模式。Ctrl-C 可停止辨識。'
fi
exec nice -n 10 "$py" "$src/vision.py" "$@"
