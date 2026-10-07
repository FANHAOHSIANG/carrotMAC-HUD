# carrotMAC-HUD

CarrotPilot → Mac JetLink → TURZX HUD。這裡管理可閱讀的 HUD 原始碼補丁、Mac 更新腳本與官方更新檢查，不需要另外建立名為 jetlink 的 Fork。

## 目前可用配對

- JetLink：`51ffd10825d9704f21293dc51d08244e8af86197`
- Carrot helper：`a564ce1dc082909b1fdc73b72e64d920336b34d6`
- 通訊協定：**protocol 2**，版本記錄於 [versions.json](versions.json)。
- 使用者已確認 v1 在 Mac/C4/TURZX 有畫面；新增 App 自動啟動已通過雲端 Mac 編譯，仍需本機確認 HUD 啟動與退出。
- 官方目前使用 protocol 3，**尚未適配**。更新檢查遇到差異會 blocked，保留以上版本；不是修改協定數字就能相容。

## 已裝過 v1：更新 App 與 HUD

1. Windows 或 Mac 都可在本頁選 **Code → Download ZIP**，解壓縮。
2. 在 **Mac** 退出 JetLink，停止舊 `02-Start.command` 視窗中的 helper。
3. 執行根目錄 **03-Update.command**。它會抓本 repository 的 main，再依 versions.json 下載官方固定版本、套用 HUD 和 App 啟動補丁、執行 Swift HUD 測試並编譯。
4. 成功後才替換原本 `~/CarrotMacHUD/jetlink/macos/build/Jetlink.app`，並備份 App/helper。之後直接點修改版 App；保持 **Start server on launch** 開啟。
5. 需要還原時，在退出 App 後執行 **04-Rollback.command**。

保留完整 Xcode、Homebrew 與現有 Python HUD 環境。雲端已用 Xcode 26.6 驗證；若本機出現 Swift typed throws 編譯錯誤，請先更新 Xcode 並選取完整 Xcode 開發目錄。此流程不更新 C4，不更換模型；C4 與 Mac 的實際通訊版本仍須配對。來源與備份會留在 ~/CarrotMacHUD，請管理磁碟空間。

第一次安裝可執行 [v1/01-Install.command](v1/01-Install.command)，再執行根目錄 03-Update.command。
[AppAutostart](AppAutostart) 保留獨立啟動整合補丁；原本 ZIP 也保留。

## 在 Windows 網頁檢查官方更新

打開 **Actions → Check official JetLink updates → Run workflow**：

- `upstream_ref = main`：檢查官方最新版。
- 填入 versions.json 的 JetLink SHA：驗證目前固定版的補丁與 Mac 編譯。
- 每天也會檢查官方 main，結果與原因在 workflow Summary 與 compatibility-report artifact。
- 檢查不相容時標示 **Update blocked; current version retained**。這表示檢查完成，**不是已同步**；Mac build 會跳過。
- 協定及補丁通過才在 GitHub 的 Apple Silicon Mac runner 編譯、簽名驗證，產生 **Jetlink-HUD-candidate** artifact。ZIP 是 ad hoc 簽名的候選 App，未公證，並且需要本機 HUD Python 環境；不能當成正式實機驗收。
- 候選基準和現有版本不同時會提出更新 versions.json 的 PR；**不自動合併**。先驗證 C4 模型、TURZX 畫面與退出清理，再合併，Mac 執行 03-Update.command 才安裝。

若 Actions 尚未允許執行，按 GitHub 顯示的啟用按鈕。若建立 PR 被 repository 政策擋下，檢查 **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests**；不需設定 PAT 或把密碼寫進程式碼。若你想保留禁用設定，也可自行提交 versions.json 更新。

## 維護方式

HUD 傳輸補丁在 v1/jetlink-mac-hud.patch；App 啟動補丁在 AppAutostart/jetlink-autostart.patch；
helper 原始碼在 AppAutostart/mac_hud_supervisor.py。官方更新導致衝突時，需要先修補這些差異並更新測試。
這是「官方原始碼＋HUD overlay」流程，保留原始碼歷史與目前安裝，不會強制 reset 你的 Mac checkout。

