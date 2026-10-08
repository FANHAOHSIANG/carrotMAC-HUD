#!/usr/bin/env bash
set -euo pipefail
trap 'echo; echo "安裝停止，請保留此視窗的錯誤訊息。"; read -r -p "按 Enter 關閉"' ERR
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/CarrotMacHUD"
JETLINK_REV="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["jetlink_revision"])' "$HERE/../versions.json")"
CARROT_REV="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["carrot_revision"])' "$HERE/../versions.json")"
[[ "$(uname -s)" == Darwin ]] || { echo '需在 Mac 執行'; exit 1; }
command -v brew >/dev/null || { echo '請先安裝 Homebrew：https://brew.sh'; exit 1; }
xcodebuild -version
brew install xcodegen
mkdir -p "$BASE"
prepare_repo() {
  local directory="$1" remote="$2" revision="$3" patch="$4"
  if [[ ! -d "$directory" ]]; then
    mkdir -p "$directory"
    git -C "$directory" init
    git -C "$directory" remote add origin "$remote"
    git -C "$directory" fetch --depth 1 origin "$revision"
    git -C "$directory" checkout --detach FETCH_HEAD
  fi
  [[ "$(git -C "$directory" rev-parse HEAD)" == "$revision" ]] || {
    echo "版本不符：$directory。請改名保存這個資料夾，再重跑安裝。" >&2; return 1;
  }
  if git -C "$directory" apply --reverse --check "$patch" 2>/dev/null; then
    echo "補丁已套用：$directory"
  else
    git -C "$directory" apply --check "$patch"
    git -C "$directory" apply "$patch"
  fi
}
HUD_PATCH="$HERE/jetlink-mac-hud.patch"
PROTOCOL="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["protocol"])' "$HERE/../versions.json")"
if [[ "$PROTOCOL" == 3 ]]; then
  HUD_PATCH="$HERE/../overlays/protocol3/jetlink-mac-hud.patch"
fi
prepare_repo "$BASE/jetlink" https://github.com/zoompilot/jetlink.git "$JETLINK_REV" "$HUD_PATCH"
prepare_repo "$BASE/carrot" https://github.com/ajouatom/openpilot.git "$CARROT_REV" "$HERE/carrot-mac-helper.patch"
bash "$BASE/carrot/tools/jetlink/setup_mac_hud.sh"
# Compile the actual Swift package and extension tests before building the App.
export CARROT_HUD_DIR="$BASE/test-hud-runtime"
swift test --package-path "$BASE/jetlink/JetlinkKit" --filter CarrotHUDTests
unset CARROT_HUD_DIR
JETLINK_VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["jetlink_version"])' "$HERE/../versions.json")" make -C "$BASE/jetlink/macos" app
printf '\n安裝完成。先結束原本的 JetLink App，再執行 02-Start.command。\n'
read -r -p '按 Enter 關閉'
