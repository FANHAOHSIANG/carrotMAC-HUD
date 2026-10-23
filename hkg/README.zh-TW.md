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
   runtime/panel lock 適配。既有 App 需含 `carrot_hud_v1`，或同時含 receiver 的
   `CarrotHUD` 與 `carrot-hud-writer` 標記；兩條路徑都需有 `mac_hud_supervisor.py` 自動啟動標記。
   這是靜態安裝前檢查，不代表實際通訊已成功；仍由 C4 hello 回覆的 HUD capability 決定是否傳送。
   檢查不通過會停止，不會覆蓋 App。
4. 工具備份 supervisor 與 adapter／選擇標記，安裝 `hkg_hud.py` 並讓既有 App
   supervisor 選擇它。不替換 App，也不更改模型。
5. C4 使用配對分支 `d248f42d7` 或含該修正的後續版本，offroad 開啟 HUD，
   再開啟原有 Jetlink App。首次更新 C4 程式需重啟一次，其後 HUD 開關無須重啟。

預設位置為 `~/CarrotMacHUD`。自訂位置可執行
`python3 scripts/enable_hkg.py --base /你的/CarrotMacHUD`，但 App 的原有啟動路徑
也必須已設定正確；此工具不修改 App 的 supervisor 路徑。

如果你目前使用官方 Jetlink App、沒有 HUD receiver，工具會停止。不要為了 HUD
直接把正在使用的 App 降級到舊版；需要取得該 App 的原始碼版本後再適配接收補丁。

### 0.8.7 App 被舊安裝器誤擋（2026-10-24）

使用者的 0.8.7 App 含 receiver class、writer thread 與 supervisor 標記，
但沒有連續的 `carrot_hud_v1` 字串，舊版因此停止。新版改用上述組合檢查，
可沿用既有 App，無須重新編譯或降級。重新下載本分支後執行 `06-HKG-HUD.command`。
安裝完成應顯示「hkg HUD adapter 已安裝」。只看到「程序完成」不表示安裝成功。
本機 jetlink 原始碼的 Git HEAD 可能與後來複製進去的 App 版本不同，不能用它判定已安裝 App 的版本。

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

安裝檢查修正後 9 項 `test_hkg.py` 測試通過，新增缺少 capability 字串但 receiver/autostart
標記完整的安裝／還原測試，以及部分標記不足時保持原檔的測試。二進位樣本為合成資料，
尚未讀取使用者實際 App，也沒有在 Mac 執行安裝。
先前 parser/live-source 測試已驗證資料失效清除與恢復；本次沒有修改 renderer。
測試不執行 USB、GPU、H.264 輸出或車輛控制。
