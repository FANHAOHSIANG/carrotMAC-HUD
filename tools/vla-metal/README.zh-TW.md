# PhysicalAI VLA — Apple Silicon Metal 離線實驗

此工具取自 Tony [b0ba1f13](https://github.com/TonyBinheWu/sunnypilot/commit/b0ba1f13db3fbed94ea88c8b93cec488ef3c2b7f) 的回放參考執行器，改用 llama.cpp Metal。不會安裝或修改 Jetlink、HUD、C4、modeld 或 CAN。沒有即時相機、USB、車輛控制或回傳介面。只在 Mac 與 C4 分離、Jetlink 與 HUD 均退出的離線環境執行。

## Jetlink App 整合候選版

在測試分支根目錄、退出 Jetlink 並斷開 C4 後執行：

```sh
python3 scripts/build_vla_jetlink.py --output "$HOME/CarrotVLA-Jetlink-candidate"
```

需要現有 Jetlink Mac 編譯工具（完整 Xcode、xcodegen 等）。使用 versions.json 的固定官方原始碼，套用現有 HUD 補丁與新增 VLA 選單，先執行 Python 單元測試，再編譯並驗證 App 簽章。候選 App 放在 output 下的 macos/build/Jetlink.app，不會替換正式 App。原始碼與編譯尚未在實體 Mac 驗證。

Jetlink 頂部選單 VLA → 離線推理測試會開啟 Terminal 的互動工具。退出 Jetlink、HUD 並斷開 C4，依提示按 Enter，選取含 rlog 與 fcamera.hevc 的單段資料夾，或已轉換的 frames.jsonl。工具建立獨立 venv、下載固定 schema 並轉換影格、建置固定 llama.cpp Metal 版、驗證與下載權重，再測試最多 13 張。結果存到 ~/Library/Application Support/CarrotMacHUD/VLA-Offline/run.*，完成後在 Finder 選取 results.jsonl。再開候選 App，從 VLA → 檢視 VLA 回放結果匯入。也可以不編譯 App，直接從測試分支根目錄執行：

```sh
bash tools/vla-metal/Run-VLA-Offline.command
```

首次需要網路、Python 3.11+、git、Xcode 命令列工具與 CMake；若缺 CMake，工具會停止並提示安裝。可直接使用公開分享給自己的 Carrot route 網址（網路行車紀錄模式），不登入 C4。工具從 /manifest 找到同段 rlog 與 fcamera.hevc，依清單大小核對下載，預設只下載第一個符合的片段；若只有 qcamera.ts 則停止。也可使用本機紀錄。個人網址由參數或對話框傳入，不寫進 GitHub。權重及編譯產物會快取。若 schema 或資料版本不符、沒有有效配對影格、引擎無法編譯，工具會停止，不會用假造位姿或 CPU 回退。原始碼尚未在 Mac 執行驗證。程式啟動與每張樣本前檢查 Jetlink 已退出，不是硬體互鎖；務必手動拔除 C4。

## 準備

Apple Silicon macOS、Python 3.11 或更新版本、至少約 3 GB 權重空間及額外統一記憶體。記憶體與延遲未實機驗證。安裝獨立 Python 環境：

```sh
cd tools/vla-metal
python3 -m venv .venv
source .venv/bin/activate
python -m pip install numpy opencv-python
python -m unittest -v test_replay
```

取得 [llama.cpp b12676](https://github.com/ggml-org/llama.cpp/releases/tag/b12676) 的 arm64 Metal 版 llama-server。如果沒有相容的二進位，需自行從該 tag 使用 CMake 建置（GGML_METAL=ON）。執行該二進位的 `--list-devices`，確認顯示 MTL0 或 Metal 裝置。程式拒絕未列出的裝置、CPU 回退及不符合 b12676 的服務版本。伺服器只聽本機 loopback，隨機 API key，離線模式；退出後關閉。

## 準備行車紀錄

manifest 是預先匯出的本機 JSONL，每行包括 image（相對於 manifest 的前向影像路徑）、timestamp_us（相機時間）、egomotion（9 筆由早到晚、每 0.25 秒的實際車輛歷史位姿 [前向公尺, 左向公尺, 逆時針弧度]，最後為 [0,0,0]）。可附帶 primary 欄位以保留已記錄主模型結果。請勿用虛構位姿衡量實際判斷能力。互動工具會使用固定 Tony schema 自動嘗試解析 rlog 與影像，其他版本的紀錄相容性尚待驗證。

退出 Jetlink、HUD，斷開 C4 後才執行（用實際檔案位置代換）：

```sh
python replay.py --offline-bench \
  --server /absolute/path/to/llama-server \
  --weights "$HOME/vla-weights" --fetch \
  --manifest /absolute/path/to/frames.jsonl \
  --max-frames 13 > results.jsonl
```

第一次 --fetch 從固定 Hugging Face revision 下載模型與影像投影器（約 2.95 GB），驗證大小及 SHA-256。之後可省略 --fetch。若有多個 Metal 裝置，增加 --device MTL0 或實際列出的 ID。輸出 JSONL 含每張影像的 longitudinal/lateral 判讀、推理毫秒數、裝置和固定權重版本；未知結果為 null。可在候選 Jetlink App 的 VLA 選單檢視結果，沒有行車 HUD 顯示，也沒有 GPU 佔用率採樣。

## 驗證限制

原始碼相容性實驗，不是 Jetlink 即時雙模型支援，也不是可上路版本。單模型 Metal 能否執行、資源佔用、與原版輸出一致性、台灣場景準確率均待實體 Mac 驗證。不在行車中或與主駕駛模型同時執行。不把 VLA 結果用作控車或安全決策。

### 直接使用既有 Carrot 分享網址

從測試分支根目錄執行 `bash tools/vla-metal/Run-VLA-Offline.command 'https://<server>/routes/<vehicle>/<selection>'`，或在互動工具選擇「網路行車紀錄」。全程離線車輛、唯讀下載。尚未在實際分享站與 Mac 驗證。

## 與正式版 Jetlink 分開的 VLA 工具

不用編譯或替換 Jetlink；在已停車、退出 Jetlink/HUD、拔除 C4 USB 後，從 repository 根目錄執行：

```sh
bash tools/vla-metal/Start-VLA.command
# 另開 Terminal，查看或停止：
bash tools/vla-metal/Status-VLA.command
bash tools/vla-metal/Stop-VLA.command
```
Start 可選擇原始資料夾、既有 route URL 或已轉換 manifest，也可直接傳入 route URL。它建立獨立的程序群組、單一工作鎖與日誌；手動停止或偵測到 Jetlink 啟動時，嘗試結束該群組，並確認工作鎖釋放。這不是硬體互鎖，也無法保證 supervisor 被強制殺死或系統故障後的清理。未做 Mac 實機或並行負載驗證，不要在車輛行駛期間執行。正式版與 C4 均不修改。停止命令不會對 Jetlink 發出信號。
