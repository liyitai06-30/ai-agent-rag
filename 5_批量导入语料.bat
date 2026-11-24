@echo off
setlocal
title ai-agent-rag - 批量导入语料
cd /d "%~dp0"

if not exist "evidenceqa\app\main.py" goto no_code
if not exist "evidenceqa\import_corpus.py" goto no_script
if not exist "corpus" goto no_corpus
if not exist ".env" goto no_env

cd /d "%~dp0evidenceqa"
if not exist ".venv\Scripts\python.exe" goto no_venv
call ".venv\Scripts\activate.bat"

echo ==========================================================
echo   批量导入语料：清空旧数据 -^> 导入 corpus 目录
echo ==========================================================
echo.
python import_corpus.py --corpus "%~dp0corpus" --reset
if errorlevel 1 goto failed

echo.
echo ----------------------------------------------------------
echo   完成。下一步：双击 3_启动服务.bat 重启服务，让新数据生效
echo ----------------------------------------------------------
pause
exit /b 0

:no_code
echo [错误] 没找到 evidenceqa\app\main.py
echo 当前目录：%~dp0
pause
exit /b 1

:no_script
echo [错误] 没找到 evidenceqa\import_corpus.py
echo 请把 import_corpus.py 复制到：
echo   %~dp0evidenceqa\
pause
exit /b 1

:no_corpus
echo [错误] 没找到 corpus 文件夹
echo.
echo 请在本目录下新建 corpus，并把挑选好的 .md 文件放进去：
echo   %~dp0corpus\
pause
exit /b 1

:no_env
echo [提示] 本目录还没有 .env
echo 如果是第一次用 embedding API，先按教程把 .env 建好再运行
pause
exit /b 1

:no_venv
echo [提示] 还没安装环境，请先双击 1_安装环境.bat
pause
exit /b 1

:failed
echo.
echo [失败] 导入过程出错，看上面的提示
echo 常见原因：
echo   1. .env 里 EMBEDDING_PROVIDER=api 但 key 或地址写错
echo   2. 网络不通（先开代理再重试）
echo   3. corpus 里的文件不是 UTF-8 编码
pause
exit /b 1
