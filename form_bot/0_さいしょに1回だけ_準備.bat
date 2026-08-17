@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   準備をします（さいしょの1回だけ）
echo ============================================
echo.
echo 200MBほどダウンロードします。5分ほどかかります。
echo.
pause

python --version
if errorlevel 1 (
  echo.
  echo [エラー] Python が入っていません。
  echo https://www.python.org/downloads/ から入れてください。
  echo インストール中の画面で「Add Python to PATH」に必ずチェックを入れてください。
  echo.
  pause
  exit /b
)

echo.
echo --- 必要な部品を入れています ---
python -m pip install --quiet playwright requests
if errorlevel 1 goto err

echo --- ブラウザを入れています（時間がかかります）---
python -m playwright install chromium
if errorlevel 1 goto err

echo.
echo ============================================
echo   準備できました
echo   次は「1_下見_5社だけ.bat」を実行してください
echo ============================================
echo.
pause
exit /b

:err
echo.
echo [エラー] 途中で失敗しました。この画面をそのままコピーして共有してください。
echo.
pause
