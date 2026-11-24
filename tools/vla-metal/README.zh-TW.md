# PhysicalAI VLA — Apple Silicon Metal 離線實驗

此工具取自 Tony [b0ba1f13](https://github.com/TonyBinheWu/sunnypilot/commit/b0ba1f13db3fbed94ea88c8b93cec488ef3c2b7f) 的回放參考執行器，改用 llama.cpp Metal。不會安裝或修改 Jetlink、HUD、C4、modeld 或 CAN。沒有即時相機、USB、車輛控制或回傳介面。只在 Mac 與 C4 分離、Jetlink 與 HUD 均退出的離線環境執行。

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

manifest 是預先匯出的本機 JSONL，每行包括 image（相對於 manifest 的前向影像路徑）、timestamp_us（相機時間）、egomotion（9 筆由早到晚、每 0.25 秒的實際車輛歷史位姿 [前向公尺, 左向公尺, 逆時針弧度]，最後為 [0,0,0]）。可附帶 primary 欄位以保留已記錄主模型結果。請勿用虛構位姿衡量實際判斷能力。本版不直接讀 rlog，需先在原 Tony 回放工具或資料匯出環境完成同步。

退出 Jetlink、HUD，斷開 C4 後才執行（用實際檔案位置代換）：

```sh
python replay.py --offline-bench \
  --server /absolute/path/to/llama-server \
  --weights "$HOME/vla-weights" --fetch \
  --manifest /absolute/path/to/frames.jsonl \
  --max-frames 13 > results.jsonl
```

第一次 --fetch 從固定 Hugging Face revision 下載模型與影像投影器（約 2.95 GB），驗證大小及 SHA-256。之後可省略 --fetch。若有多個 Metal 裝置，增加 --device MTL0 或實際列出的 ID。輸出 JSONL 含每張影像的 longitudinal/lateral 判讀、推理毫秒數、裝置和固定權重版本；未知結果為 null。沒有自動 HUD 顯示，也沒有 GPU 佔用率採樣。

## 驗證限制

原始碼相容性實驗，不是 Jetlink 即時雙模型支援，也不是可上路版本。單模型 Metal 能否執行、資源佔用、與原版輸出一致性、台灣場景準確率均待實體 Mac 驗證。不在行車中或與主駕駛模型同時執行。不把 VLA 結果用作控車或安全決策。
