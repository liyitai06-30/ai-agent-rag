@echo off
setlocal
title ai-agent-rag - 运行评测
cd /d "%~dp0"

if not exist "eval\questions.txt" goto no_q
if not exist "evidenceqa\eval_run.py" goto no_script

cd /d "%~dp0evidenceqa"
if not exist ".venv\Scripts\python.exe" goto no_venv
call ".venv\Scripts\activate.bat"

echo ==========================================================
echo   第 1 轮：混合检索（BM25 + 向量）
echo ==========================================================
echo.
python eval_run.py --questions "%~dp0eval\questions.txt" --mode hybrid
if errorlevel 1 goto stop

echo.
echo ==========================================================
echo   第 2 轮：纯向量检索
echo ==========================================================
echo.
python eval_run.py --questions "%~dp0eval\questions.txt" --mode vector

echo.
echo ----------------------------------------------------------
echo   两轮结果已存到 eval\ 目录（results_*.md）
echo   对比两轮的 Recall@5 / Hit@5 / MRR，那就是你的第一组真实数字
echo ----------------------------------------------------------
pause
exit /b 0

:stop
echo.
echo [中断] 题目校验没通过，按上面的提示改 eval\questions.txt 再跑
pause
exit /b 1

:no_q
echo [错误] 找不到 eval\questions.txt
echo.
echo 请把 questions_template.txt 复制到下面这个位置，并改名为 questions.txt：
echo   %~dp0eval\questions.txt
pause
exit /b 1

:no_script
echo [错误] 找不到 evidenceqa\eval_run.py
echo 请把 eval_run.py 复制到：%~dp0evidenceqa\
pause
exit /b 1

:no_venv
echo [提示] 还没安装环境，请先双击 1_安装环境.bat
pause
exit /b 1
