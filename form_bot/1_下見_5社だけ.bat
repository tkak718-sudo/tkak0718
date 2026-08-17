@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   下見：5社だけ（送信されません）
echo ============================================
echo.
echo ブラウザが自動で開きます。触らずに見ていてください。
echo 文字が自動で入っていく様子が見えます。
echo.
echo 送信は一切しません。
echo.
pause

python form_bot.py --csv "..\自動送信対象_77社_20260806.csv" --profile profile.json --headed --limit 5

echo.
echo ============================================
echo   終わりました
echo.
echo   result.csv  … 結果の一覧
echo   shots フォルダ … 画面の写真
echo.
echo   この2つを確認してください
echo ============================================
echo.
pause
