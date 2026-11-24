@echo off
setlocal
title ai-agent-rag - API 冒烟测试
cd /d "%~dp0"

if not exist "day01_api_smoke.py" goto no_script
if not exist ".env" goto no_env

echo ==========================================================
echo   API 冒烟测试：4 个实验
echo ==========================================================
echo.
python day01_api_smoke.py --json
if errorlevel 1 goto failed

echo.
echo ----------------------------------------------------------
echo   结果同时保存在：exp_records\day01_api_smoke.json
echo ----------------------------------------------------------
pause
exit /b 0

:no_script
echo [错误] 没找到 day01_api_smoke.py
echo.
echo 请把这个文件复制到本目录：
echo   来源：E:\桌面\DOING\大模型\day01_api_smoke.py
echo   目标：%~dp0
pause
exit /b 1

:no_env
echo [错误] 没找到 .env 文件
echo.
echo 请在下面这个目录新建 .env，内容三行：
echo   %~dp0
echo.
echo   LLM_API_KEY=sk-你的key
echo   LLM_BASE_URL=https://api.deepseek.com/v1
echo   LLM_MODEL=deepseek-chat
echo.
echo 建 .env 的方法：
echo  记事本 - 文件 - 另存为 - 定位到上面的目录
echo  文件名填    ".env"     注意要带英文双引号
echo  保存类型选  「所有文件」
echo  编码选      UTF-8
pause
exit /b 1

:failed
echo.
echo [失败] 上面有报错。对照：
echo   401 = Key 错或没生效      402 = 余额不足
echo   404 = 地址或模型名写错     网络不通 = 代理没开
pause
exit /b 1
