@echo off
setlocal
title [3/3] ai-agent-rag - 服务 http://127.0.0.1:8001
cd /d "%~dp0"

if not exist "evidenceqa\app\main.py" goto no_code
cd /d "%~dp0evidenceqa"

if not exist ".venv\Scripts\python.exe" goto no_env

call ".venv\Scripts\activate.bat"

echo ==========================================================
echo   正在启动 RAG 服务
echo.
echo   地址：http://127.0.0.1:8001
echo   浏览器会在约 5 秒后自动打开
echo.
echo   这个窗口不要关闭 —— 关掉窗口就等于停止服务
echo   要停止服务：按 Ctrl + C
echo ==========================================================
echo.
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8001"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

echo.
echo 服务已停止。
pause
exit /b 0

:no_env
echo [提示] 还没安装环境
echo 请先双击  1_安装环境.bat
pause
exit /b 1

:no_code
echo [错误] 找不到 evidenceqa\app\main.py
echo 当前目录：%~dp0
pause
exit /b 1
