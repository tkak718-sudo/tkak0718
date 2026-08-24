@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo   自動入力 → 送信は自分で押す
echo ============================================
echo.
echo ブラウザが自動で開き、フォームに入力されます。
echo 入力が終わると、そこで止まります。
echo.
echo   1. ブラウザで内容を確認
echo   2. 自分で送信ボタンを押す
echo   3. この黒い画面に戻って Enter
echo.
echo   送らない場合は  s  ＋Enter
echo   やめる場合は    q  ＋Enter
echo.
set /p N="何社ぶん開きますか（最初は 5 を推奨）: "
if "%N%"=="" set N=5

python form_bot.py --csv "..\自動送信対象_77社_20260806.csv" --profile profile.json --assist --to-confirm --limit %N%

echo.
echo ============================================
echo   終わりました
echo   Enterを押した会社は台帳に記録されています。
echo   次に実行しても、その会社は開きません。
echo ============================================
echo.
pause
