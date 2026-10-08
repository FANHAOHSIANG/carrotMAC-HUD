# C4 停車換模型實驗修補

官方 carrot-wip 的 offroad 是系統狀態，沒有手動切换選項。本修補不改 IsOnroad／IsOffroad，也不把 READY 偽裝為熄火。

驗證基準：官方 `ajouatom/openpilot` 的 `e74e6938ddc4574b1ba19ee7405ff146f3c1728e`，配合已驗證的 Mac JetLink 0.8.5／Protocol 3。安裝器只接受這個 C4 commit；版本不同或補丁衝突時停止。main 的 Mac 自動同步流程不會安裝此 C4 修補。

## 行為

- 需明確安裝啟用；不存在 `/data/jetlink-parked-model-switch` 時，維持官方條件。
- Mac／相容 Protocol 3 App 連線、P 檔、standstill、vEgo 與 vEgoRaw 均小於 0.01 m/s，CAN 有效且未 timeout，selfdriveState 和 carControl 的 enabled／active／latActive／longActive 都關閉。
- 三個服務的資料皆須有效、存活且小於 250 ms；以上條件持續至少 2 秒。
- **啟用後，P 檔會先暫停外接模型、使用 C4 內建模型，即使當下沒有要換模型。** modeld 關閉外接 IPC、重置內建 recurrence，產出至少三個內建輸出並持續更新確認，daemon 才釋放舊 ENGINE_REQ，讓 App 能選另一個模型。
- 新模型仍經官方完整 spec 驗證及原有原子核准記錄。離開 P 檔、開始移動、啟用控制、資料過期、內建輸出停止，皆撤銷核准窗口。Mac 正在下載／編譯的工作可能繼續，但 C4 不核准新模型。
- P 檔期間維持內建推論；選好模型後，在停止、未啟用控制的情況下排入 D 檔，才允許重新接入外接推論。先等 C4 確認外接模型工作，再啟用輔助駕駛。啟用此修補時，行駛或控制已啟用都不能重新接入另一個外接 session。
- 未準備好的模型、未知 host、Protocol 2 與 Jetson 不會獲得新增的停車核准權限。

## 安裝（在 C4 的 SSH 終端執行）

首次安裝必須關閉車輛電源，保持 C4 供電，等 C4 回到 offroad 畫面。Mac 上先完成 0.8.5／Protocol 3 安裝。此實驗版尚未做 C4／Ioniq 5／TURZX 實機測試，不是已完成的道路驗收版本。

```sh
git clone --depth 1 --branch experimental/parked-model-switch https://github.com/FANHAOHSIANG/carrotMAC-HUD.git /data/carrot-parked-switch
python3 /data/carrot-parked-switch/scripts/install_c4_parked.py --check
python3 /data/carrot-parked-switch/scripts/install_c4_parked.py --install
sudo reboot
```

安裝器檢查真正 offroad、固定 C4 commit、補丁可套用性，備份原始檔，執行 CPU 測試後才建立啟用檔。任何步驟失敗即嘗試還原，並輸出錯誤；不要跳過檢查或強行覆蓋。它不拉取／更新 C4 的官方分支。

重啟後只做停車測試：車輛 READY、P 檔、未啟用控制，等待 `parked_switch_ready` 變成 true，再在 Mac 點 Use Model。可在 C4 查看：

```sh
cat /dev/shm/carrot-jetlink-model.json
cat /dev/shm/carrot-jetlink.json
```

狀態欄位的時間戳必須持續更新；單次 true 不代表窗口一直有效。若沒有就緒或出現錯誤，不要嘗試移動來完成核准。可回到正常熄火流程選模型。

## 還原

關閉車輛電源、保持 C4 供電並回到 offroad：

```sh
python3 /data/carrot-parked-switch/scripts/install_c4_parked.py --rollback
sudo reboot
```

備份在 `/data/carrot-parked-switch-state/backups/`。若 C4 已更新到別的官方 commit，還原器只停用窗口，不會覆蓋成舊程式。官方更新也可能覆蓋這個本機修補；每個新基準須重新適配與驗證，不能視為自動沿用。

## 驗證

`python3 scripts/check_c4_parked.py` 下載固定官方基準的四個相關檔案、檢查／套用補丁、解析 Python 語法，並執行 25 個 CPU 測試。

測試直接執行套用後的 modeld handoff、daemon setup gate 及 Mac approval 函式；以替身隔離 CAN、GPU、USB 與模型契約驗證器，覆蓋車況／資料失效、交接順序、三個內建輸出、確認過期、取消 pending IPC、未就緒模型和核准前取消。它們沒有驗證真實 CAN 訊號、QCOM fallback 時間、CUDA／CoreML、USB 重連、HUD 或道路控制。原有契約檢查保留；本次沒有重跑官方完整模型測試集。