[雲端驗證已通過](https://github.com/FANHAOHSIANG/carrotMAC-HUD/actions/runs/37659804608)：6 項 Python 測試、補丁套用、2 項 Swift HUD 測試、Apple Silicon App 編譯及 ad hoc 簽名驗證（macOS 26／Xcode 26.6）。C4/TURZX 的新版自動啟動、退出清理與推論延遲仍需本機實測。
授權沿用各 upstream；本 repository 不包含模型權重。

<details>
<summary>原本 v1 說明（保留歷史，啟動與更新方式請以以上為準）</summary>

# carrotMAC-HUD
carrotpilot jetlink&HUD for MAC
CarrotPilot → Mac JetLink → TURZX HUD 移植版 v1
這是可套用的原始碼補丁與安裝工具，已在 Mac/C4/TURZX 實機驗證，不是已簽署的 DMG。安裝時會在你的 Mac 編譯 JetLink。
接線與執行方式
C4 Port 2 → USB 3 資料線 → Mac mini。
TURZX 1CBE:0092 → Mac 的另一個 USB 接口。
修改版 JetLink App 負責大模型推論與接收 HUD；Python helper 負責沿用 Carrot renderer、H.264 編碼及 TURZX 輸出。
C4 與 Mac 之間全部走原本 JetLink USB。導航媒體在 Mac 內使用 127.0.0.1:47741 UDP IPC，不需要 Wi-Fi，也不是 C4 的 JetLink port。
必要條件
Apple Silicon Mac、macOS 15 以上、完整 Xcode（Swift 6.2 或更新）、Homebrew。若 Xcode 第一次開啟要求安裝元件或接受授權，先完成。你的 CarrotPilot 必須有 `carrot_hud_v1` sender。
版本配對非常重要： 本版以提供的 Carrot commit `a564ce1dc082909b1fdc73b72e64d920336b34d6` 與 JetLink `51ffd10825d9704f21293dc51d08244e8af86197` 為基準。兩者都是 protocol 2，已比對 header、message IDs、flags、推論封包 layout 與 USB padding 常數。最新 JetLink main/v0.8.3 是 protocol 3，不能直接拿來配這個 Carrot commit。不要只更改版本數字。
在 Mac 安裝
解壓縮 ZIP，放在 Downloads 或桌面。
先確認 Homebrew 已安裝，Xcode 能正常開啟。
雙擊 `01-Install.command`。它會建立 `~/CarrotMacHUD`，下載上述固定版本、套用補丁、安裝 HUD 依賴、執行 Swift HUD 測試，再編譯 App。下載 ONNX Runtime/Xcode 依賴可能需要較長時間。
如果 macOS 不允許雙擊，開 Terminal 輸入 `bash `（後面留一個空格），把 `01-Install.command` 拖入視窗，再按 Enter。兩個後續 .command 也可用相同方式。
安裝中發生錯誤會停下；不要繼續到啟動步驟。保留 Terminal 錯誤訊息即可定位問題。此環境未跑過 Mac 的 Swift build，因此這一步的通過是使用前必要的驗證。
原始碼放在獨立資料夾，不覆蓋你的其他 checkout 或 Applications 中的舊 App。重跑時只接受指定版本，已套用的補丁會跳過；不會強制 reset 既有改動。
第一次啟動
結束原本下載的 JetLink App，避免同時占用 C4。
雙擊 `02-Start.command`，它會開啟修改版 JetLink App，並在 Terminal 執行 HUD helper。先維持 Mac 登入桌面、電源接妥且不睡眠。
在修改版 App 選用 CoreML/ANE 模式；Carrot 的這個版本只辨識符合 Mac peer 條件的 ORT/CoreML 裝置。等待 C4 大模型模型下載/準備/連線完成。模型選擇與推論流程由原本 CarrotPilot 和 JetLink 管理，本補丁沒有重寫模型。
HUD helper 會等待車輛 onroad 或 `ClusterHudDebug >= 1`，以及 TURZX 接上。熄火且 debug=0 時會結束顯示；需要時 launcher 會重新啟動 helper。`ClusterHud=0` 不會禁止 Mac 上的 HUD。
`03-Check.command` 會連續五秒顯示封包新鮮度與 USB 輸出 heartbeat。封包年齡應小於 0.5 秒、output heartbeat 小於 3 秒。
先停車測試：確認速度/ACC/導航資料更新、拔掉 TURZX 後大模型仍正常、停止 helper 後 App 仍正常、重新插入後能恢復。Big Model 連線成功與 HUD 成功是兩個獨立檢查，不可只看綠色圖示。
如果這個基底版本的 App 出現官方更新選項，關閉自動下載/安裝，避免官方 App 替換這個客製 build。
C4 端：道路攝影機 preview 的小補丁
基本速度、ACC、車道、導航狀態與導航媒體 sender 已存在，不需重寫。`a564ce1d` 的道路攝影機 preview 啟動條件卻只認 `jetSON` heartbeat；要讓 Mac HUD 在 `ClusterHud=0` 時也能取得 preview，需套用 `c4-camera-heartbeat.patch`，僅把允許的 host label 加上 `MAC`。
Mac 的 helper 原始碼補丁已包含這一行，但 Mac 的檔案不會自動更新 C4。將單獨的 `c4-camera-heartbeat.patch` 複製到 C4，在 `/data/openpilot` 執行：
```bash
git apply --check /path/to/c4-camera-heartbeat.patch
git apply /path/to/c4-camera-heartbeat.patch
```
`/path/to/` 換成你實際複製的位置。先停車處理，套用後重啟軟體或 C4。若 check 失敗，表示 C4 版本已有變動或已包含修正，應核對原始碼；不要強行覆蓋。這裡沒有遠端登入你的 C4，也沒有幫它刷機或推到 ajouatom 的分支。
本版涵蓋範圍
HELLO 宣告 `carrot_hud_v1`、`carrot_navi_v1`、`carrot_host=mac`。
接收 `0x4000` snapshot 與 `0x4001` 導航碎片，保留 upstream Wire enum。
HUD snapshot 背景驗證/原子替換，最多一個待處理 snapshot，過期資料會丟棄；HUD 處理不回覆額外協定訊息。
Mac 專用 IPC 路徑、跨 Swift/Python 的時鐘換算、導航碎片排序/丟包防護。
Carrot 既有 renderer、USB driver、libx264 H.264、10 FPS 啟動參數、熄火/debug/亮度/版面設定。
真實 USB 輸出 heartbeat 從 helper 回傳給 JetLink，再回 C4。helper 停止後回報會過期。
Mac helper 使用獨立 panel lock；一個 JetLink session 持有 HUD extension。
Mac 溫度讀取/Jetson 過熱門檻沒有移植；本版使用 Carrot 原有 MAC badge，不把 Mac 假裝成 Jetson。也尚未把 helper 嵌入 App bundle；目前用 `02-Start.command` 同時啟動兩者。顯示編碼/render 仍會與推論共用 Mac 資源，是否影響模型延遲需要實機量測，不能保證零影響。
驗證結果與限制
Python 封包、時鐘、導航 IPC/碎片缺失、資料過期、斷線 invalidation、HUD switch/ignition、Mac/Jetson camera heartbeat 等 36 項測試通過。
Carrot helper 全部依賴安裝後的 `--help` import/CLI 載入通過；腳本語法與補丁 whitespace 檢查通過。
两端 protocol 2 常數/message IDs/flags/inference layout 比對通過。
沒有 Mac SDK/Swift 編譯器、實體 C4、Mac mini 或 TURZX 可用；Swift tests 已附上，但未在此執行。Mac 編譯、raylib/OpenGL 顯示、TURZX 的 macOS libusb 權限、真實 H.264 畫面與推論延遲都尚未驗證。
尚未發布成 DMG，也未修改你的 Mac、C4 或遠端 repo。此檔案是完整的移植候選版本，不能當成已完成實機驗收。
移除與復原
退出修改版 App，關閉 HUD Terminal，再開原本的 JetLink 即可回復舊 Mac 端。若 C4 套過小補丁，可在同一個 checkout 用 `git apply --reverse --check` 後再 `git apply --reverse` 復原該補丁。
原始碼基準
https://github.com/ajouatom/openpilot/commit/a564ce1dc082909b1fdc73b72e64d920336b34d6
https://github.com/zoompilot/jetlink/commit/51ffd10825d9704f21293dc51d08244e8af86197
補丁套用後的原始碼仍依各 upstream 專案的授權；安裝工具沒有攜帶模型權重。

</details>

