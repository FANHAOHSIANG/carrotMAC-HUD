# Mac 外接 HUD 立體物件測試版

停車時退出 Jetlink 與 HUD helper，解壓縮測試分支，開啟 Start-Mac-Vision.command。需要 Python 3.10 或更新、原有 CarrotMacHUD 與網路下載依賴及權重。保持終端機開啟，重新啟動 Jetlink，使用有 3D 車道的模式。道路預覽與相機校正都需要有效。物件出現於原有車道場景。Mac 以 CPU 執行 YOLO11n 和 Safety Cone 模型，首次載入可能較慢。

重播：在 Terminal 執行 bash Start-Mac-Vision.command --video /完整路徑/道路影片.mp4 --output /完整路徑/辨識預覽.mp4。輸出是標有辨識結果的影片。即時視窗左側顯示 USB ROAD 影像及辨識框，右側顯示更新率、延遲與 HUD 最近一次成功繪出的 3D 物件數。斑馬線會以 CROSSWALK 和條紋圖示顯示。按 Q 或 Esc，或用 Ctrl-C 停止即時辨識，退出 Jetlink 後執行 bash Start-Mac-Vision.command --remove 可移除 renderer 掛鉤。

目前使用前鏡頭預覽與平坦路面假設，立體圖形為類別示意，車頭方向未估算。測速與導航沿用原本 HUD。僅供顯示，低解析度、坡道及較遠的小物件可能誤判或漏判。尚待 M4／TURZX 實測。若安裝器提示找不到插入點，請保留原 renderer 版本與訊息。

[三角錐模型來源與授權說明](https://github.com/FANHAOHSIANG/openpilot-carrot/blob/e63ca079953b58bed02117914d060ac36e9a0f01/openpilot/selfdrive/carrot/web/vendor/road-detector/NOTICE.md) · [Ultralytics 模型](https://github.com/ultralytics/ultralytics)

也可以從解壓縮資料夾啟動 Carrot Vision.app。請將它與 Start-Mac-Vision.command 保存在同一資料夾。第一次會下載並驗證約 49 MB 的斑馬線模型。USB 接收仍由 Jetlink 提供。

[斑馬線模型來源、授權及限制](https://github.com/TonyBinheWu/sunnypilot/blob/83b562a5f21596e81f7e2bd50b41aa7b75d2a796/openpilot/selfdrive/carrot/web/vendor/road-detector/NOTICE.md)
