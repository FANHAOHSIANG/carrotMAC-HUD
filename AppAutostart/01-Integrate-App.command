#!/usr/bin/env bash
set -euo pipefail
trap 'echo "更新停止，請保留錯誤訊息。"; read -r -p "按 Enter 關閉"' ERR
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/CarrotMacHUD"
[[ "$(uname -s)" == Darwin ]]
echo '更新前請退出 JetLink，並在舊 02-Start.command 視窗按 Ctrl-C。'
read -r -p '完成後按 Enter 開始更新'
xcodebuild -version
[[ -x "$BASE/carrot/.mac-hud-venv/bin/python" ]]
JETLINK_REV="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["jetlink_revision"])' "$HERE/../versions.json")"
[[ "$(git -C "$BASE/jetlink" rev-parse HEAD)" == "$JETLINK_REV" ]]
[[ "$(git -C "$BASE/carrot" rev-parse HEAD)" == a564ce1dc082909b1fdc73b72e64d920336b34d6 ]]
apply_patch() {
  local repo="$1" patch="$2"
  if git -C "$repo" apply --reverse --check "$patch" 2>/dev/null; then
    echo '更新已套用'
  else
    git -C "$repo" apply --check "$patch"
    git -C "$repo" apply "$patch"
  fi
}
# Validate both updates before changing either repository.
for item in jetlink carrot; do
  patch="$HERE/$item-autostart.patch"
  git -C "$BASE/$item" apply --reverse --check "$patch" 2>/dev/null || git -C "$BASE/$item" apply --check "$patch"
done
apply_patch "$BASE/jetlink" "$HERE/jetlink-autostart.patch"
apply_patch "$BASE/carrot" "$HERE/carrot-autostart.patch"
"$BASE/carrot/.mac-hud-venv/bin/python" "$BASE/carrot/tools/jetlink/mac_hud_supervisor.py" --help
make -C "$BASE/jetlink/macos" app
open "$BASE/jetlink/macos/build"
echo '更新完成！直接點這個資料夾內的 Jetlink.app；可拖到 Dock。'
echo '之後不用再執行 02-Start.command。App 的 Start server on launch 請保持開啟。'
read -r -p '按 Enter 關閉'
