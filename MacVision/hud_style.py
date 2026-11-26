"""Mac-specific HUD appearance, loaded once when the HUD helper starts."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

CONFIG = Path.home() / "Library/Application Support/CarrotMacVision/appearance.json"
STYLES = ("factory", "night", "large")


def load():
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    style = data.get("style")
    return (style if style in STYLES else "factory",
            data.get("arrows") is True, data.get("limit") is not False)


STYLE, SHOW_ARROWS, SHOW_LIMIT = load()


if __name__ == "__main__":
    def select(prompt, choices, current):
        while True:
            answer = input(f"{prompt} [Enter 保留 {current}]：").strip() or current
            if answer in choices:
                return answer
            print("請輸入選項中的數字。")

    number = select("車模  1 原廠像素  2 夜間黑鑽  3 大燈號", ("1", "2", "3"), str(STYLES.index(STYLE) + 1))
    arrows = select("懸浮方向箭頭  1 顯示  0 隱藏", ("0", "1"), str(int(SHOW_ARROWS)))
    limit = select("速限圓牌  1 顯示  0 隱藏", ("0", "1"), str(int(SHOW_LIMIT)))
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=CONFIG.parent, delete=False) as output:
        json.dump(dict(style=STYLES[int(number)-1], arrows=arrows=="1", limit=limit=="1"), output)
    Path(output.name).replace(CONFIG)
    print("已儲存，下次開啟 Jetlink／HUD helper 生效。")
