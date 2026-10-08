@echo off
chcp 65001 >nul
title 杏林大健康 AI 问答系统 - 前端页面
cd /d %~dp0
echo [启动] 在默认浏览器中打开前端页面...
start "" "%~dp0index.html"
echo [提示] 请确认后端已启动（双击后端.bat）。
echo [提示] 本窗口将在数秒后自动关闭。
ping -n 5 127.0.0.1 >nul
