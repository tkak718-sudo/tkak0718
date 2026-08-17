@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   下見：77社ぜんぶ（送信されません）
echo ============================================
echo.
echo ブラウザは表示しません。15分ほどかかります。
echo 送信は一切しません。
echo.
pause

python form_bot.py --csv "..\自動送信対象_77社_20260806.csv" --profile profile.json --limit 77

echo.
echo ============================================
echo   終わりました
echo.
echo   result.csv の「理由」の列を見てください。
echo   ・空欄        … 自動で送れます
echo   ・必須項目が…  … 手動になります
echo   ・本文が上限…  … 手動になります
echo ============================================
echo.
pause
