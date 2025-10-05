@echo off
echo 🚀 启动读书反馈应用
echo ========================================

cd /d D:\projects\reading-feedback-app
echo ✅ 已切换到项目目录: %CD%

REM 检查环境变量
if "%DEEPSEEK_API_KEY%"=="" (
    echo ❌ 请设置 DEEPSEEK_API_KEY 环境变量
    echo.
    echo 设置方法：
    echo 1. 在 CMD 中运行: set DEEPSEEK_API_KEY=your_api_key
    echo 2. 创建 .env 文件并添加: DEEPSEEK_API_KEY=your_api_key
    echo.
    echo 示例：
    echo set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
    echo.
    pause
    exit /b 1
)

echo ✅ 环境变量已设置
echo.
echo 📱 应用将在以下地址启动：
echo    前端页面: http://localhost:8000
echo    API文档: http://localhost:8000/docs
echo    Self-talk: http://localhost:8000/static/self_talk/index.html
echo.
echo 按 Ctrl+C 停止应用
echo ========================================
echo.

"C:\Users\冉冉\AppData\Local\Programs\Python\Python313\python.exe" start_secure.py

pause
