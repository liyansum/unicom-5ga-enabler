@echo off
chcp 65001 >nul
title 开启5GA
setlocal
cd /d "%~dp0"
set "FIVEGA_PY=%~dp0runtime\python.exe"
if exist "%FIVEGA_PY%" goto run
set "FIVEGA_PY=%~dp0runtime\Scripts\python.exe"
if not exist "%FIVEGA_PY%" goto missing
:run
"%FIVEGA_PY%" -I -X utf8 -u "%~dp0restore.py"
set "RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %RESTORE_EXIT%
:missing
echo 缺少运行环境，请完整保留 fastboot 文件夹。
pause
exit /b 1
