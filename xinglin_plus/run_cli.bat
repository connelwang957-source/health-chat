@echo off
REM 杏林大健康 AI 问答系统 —— 命令行入口
REM 用法：run_cli.bat                      交互式（默认 hybrid）
REM       run_cli.bat -q "感冒有什么症状？"  单次提问
REM       run_cli.bat --mode agent          指定形态
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe，请先在本目录创建虚拟环境并安装依赖。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 main.py %*
pause
