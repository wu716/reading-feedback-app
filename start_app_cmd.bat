@echo off
chcp 65001 >nul
cd /d D:\projects\reading-feedback-app

echo [执行] 激活虚拟环境...
call .venv\Scripts\activate.bat

REM 设置环境变量（如果需要）
if "%DEEPSEEK_API_KEY%"=="" (
    echo [错误] 请设置环境变量 DEEPSEEK_API_KEY
    echo [示例] set DEEPSEEK_API_KEY=your-api-key-here
    pause
    exit /b 1
)

echo [执行] 启动应用...
python main.py

pause
