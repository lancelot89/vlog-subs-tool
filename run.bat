@echo off
setlocal enabledelayedexpansion
set "APPDIR=%~dp0"
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"
set "PY=%APPDIR%env\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] 同梱Pythonが見つかりません: "%PY%"
  echo [HINT] README_start_here.md のトラブルシューティングを参照してください。
  pause
  exit /b 1
)
set "LOGDIR=%LOCALAPPDATA%\VlogSubsTool\logs"
if "%LOCALAPPDATA%"=="" set "LOGDIR=%USERPROFILE%\AppData\Local\VlogSubsTool\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOGFILE=%LOGDIR%\launch.log"
echo [%DATE% %TIME%] Launching VLog Subs Tool >> "%LOGFILE%"
"%PY%" -m app.main %* >> "%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo [ERROR] アプリケーションがエラー終了しました。ログを参照してください。
  echo        "%LOGFILE%"
  pause
  exit /b %EXITCODE%
)
endlocal
