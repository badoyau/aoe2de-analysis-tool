@echo off
chcp 65001 >nul
echo ===================================
echo  AOE2 DE 分析工具 — 打包成 EXE
echo ===================================
echo.

REM 確認 pyinstaller 是否安裝
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [安裝] 找不到 PyInstaller，正在安裝...
    pip install pyinstaller
)

echo [打包] 開始打包...
python -m PyInstaller ^
    --onedir ^
    --windowed ^
    --name "AOE2分析工具" ^
    --clean ^
    launcher.py

if errorlevel 1 (
    echo.
    echo [錯誤] 打包失敗，請查看上方訊息
    pause
    exit /b 1
)

echo.
echo [完成] exe 已產生於 dist\AOE2分析工具\AOE2分析工具.exe
echo.
echo [提醒] 發布時請將以下資料夾一起複製到 dist\AOE2分析工具\ ：
echo         scripts\
echo         data\
echo         replays\   （可選，使用者也可自行建立）
echo.
pause
