# hkg Jetlink HUD adapter

此分支配對：
https://github.com/FANHAOHSIANG/sunnypilot/tree/hkg-enhanced-jetlink-hud

這是第一版離線驗證候選，實體 C4/Mac/TURZX 與推論延遲待驗證。
只顯示行車資料、路徑、車道線、前車及狀態；不含相機或導航影像。

## 既有 CarrotMacHUD 安裝

1. 下載本 `hkg-jetlink-hud` 分支，退出 Jetlink App 與所有 HUD helper。
2. 在 Mac 執行 `06-HKG-HUD.command`；若下載後不能雙擊，可在該資料夾執行
   `bash 06-HKG-HUD.command`。
3. 工具要求 helper 基底為 `a564ce1dc082909b1fdc73b72e64d920336b34d6`，已有 Mac
   runtime/panel lock 適配，且既有 App 二進位包含 `carrot_hud_v1` receiver 標記。
   這是安裝前檢查，不代表實際通訊已成功。不同版本會停止，不會覆蓋 App。
4. 工具備份 supervisor 與 adapter／選擇標記，安裝 `hkg_hud.py` 並讓既有 App
   supervisor 選擇它。不替換 App，也不更改模型。
5. C4 切到配對測試分支並 offroad 啟用 HUD、重啟，再開啟原有 Jetlink App。

預設位置為 `~/CarrotMacHUD`。自訂位置可執行
`python3 scripts/enable_hkg.py --base /你的/CarrotMacHUD`，但 App 的原有啟動路徑
也必須已設定正確；此工具不修改 App 的 supervisor 路徑。

如果你目前使用官方 Jetlink App、沒有 HUD receiver，工具會停止。不要為了 HUD
直接把正在使用的 App 降級到舊版；需要取得該 App 的原始碼版本後再適配接收補丁。

## 還原

退出 App/helper 後：`python3 scripts/enable_hkg.py --rollback`。
這會還原安裝前的 helper 與選擇狀態；App 始終保持原檔案。
重複安裝前需先還原，避免覆蓋第一份備份。
測試期間不要執行原 `03-Update.command`，它不包含 hkg adapter 安裝流程。

## 資料保護與限制

- 接收既有 `0x4000` 顯示通道，以 `source=hkg_hud_v1` 區分。
- 新 sender 的 `events` 為空，另以有上限的 JSON 傳遞欄位。
  Mac 以屬性物件提供給舊 renderer，不解碼 hkg cereal bytes。
- 不增加 CAN／控制／參數回寫功能，不顯示未提供的相機／地圖。
- Mac 收到封包超過 0.5 秒後失效；不同 C4/Mac 開機時間透過本機接收時間換算。
- 來源缺失時清除 parser 中快取的路徑、前車與啟用狀態，保留最後的顯示設定。
- 現有 supervisor/panel lock 維持單一 TURZX 擁有者。

測試：`python3 -m unittest discover -s tests -p test_hkg.py -v`。
包含過期／錯誤來源／超大封包、接收時鐘、資料中斷復原、安裝失敗回復及完整還原。

若有 pinned Carrot helper 原始碼，可再執行實際 parser/live-source 測試：

```sh
CARROT_HELPER_ROOT="$HOME/CarrotMacHUD/carrot" python3 -m unittest discover -s tests -p test_hkg_renderer.py -v
```

本次 8 項 Mac 測試通過（含實際 parser/live-source 的資料失效清除與恢復）；
測試替代 messaging IPC，不執行 USB、GPU、H.264 輸出或車輛控制。
