@echo off
setlocal
title [2/3] ai-agent-rag - 导入演示数据
cd /d "%~dp0"

if not exist "evidenceqa\app\main.py" goto no_code
cd /d "%~dp0evidenceqa"

if not exist ".venv\Scripts\python.exe" goto no_env
if not exist "scripts\seed_demo.py" goto no_seed

call ".venv\Scripts\activate.bat"

echo ==========================================================
echo   正在重建演示数据库，并导入 3 篇示例文档
echo ==========================================================
python scripts\seed_demo.py
echo.
echo ----------------------------------------------------------
echo   如果上面显示导入成功：下一步双击  3_启动服务.bat
echo   如果提示「数据已存在」之类：可以忽略，直接启动即可
echo ----------------------------------------------------------
pause
exit /b 0

:no_seed
echo [错误] 找不到 scripts\seed_demo.py
echo 请确认 evidenceqa 文件夹是完整的（应包含 app / data / scripts / tests）
pause
exit /b 1

:no_env
echo [提示] 还没安装环境
echo 请先双击  1_安装环境.bat
pause
exit /b 1

:no_code
echo [错误] 没找到 evidenceqa\app\main.py
echo 当前目录：%~dp0
pause
exit /b 1
