@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   テスト送信：自社のフォームあて 1件だけ
echo ============================================
echo.
echo ここで初めて「実際に送信」します。
echo 宛先は御社自身のフォームです。他社には送りません。
echo.
set /p URL="御社の問い合わせフォームのURLを貼り付けてEnter: "
if "%URL%"=="" (
  echo URLが空です。中止します。
  pause
  exit /b
)
echo.
echo 送信先: %URL%
echo.
set /p OK="この1件を送信します。よければ「はい」と入力してEnter: "
if not "%OK%"=="はい" (
  echo 中止しました。
  pause
  exit /b
)

python form_bot.py --csv "..\自動送信対象_77社_20260806.csv" --profile profile.json --test-url "%URL%" --send --yes --headed

echo.
echo ============================================
echo   終わりました
echo.
echo   御社のメールに届いた内容を確認してください。
echo   ・改行が崩れていないか
echo   ・返信先が ishii@active-c.jp になっているか
echo ============================================
echo.
pause
