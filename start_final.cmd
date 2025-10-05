@echo off
echo 🚀 启动读书反馈应用（最终版）
echo ========================================

cd /d D:\projects\reading-feedback-app
echo ✅ 已切换到项目目录: %CD%

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

"C:\Users\冉冉\AppData\Local\Programs\Python\Python313\python.exe" start_final.py

pause
