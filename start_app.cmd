@echo off
echo 🚀 启动读书反馈应用
echo ========================================

cd /d "%~dp0"
echo ✅ 已切换到项目目录: %CD%

REM 检查 .env 文件是否存在
if not exist ".env" (
    echo ❌ 未找到 .env 文件
    echo.
    echo 🔧 请确保在项目根目录创建 .env 文件，包含以下内容：
    echo    DEEPSEEK_API_KEY=your-deepseek-api-key
    echo    YOUR_OTHER_API_KEY=your-other-api-key
    echo.
    pause
    exit /b 1
)

echo ✅ 找到 .env 文件
echo.
echo 📱 应用将在以下地址启动：
echo    前端页面: http://localhost:8000
echo    API文档: http://localhost:8000/docs
echo    Self-talk: http://localhost:8000/static/self_talk/index.html
echo.
echo 按 Ctrl+C 停止应用
echo ========================================
echo.

python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动失败
    echo 🔧 故障排除：
    echo 1. 检查端口 8000 是否被占用
    echo 2. 检查 Python 环境是否正确
    echo 3. 检查所有依赖是否已安装: pip install -r requirements.txt
    echo.
)

pause