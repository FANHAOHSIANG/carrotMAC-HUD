CarrotMacHUD：App 自動啟動 HUD 更新包

適用於已成功安裝 CarrotMacHUD-v1 的 Mac。
1. 退出 JetLink，在舊 02-Start.command 的 Terminal 視窗按 Ctrl-C。
2. 解壓縮本包，雙擊 01-Integrate-App.command，按 Enter 開始。
3. 編譯完成會開啟 build 資料夾。將其中 Jetlink.app 拖到 Dock。
4. 之後點這個修改版 Jetlink.app 即可，HUD 在背景啟動，不必再開 02-Start.command。
   App 的 Start server on launch 設定須開啟；手動 Start Server 也會啟動 HUD。

退出 App 或停止 Server 會停止 HUD。HUD 程序正常退出或發生錯誤後會重試，
方便車輛再次連線。這仍須 C4、Mac 與 TURZX USB 連線正常。
HUD 記錄：~/Library/Logs/CarrotMacHUD/hud.log

此更新只整合啟動，不更新 JetLink 通訊協定或模型，不重裝 Python 套件。
請使用本次編譯的 App，原版／其他下載的 JetLink 不會自動啟動此 HUD。
安裝器不清除現有程式碼；版本不符或補丁衝突會停止並留下錯誤訊息。

驗證：背景 supervisor 的重新啟動、單實例鎖、App 消失時 renderer/encoder 清理
已在 Linux 通過。Swift App 須由安裝器在你的 Mac 上使用 Xcode 編譯驗證；
本更新尚未在實體 Mac/C4/TURZX 上測試。
