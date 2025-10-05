@echo off
cd /d D:\projects\reading-feedback-app

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 设置环境变量（如果需要）
if "%DEEPSEEK_API_KEY%"=="" (
    echo 请设置环境变量 DEEPSEEK_API_KEY
    echo 例如: set DEEPSEEK_API_KEY=your-api-key-here
    pause
    exit /b 1
)

REM 启动应用
python main.py

pause
