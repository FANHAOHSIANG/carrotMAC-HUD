# HKG 外接 HUD 移植檢查

## 相鄰車道雷達目標轉接（2026-10-24）

已接入 HKG 現有 `radarTracks.points`，Mac 僅在 HUD 程序內改名為 Carrot 的
`liveTracks.points`，由原版雷達篩選與場景程式處理。這不是完整側後方角雷達移植。

- 只轉送有有限數值 dRel/yRel/vRel/trackId 的前方目標；最多 32 個，依距離排序。
- HKG SCC-only 來源的 yRel=NaN 不會被當成置中的車，也不以盲點旗標虛構距離或車速。
- 雷達錯誤、來源過期、空目標或來源消失時清除額外目標；沿用 0.5 秒有效期。
- 保留 5 Hz／14 KiB 上限；超限優先捨棄額外 tracks，避免擠掉車道、路徑與主要前車。
- 場景測試：左側 20 m、64.8 km/h；右側 25 m、75.6 km/h，左右座標正確；
  T101/T102 為一般目標，L1 仍為主要前車，不改既有字體優先級。
- 不修改雷達 ECU 設定、CAN 收發、Panda Safety、模型或車輛控制。

63 項 Jetlink 與 25 項 Mac 測試通過。包含實際 publisher→JSON→Mac reader→
pinned Carrot parser→build_cluster_scene 的測試；未作實車／USB 驗證。

HKG 目前的 Hyundai RadarInterfaceExt 在 SCC 路徑僅取得一個 ACC 前車，橫向位置為 NaN。
carState 只有左右盲點 Bool，沒有 Carrot 的 leftLongDist/rightLongDist 等距離欄位。
因此，只有實車 `radarTracks` 已含左右目標時，這次轉接才會讓 HUD 出現那些目標。
原始角雷達與 ADRV/CCNC 物件解碼尚未接入；下一步需確認車上實際報文與內容。

C4 更新 HUD 分支後，可在車輛停妥且 CAN 正常工作時執行：

```sh
cd /data/openpilot
python tools/jetlink/hud_radar_check.py
```

此診斷只訂閱 radarTracks/carState/can，五秒後結束；顯示目標數、可用橫向位置、
錯誤旗標及 pinned Carrot 解碼器所用候選報文的 bus/長度/次數，不傳送 CAN。
觀察到位址不代表已驗證物件格式，短時間沒收到也不能判定硬體不支援。

Mac 需更新 HKG helper（最新版套件的 06-HKG-HUD.command），既有 Jetlink.app 保留，
不重建 App、不重新下載模型。新舊兩端可分開更新：舊 Mac 會忽略新 radarTracks 欄位，
新版 Mac 仍接受舊七來源封包。

## 車道、車速與前車對接複查（2026-10-24）

發現並修正兩個前車資料缺口：
- HKG `RadarState.LeadData` 使用 `present`，pinned Carrot 讀取 `status`。publisher 現在將兩個 lead 的旗標轉換；明確的 present=false 優先，保留舊 status 相容性。
- 補送 `modelV2.leadsV3`（最多三組預測的第一個位置／速度／加速度與不確定度）及模型第一個自車速度，讓原版視覺 lead parser 可工作。三組模型預測不代表三輛不同實車。

| 項目 | 完整資料鏈測試結果 |
| --- | --- |
| 車速 | vEgo=20 m/s → 72 km/h；vEgoCluster=20.5 → 顯示速度欄位 73.8 km/h；停車回到 0 |
| 設定速度 | vCruiseCluster=90 km/h 保持 90，沒有重複乘 3.6 |
| 車道與路徑 | 四條曲線、兩條道路邊緣、路徑均到達 Carrot UI state；33 點取樣成 17 點，保留端點與左右方向；低機率車道隱藏 |
| 前車 | present=true 的 leadOne/leadTwo 可見；雷達 yRel 左正轉為繪圖 lateral 左負；距離、相對速度、絕對速度與 TTC 核對通過 |
| 視覺前車 | 無 radarState 時可從 leadsV3 取得目標；低機率預測排除；保留 Carrot 相機到保桿距離修正 |
| 過期／消失 | present=false 清除目標；model/radar service 消失或封包過期時清除真實路徑和目標，過期顯示無資料 |

使用實際 publisher → JSON → Mac read_packet → pinned Carrot live parser → UI state。
舊版 897b2932d 在前車／視覺前車兩項測試均得到 0 個目標，修正後五項資料鏈測試通過。
另有 61 項 Jetlink 測試及 23 項 Mac 測試通過（Mac 測試含上述五項）。
測試命令：

```sh
CARROT_HELPER_ROOT=/path/to/carrot HKG_CHECKOUT=/path/to/sunnypilot python -m unittest discover -s tests -v
```

本次 runtime 修改只有 C4 publisher；既有 Mac adapter/renderer 可直接消費新欄位，不必重建 App。
不擴大 14 KiB／5 Hz 上限，不修改 CAN、控制、模型推論或資料有效期。
未接入 liveTracks、側後方角雷達／Carrot 特有 CAN 解碼、導航速限與相機串流；不能宣稱完整周遭車輛偵測。
仍需實機核對畫面與延遲；上述為合成資料測試，並非實車、GPU 或 USB 驗證。


以下為先前移植紀錄；本節為最新核對與修正結果。
## 結論

不需要把整套 Carrotpilot 複製進 hkg。Mac 已使用 Carrot 的 cluster renderer、
H.264 編碼、TURZX USB 輸出與 Jetlink App receiver；需要完善的是跨分支資料轉接、
待機生命週期，以及 hkg 的 HUD 傳送排程。

