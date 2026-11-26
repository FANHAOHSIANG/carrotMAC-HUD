# Mac 外接 HUD 立體物件測試版

Mac 第一次設定時先停止舊版辨識、退出 Jetlink，再雙擊根目錄的 `Start-IONIQ5-HUD.command`。完成後開啟 Jetlink。之後登入同一 macOS 帳號時，Mac Vision 會在背景等待 ROAD 影像。安裝後可移動下載資料夾。最近的解析度、幀率與 HUD 回報記錄在 `~/Library/Application Support/CarrotMacVision/worker.log`。執行根目錄的 `Disable-Mac-Vision-Autostart.command` 可立即停止背景辨識並取消登入啟動。

需要即時預覽視窗時，先停用背景辨識。停車時退出 Jetlink 與 HUD helper，解壓縮測試分支，開啟 Start-Mac-Vision.command。需要 Python 3.10 或更新、原有 CarrotMacHUD 與網路下載依賴及權重。保持終端機開啟，重新啟動 Jetlink，使用有 3D 車道的模式。道路預覽與相機校正都需要有效。物件出現於原有車道場景。Mac 以 CPU 執行 YOLO11n 和 Safety Cone 模型，首次載入可能較慢。

重播：在 Terminal 執行 bash Start-Mac-Vision.command --video /完整路徑/道路影片.mp4 --output /完整路徑/辨識預覽.mp4。輸出是標有辨識結果的影片。即時視窗左側顯示 USB ROAD 影像及辨識框，右側顯示更新率、延遲與 HUD 最近一次成功繪出的 3D 物件數。斑馬線會以 CROSSWALK 和條紋圖示顯示。按 Q 或 Esc，或用 Ctrl-C 停止即時辨識，退出 Jetlink 後執行 bash Start-Mac-Vision.command --remove 可移除 renderer 掛鉤。

目前使用前鏡頭預覽與平坦路面假設，立體圖形為類別示意，車頭方向未估算。測速與導航沿用原本 HUD。僅供顯示，低解析度、坡道及較遠的小物件可能誤判或漏判。尚待 M4／TURZX 實測。若安裝器提示找不到插入點，請保留原 renderer 版本與訊息。

[三角錐模型來源與授權說明](https://github.com/FANHAOHSIANG/openpilot-carrot/blob/e63ca079953b58bed02117914d060ac36e9a0f01/openpilot/selfdrive/carrot/web/vendor/road-detector/NOTICE.md) · [Ultralytics 模型](https://github.com/ultralytics/ultralytics)

也可以從解壓縮資料夾啟動 Carrot Vision.app。請將它與 Start-Mac-Vision.command 保存在同一資料夾。第一次會下載並驗證約 49 MB 的斑馬線模型。USB 接收仍由 Jetlink 提供。

[斑馬線模型來源、授權及限制](https://github.com/TonyBinheWu/sunnypilot/blob/83b562a5f21596e81f7e2bd50b41aa7b75d2a796/openpilot/selfdrive/carrot/web/vendor/road-detector/NOTICE.md)

### 自車尾燈

退出 Jetlink，執行本版 `Start-Mac-Vision.command` 後再開啟 Jetlink。3D 車道畫面會在自車車尾顯示紅色煞車燈與琥珀色方向燈。煞車燈讀取 comma 回報的 carState.brakeLights。左右方向燈與 HUD 箭頭共用閃爍節奏，雙黃燈兩側同閃。煞車與轉向可以同時顯示。車況訊號失效時熄滅燈號。安裝完成後，尾燈顯示直接讀取車況，不依賴鏡頭辨識。

### 辨識到了，HUD 有沒有畫出來？

在版面 5 的 3D 車道視角，Mac 會把新鮮且可定位的辨識結果畫在目標旁。行人、機車、自行車、三角錐、汽車、公車、卡車和斑馬線各有圖示，並為前車的紅色距離與速度文字預留空間。固定的 ROAD 圖示列彙整當前影格中辨識到的類別，斑馬線的實際寬度仍須參考道路畫面。

切到道路實景時，空間圖示跟隨已核對影格的前方 ROAD 影像。鏡頭切到廣角、資料過期或無法對齊時，以固定圖示列查看仍然新鮮的辨識結果。畫面上的 `ROAD 2` 表示這一幀有兩個圖示畫在目標旁。單獨顯示 `ROAD` 時，仍可從固定圖示列查看辨識到的類別。終端機與背景紀錄每五秒列出一次 HUD 回報。

| 終端機回報 | 畫面狀態 |
|---|---|
| `HUD 3D: 2 \| projected` | HUD 程式已對這張影格送出兩個立體物件的繪圖指令。 |
| `estimated height` | 有鏡頭角度校正，投影採用原 HUD 的預設鏡頭高度。 |
| `no camera calibration`、`outside ground view` 或 `no ROAD projection` | ROAD 圖示列仍可提示辨識類別。 |
| `matched 1 native` 搭配 `icons 1` | 同一部前車沿用原生車模，另外畫出一個汽車類別圖示。新增立體車模計數可以是 0。 |
| `2D view` | 道路實景使用固定圖示列。出現 `icons N` 表示另有 N 個圖示已畫在影像中的目標旁。 |
| `result expired` | 已排除時間過期或超前的辨識結果。 |
| `HUD: awaiting renderer` | 尚未收到新鮮的 HUD 繪圖回報。確認正在使用新版 Mac helper，並切到有 3D 車道的畫面，例如模式七。 |

### 前車重複顯示

Mac HUD 用實際距離比對 Carrot 和 ROAD 偵測到的車輛。位置吻合時立即沿用原生車模和距離標籤，避免同一台車疊上第二個灰白車身。只有 ROAD 看到的汽車、公車或卡車，會在連續兩張不同影格都有目標時顯示，並使用相同的 3D 距離比例。相鄰車道的目標仍可個別顯示。終端或背景紀錄的 `matched 1 native` 表示已配對一台原生車輛。

### 前車資訊、路緣與機車

原生 L1 的距離與速度使用亮紅字。01 自車保留 92% 的車身大小。煞車時，上排紅色像素和中央煞車燈亮起。打方向燈時，下排對應側的琥珀色像素會閃爍。兩排燈獨立加大，同時煞車、打燈時也能分辨。3D 場景以可靠且新鮮的道路邊緣，在各目標所在距離判斷它是否明顯位於路外。主要前車與切入警示保留；視野缺少可靠路緣時繼續顯示。ROAD 圖示列仍反映鏡頭辨識類別。

機車辨識保留較低分的候選，連續兩張新影格位置吻合才採用低分候選。騎士與車體一對一重疊時合併為機車。車體完全沒被模型辨識時，單靠人形框無法可靠區分騎士與行人。
