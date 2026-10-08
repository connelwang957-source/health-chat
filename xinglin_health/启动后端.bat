@echo off
chcp 65001 >nul
title 杏林大健康 AI 问答系统 - 后端服务
cd /d %~dp0
echo ============================================
echo   杏林大健康 AI 问答系统 · 后端服务
echo   接口地址: http://127.0.0.1:8000
echo   接口文档: http://127.0.0.1:8000/docs
echo   关闭本窗口即停止服务
echo ============================================
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo [提示] 服务已退出。若上方有报错，请检查 .env 配置或 Neo4j 是否启动。
pause