本次比較以使用者安裝的 Carrot renderer `a564ce1dc082909b1fdc73b72e64d920336b34d6`、
Mac adapter 基準 `7e14cc345a4602ad0b624babe087f51c1624b45a`、
hkg HUD `ea4b498f5198b6d58d0cce797cb47e34da90ada9` 為準，沒有宣稱涵蓋 Carrot 最新所有分支。

## 目前已有與尚缺

| 部分 | 目前實作 | 判斷 |
| --- | --- | --- |
| 繪圖、H.264、TURZX | Mac 使用既有 Carrot renderer | 不需要重搬 |
| Mac USB 接收 | 既有 App 的 CarrotHUD receiver；latest-only writer | 可繼續使用既有 App |
| 基本車況 | hkg JSON 轉接七種 service；車速、路徑、前車、方向燈等 | 保留跨 schema 轉接，不能直接混用兩分支的序列化事件 |
| 待機輸出 | 原版 startup、output gate、deviceState.started 都有限制 | 本次使用 renderer 的 mode 1 支援 live standby |
| HUD 排程 | hkg 發布上限 5 Hz；只在沒有 pending inference 且軟期限至少剩 3 ms 時嘗試送出 | 可能飢餓，需實機分段量測；本次不改模型 deadline 或 USB ownership |
| 完整進階資訊 | Carrot 訂閱 26 種 service；hkg 目前轉接七種及有限欄位 | 統計、TPMS、校正、規劃與導航等須逐項確認 hkg 來源與欄位後擴充 |
| 地圖、相機影像 | Carrot 有獨立 media/camera 流程；hkg 尚未接入 | 需要另行移植來源、媒體封包與頻寬安排，複製 renderer 不會產生資料 |

## 本次修正

- HKG helper 使用 `ClusterHudDebug=1`，只允許 live standby 輸出；不開 mode 2/3 的除錯面板。
- 啟動不再等待 IsOnroad，熄火後也不因 deviceState.started=false 結束輸出。
- 啟用時鐘；收到新鮮 deviceState 且 started=false、沒有 carState 時，顯示 `HUD connected / Vehicle standby` 與時間。
- 有新鮮封包但缺車況時顯示等待車況；封包過期仍顯示無資料。
- 不修改 IsOnroad / started，不產生假的車速、車道或前車。若 C4 尚未發布某項資料，畫面無法顯示該項即時值。

18 項 Mac adapter/installer/settings/renderer 測試通過。測試使用 pinned Carrot parser、
DisplayParams 與實際 output gate 類別，驗證無封包啟動、offroad/onroad/offroad、
待機、資料遺失與恢復；無實體 Mac/C4/TURZX/GPU 驗證。

## 使用者日誌的判讀與未解項目

七種 service 都出現在封包中，代表先前漏掉新接收車況的 timestamp bug 已不再阻擋全部車況。
螢幕 heartbeat 與約 9.9 Hz refresh 表示輸出程序仍在更新。
接收封包距今 2.24 秒超過目前 0.5 秒有效期，會讓資料被清空。
`alive=7/26` 是七種可用 service 除以 renderer 訂閱數，不代表另外 19 種都是必需或出錯。
`state=0.7–1.0Hz` 是 renderer 自啟動以來有有效 carState 的更新次數平均，不能當作 USB 封包頻率。

尚不能只憑 Mac 日誌分辨低頻發生於 C4 publisher、USB 傳送空檔或 Mac receiver。
應在 C4 讀取 `/dev/shm/sunnypilot-jetlink-hud.packet` 的 header 年齡與更新頻率，
並同時觀察 Mac snapshot.packet。C4 穩定約 5 Hz 而 Mac 斷續時再調查 sender/receiver；
C4 檔案本身也斷續則先處理 publisher 排程或例外。
不把有效期直接延長到數秒來掩蓋斷流。

## 原版差異來源

- [Carrot HUD protocol / SnapshotBuilder](https://github.com/ajouatom/openpilot/blob/a564ce1dc082909b1fdc73b72e64d920336b34d6/tools/jetlink/hud_protocol.py)：26 種 service、參數與 cereal 事件；10 Hz 發布節奏。
- [Carrot HUD helper](https://github.com/ajouatom/openpilot/blob/a564ce1dc082909b1fdc73b72e64d920336b34d6/tools/jetlink/hud.py)：startup 等待行車或 debug mode。
- [Carrot cluster main](https://github.com/ajouatom/openpilot/blob/a564ce1dc082909b1fdc73b72e64d920336b34d6/openpilot/selfdrive/carrot/cluster/main.py)：輸出 gate 與 deviceState.started 的關閉條件。
- [Carrot Jetlink daemon](https://github.com/ajouatom/openpilot/blob/a564ce1dc082909b1fdc73b72e64d920336b34d6/openpilot/selfdrive/modeld/jetlink/daemon.py)：同步推論、before/after reply HUD 傳送，與 hkg pipeline/lease 架構不同。
- [hkg HUD sender](https://github.com/FANHAOHSIANG/sunnypilot/blob/ea4b498f5198b6d58d0cce797cb47e34da90ada9/openpilot/selfdrive/modeld/jetlink/hud.py)：pending、期限與 backpressure 保護。

Carrot daemon 不是可直接替換 hkg DirectClient 的獨立 HUD 模組；替換會連帶改變模型傳輸與端點管理。
