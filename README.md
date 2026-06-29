# ⚔️ AOE2 DE Replay 分析工具

Age of Empires II: Definitive Edition 錄像檔深度分析工具，提供圖形化操作介面，自動解析對戰紀錄並產生 HTML 互動報告。

![version](https://img.shields.io/badge/version-1.0.0-gold)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## 功能特色

- **一鍵分析**：選擇 `.aoe2record` 檔案，點擊開始，自動完成五個分析步驟
- **兵種統計**：依文明、兵種類別統計各玩家訓練數量與比例
- **策略辨識**：自動判斷各玩家戰術（騎兵流、弓兵流、攻城流等）
- **轉折點偵測**：找出對局中物件數量出現反轉的關鍵時刻
- **MVP 排名**：綜合軍事投入、APM、策略深度給出評分
- **互動式 HTML 報告**：含圖表、快照對比、兵種卡片，可直接在瀏覽器查看

## 畫面預覽

```
┌─────────────────────────────────────────┐
│ ⚔️  AOE2 DE Replay 分析工具        v1.0.0 │
├─────────────────────────────────────────┤
│ 選擇 .aoe2record 紀錄檔               │
│ [___________________________] [瀏覽…]  │
│                                         │
│ [▶   開始分析]                          │
│                                         │
│ ① ② ③ ④ ⑤  分析步驟進度              │
│                                         │
│ 分析日誌...                             │
│                                         │
│ [🌐 開啟 HTML 報告] [📄 開啟文字報告]  │
└─────────────────────────────────────────┘
```

---

## 系統需求

- Windows 10 / 11
- Python 3.10 以上
- Age of Empires II: Definitive Edition（Steam 版）

## 安裝

```bash
# 1. 下載專案
git clone https://github.com/badoyau/aoe2de-analysis-tool.git
cd aoe2de-analysis-tool

# 2. 安裝 Python 套件
pip install mgz-fast

# 3. 啟動
python launcher.py
```

## 使用方式

1. 執行 `python launcher.py`（或雙擊打包好的 `AOE2分析工具.exe`）
2. 點擊「瀏覽…」選擇 `.aoe2record` 錄像檔
   - 錄像檔預設位置：`C:\Users\<你的名字>\Games\Age of Empires 2 DE\<ID>\savegame\`
3. 點擊「▶ 開始分析」
4. 分析完成後自動開啟 HTML 報告

---

## 打包成 EXE

```bash
# Windows（雙擊執行）
build.bat

# 或使用 make（需安裝 Git Bash）
make build
```

打包完成後，`dist/AOE2分析工具/` 資料夾內容：

```
dist/AOE2分析工具/
├── AOE2分析工具.exe   ← 主程式
├── scripts/           ← 分析腳本（必須保留）
├── data/              ← 兵種資料（必須保留）
└── _internal/         ← PyInstaller 執行環境（自動產生）
```

> 發布時請將整個 `dist/AOE2分析工具/` 資料夾一起壓縮分享。

---

## 專案結構

```
aoe2de-analysis-tool/
├── launcher.py              # GUI 主程式
├── scripts/
│   ├── parse_replay.py      # ① 解析標頭
│   ├── parse_body.py        # ② 解析主體
│   ├── parse_body_deep.py   # ③ 深度分析（兵種、建築、APM）
│   ├── analyze.py           # ④ 產生文字報告
│   └── generate_web_report.py  # ⑤ 產生 HTML 互動報告
├── data/
│   ├── units.json           # 兵種 ID ↔ 中文名稱對照表（245 種）
│   └── civilizations.json   # 文明資料
├── replays/                 # 放置 .aoe2record 錄像檔
├── build.bat                # Windows 打包腳本
├── Makefile                 # make build / make clean
└── .gitignore
```

---

## 版本紀錄

| 版本 | 日期 | 說明 |
|------|------|------|
| 1.0.0 | 2026-06-29 | 初始版本，支援 8 人對戰分析、245 種兵種中文對照 |

---

## 使用套件

- [mgz-fast](https://github.com/mgz-fast/mgz-fast) — AOE2 DE 錄像解析
- [tkinter](https://docs.python.org/3/library/tkinter.html) — GUI 介面
- [PyInstaller](https://pyinstaller.org/) — 打包成 exe
