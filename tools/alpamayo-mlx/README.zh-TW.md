# Alpamayo 2 Edge MLX：Mac 離線研究候選版

基於既有 CarrotVLA-Jetlink 離線分支，獨立工具不修改正式 Jetlink、HUD 或 C4。禁止在行駛或駕駛輔助啟用時測試；先停車、退出 Jetlink/HUD 並拔除 C4 USB。沒有車輛控制、即時訊息、CAN、USB 發送或控制器介面。

## 第一階段
- 固定 SMJD11/mlx-vla 43893667449fd5cdc621a8c8da3624ce014f202f。
- 使用 Safman 公開 Q4 模型，首次解析並固定 Hugging Face revision；下一次以 --revision 指定 summary.json 所列 SHA。不是 Tony lat2v 微調權重，不宣稱兩者等效。
- 匯出固定 Tony 980a186 的雙鏡頭幾何及測得的兩秒運動歷史，不使用未來資料推論；未來 1.5 秒只在可用時作參考評分。與 Tony 的 learned bicycle history 不完全等同。
- 十張完整雙鏡頭、64 點軌跡、推理文字、p50/p95 延遲、Metal 峰值記憶體及可用的測得軌跡誤差。基線不啟用剪枝或 ANE 近似，不與 N16/RL Nav 同時執行。
- 未驗證 Mac 硬體、實際模型、錄檔 schema 或權重轉換。只用於研究。

## Mac 安裝
在儲存庫根目錄執行（Python 3.12 建議）：

    python3.12 -m venv .venv-alpamayo
    source .venv-alpamayo/bin/activate
    python -m pip install --upgrade pip
    python -m pip install numpy scipy av pycapnp zstandard huggingface_hub
    python -m pip install 'git+https://github.com/SMJD11/mlx-vla.git@43893667449fd5cdc621a8c8da3624ce014f202f'
    python -m unittest discover -s tools/alpamayo-mlx -p 'test_*.py' -v

另外取得固定 Tony 來源（唯讀研究用，非安裝到 C4）：

    git clone --filter=blob:none --no-checkout https://github.com/TonyBinheWu/sunnypilot.git "$HOME/tony-alpamayo-source"
    git -C "$HOME/tony-alpamayo-source" checkout --detach 980a186d4b63d6f0a62ab2b487dbdfe3f2939127
    git -C "$HOME/tony-alpamayo-source" submodule update --init opendbc_repo

若 opendbc_repo 是普通目錄而非 submodule，只須確認 car.capnp 存在。不要執行 Tony 的安裝器。若來源記錄使用不同 schema 或 camera index 不完整，匯出會停止。需要完整本機 C4 segment 資料夾（名稱末尾 --段號），含 rlog.zst、fcamera.hevc、ecamera.hevc；qcamera 不支援。若 clone 檔案過大可使用已有的同一 commit 完整 checkout。

    python tools/alpamayo-mlx/export_segment.py --segment "/path/to/route--13" --tony-root "$HOME/tony-alpamayo-source" --output "$HOME/alpamayo-samples" --max-samples 6
    python tools/alpamayo-mlx/replay.py --offline-bench --samples "$HOME/alpamayo-samples" --output "$HOME/alpamayo-results" --max-samples 6

每次使用新輸出資料夾。results.jsonl 每個樣本一行；summary.json 為效能總結。首次需下載 Q4 權重及依賴。無法找到相容模型、GPU、輸入、歷史或完整影片則報錯，不以 CPU 或假資料取代。輸出只留在本機；不發送行車資料。

## 下一階段
Tony lat2v 使用不同微調 checkpoint 和 AMD 專用 FP8/INT4 cache；不能把 weights.bin 或 gfx1200 圖直接當成 MLX 權重。需從完整原始 safetensors 驗證 config/tokenizer/模型結構後另行轉換；與公開 Q4 在同一批雙鏡頭資料上比較，才評估 Mac 影子觀察。尚未加入即時 HUD 或 Jetlink 同時推論。

來源：
- https://github.com/SMJD11/mlx-vla/tree/43893667449fd5cdc621a8c8da3624ce014f202f
- https://huggingface.co/Safman/Alpamayo2-Edge-MLX-q4
- https://github.com/TonyBinheWu/sunnypilot/tree/980a186d4b63d6f0a62ab2b487dbdfe3f2939127/openpilot/selfdrive/alpamayo
- https://huggingface.co/karelnagel/alpamayo2-edge-lat2v/tree/34c8c070b1557c8df79ebf3688ed0ff840f339a0

## 一鍵啟動（候選版）

停車、退出 Jetlink/HUD 並拔除 C4 後，在分支根目錄執行：

    bash tools/alpamayo-mlx/Run-Alpamayo-Offline.command

也可以將完整本機 segment 路徑作為第一個參數。工具建立獨立 venv，執行單元測試、匯出雙鏡頭資料並進行 Q4 推論，結果留在 ~/Library/Application Support/CarrotMacHUD/Alpamayo-MLX-Offline/run.*。未驗證實體 Mac；首次下載模型與來源需要網路。
