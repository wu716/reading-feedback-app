@echo off
REM 使用 PowerShell 设置 UTF-8 编码
powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"

echo 🚀 启动读书笔记实践反馈系统
echo ========================================

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未找到，请检查安装
    pause
    exit /b 1
)

REM 检查 API Key
if "%DEEPSEEK_API_KEY%"=="" (
    echo ⚠️  请先设置 DeepSeek API Key:
    echo PowerShell: $env:DEEPSEEK_API_KEY='your-key'
    echo CMD: set DEEPSEEK_API_KEY=your-key
    echo.
    set /p api_key="请输入你的 API Key: "
    if not "%api_key%"=="" (
        set DEEPSEEK_API_KEY=%api_key%
        echo ✅ API Key 已设置
    ) else (
        echo ❌ 未设置 API Key，应用可能无法正常工作
    )
)

echo.
echo 📱 应用将在以下地址启动：
echo    前端页面: http://localhost:8000
echo    API文档: http://localhost:8000/docs
echo    健康检查: http://localhost:8000/health
echo.
echo 按 Ctrl+C 停止应用
echo ========================================

REM 启动应用
python run_utf8.py

pause

