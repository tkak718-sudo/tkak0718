@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   本番送信
echo ============================================
echo.
echo 実際に他社へ送信します。
echo 一度送った会社は自動で飛ばされるので、
echo このファイルを何度実行しても二重送信にはなりません。
echo.
set /p N="今回、何社に送りますか（最初は 10 を推奨）: "
if "%N%"=="" set N=10
echo.
echo %N%社に、60秒おきに送信します。
echo おおよそ %N% 分かかります。
echo.
set /p OK="よろしければ「送信します」と入力してEnter: "
if not "%OK%"=="送信します" (
  echo 中止しました。
  pause
  exit /b
)

python form_bot.py --csv "..\自動送信対象_77社_20260806.csv" --profile profile.json --send --yes --limit %N% --interval 60

echo.
echo ============================================
echo   終わりました
echo.
echo   result.csv の「結果」の列
echo   ・sent     … 送信できました
echo   ・unknown  … 送ったが完了画面を確認できず
echo                 shots の写真を見て判断してください
echo   ・skip     … 送っていません
echo.
echo   sent_ledger.jsonl は絶対に消さないでください。
echo   二重送信を防ぐファイルです。
echo ============================================
echo.
pause
