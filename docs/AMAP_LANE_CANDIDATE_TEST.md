# Mac HUD AMap 車道候選測試層
配合 Carrot Bridge wide.89 即時欄位和 C4 test/c4-vision-ar-hud 的新 CarrotNaviState.amapLaneCandidate。保留原有 HUD 與 Jetlink 協定，只在有效引導、來源候選、期限有效時以中性色顯示「車道候選 x/y 未配對」。不提供變道箭頭、絕對車道或控制。獨立測試分支，不動 main，不修改已安裝 Mac。需先完成標準 Mac HUD overlay，停車退出 Jetlink，再在此分支執行 python3 scripts/apply_lane_candidate.py "$HOME/CarrotMacHUD/carrot"；還原加 --rollback。先驗證 CI 及 Mac 實機，勿在駕駛時設定。此為額外測試層，尚未納入正式自動安裝。

2026-11-28 安裝相容性修正：支援固定基底的原始 Mac helper、已有標準導航時鐘補丁或交流道補丁的已知版本。無交流道補丁時保留相容 wire slot，不啟用交流道顯示。未知修改仍中止，勿強行覆蓋。若日後更新正式 HUD overlays，先還原本測試層再更新。
