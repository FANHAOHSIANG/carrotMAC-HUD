CarrotMacHUD：Protocol 3 與 App 自動啟動更新

01-Integrate-App.command 現在轉交根目錄 03-Update.command，使用隔離編譯、備份及還原流程。
更新前退出 JetLink、停止舊 HUD helper，並確認 C4 已包含 commit
034581414fa57fb20738a47238d1f8b266fa38d3。

本工具把 Mac App 升級到 Protocol 3，不會更新 C4，不會自動選擇新模型。
Mac 的 Python 顯示 helper 保留原本版本和環境；它不負責 C4 的模型協定。
完成後點原本位置的修改版 Jetlink.app，保持 Start server on launch 開啟。
要换模型，在熄火狀態按 Use Model，等下載、引擎準備和 C4 驗證完成。

完整版本配對、C4 攝影機補丁、還原與驗證限制請見根目錄 README.md。
舊 jetlink-autostart.patch 僅供 Protocol 2 歷史版本，不套用到 Protocol 3。
