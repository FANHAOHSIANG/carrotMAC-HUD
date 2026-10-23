# Jetlink / CommaView 整合實驗

目前只提供整合前檢查，不是可顯示 CommaView 的新版 App。

保留原本的 Jetlink App 執行，Mac 與 C4 連同一網路，雙擊
`08-CommaView-Check.command`，輸入 C4 設定 → 網路顯示的 IP。
檢查結果自動複製，可直接貼回對話。不必執行 03 或 06，也不必切換 C4 分支。

檢查只 GET 官方版本 API，讀取本機 App 標記及 HUD 封包／heartbeat。
不讀取認證金鑰、不建立或撤銷配對、不控制 USB、不改寫 C4 UI。
版本 API 可達不能證明配對、影像或疊圖可用。

## 接入位置與未完成部分

預定由既有 Jetlink App 啟動的 `mac_hud_supervisor.py` 管理新的顯示模式。
Carrotpilot / HKG 仍依封包自動辨識；CommaView 是另選的畫面模式，不能只靠
HKG 封包來源判斷是否應切換。切換時必須先停止舊 renderer 和 ffmpeg，釋放
panel lock，才啟動另一個輸出，並保留模型推論服務。

尚缺可驗證的 CommaView 客戶端協定：配對回覆和權杖生命週期、串流工作階段、
傳輸分框及可能的加密、影像格式／時間戳、telemetry 與畫面座標對齊。
取得規格後才可實作接收器、寬螢幕合成及切換入口。沒有加入無法使用的顯示按鈕。

## 本次查核依據

- 官方安裝文件：<https://commaview.com/docs/install>，目前提供 Android 客戶端。
- 官方 v0.0.59-beta installer：
  <https://commaview.com/commaviewd/v0.0.59-beta/comma/install.sh>，
  `wait_for_control_api` 使用 `http://127.0.0.1:5002/commaview/version`。
- 同版本官方發行包包含 ARM64 runtime、UI exporter、啟動腳本和依賴，
  沒有完整的 bridge/control 客戶端協定原始碼。
- 本次存取 `RhynoTech/commaviewd` 及 `CommaView/commaviewd` 均回傳 404；
  這不代表永久不可取得，也不代表已確認第三方客戶端支援。

尚未在使用者 Mac、C4 或 USB HUD 上驗證。本分支不更動既有 HUD 執行路徑。
