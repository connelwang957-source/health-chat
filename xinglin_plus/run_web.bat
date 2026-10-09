@echo off
REM 杏林大健康 AI 问答系统 —— Web 服务（FastAPI）
REM
REM 启动后打开浏览器：
REM   对话界面   http://127.0.0.1:8000/            （支持深/浅色主题切换）
REM   依赖探活   http://127.0.0.1:8000/health
REM   接口文档   http://127.0.0.1:8000/docs
REM   问答接口   POST http://127.0.0.1:8000/v1/chat   {"question": "感冒有什么症状?"}
REM
REM 监听地址说明：这里用 127.0.0.1（只允许本机访问）——最稳，无需放行防火墙。
REM 开发文档 §8.3 的示例是 0.0.0.0（供局域网访问），但在 Windows 上常被防火墙拦截，
REM 表现为浏览器一直转圈/超时。确实需要外部访问时，把下面的 127.0.0.1 改成 0.0.0.0，
REM 并在弹出的防火墙提示中选"允许访问"。
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe，请先在本目录创建虚拟环境并安装依赖。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m xinglin.interfaces.web --mode agent --host 127.0.0.1 --port 8000
echo.
echo [服务已退出] 若上方有报错信息，请把窗口内容截图反馈。
pause
