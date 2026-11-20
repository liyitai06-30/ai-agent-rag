@echo off
setlocal
title [1/3] ai-agent-rag - 安装环境
cd /d "%~dp0"

if not exist "evidenceqa\app\main.py" goto no_code

echo ==========================================================
echo   第 1 / 3 步：创建 Python 虚拟环境
echo ==========================================================
cd /d "%~dp0evidenceqa"

if exist ".venv\Scripts\python.exe" goto have_venv
echo 正在创建 .venv ...
python -m venv .venv
if errorlevel 1 goto venv_fail
goto pip_install

:have_venv
echo 检测到已有虚拟环境，跳过创建。

:pip_install
echo.
echo ==========================================================
echo   第 2 / 3 步：安装依赖（6 个包，约 1 分钟）
echo ==========================================================
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 goto pip_fail

echo.
echo ==========================================================
echo   第 3 / 3 步：跑一遍自检测试
echo ==========================================================
python -m pytest -q
echo.
echo ----------------------------------------------------------
echo   安装完成！
echo   下一步：回到上一级目录，双击  2_导入演示数据.bat
echo ----------------------------------------------------------
pause
exit /b 0

:no_code
echo [错误] 没找到 evidenceqa\app\main.py
echo.
echo 当前目录：%~dp0
echo 正确结构应该是：
echo   %~dp0evidenceqa\app\main.py
echo.
echo 请把上游代码里的 evidenceqa 文件夹整个放到本目录下，再运行本文件。
pause
exit /b 1

:venv_fail
echo [错误] 创建虚拟环境失败
echo.
echo 常见原因：Python 没装，或没加入 PATH。
echo 处理办法：另开一个命令行窗口，执行  python --version  看是否正常。
pause
exit /b 1

:pip_fail
echo [错误] 依赖安装失败，多半是网络问题
echo.
echo 处理办法（二选一）：
echo   1. 先打开你的代理软件，再重新双击本文件
echo   2. 用记事本打开本文件，把 pip 那一行改成带代理的写法：
echo      python -m pip install --proxy http://127.0.0.1:7897 -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
pause
exit /b 1
