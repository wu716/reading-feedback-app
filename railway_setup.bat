@echo off
chcp 65001 >nul
REM Railway 环境变量一键设置脚本 (Windows)

echo.
echo ===================================
echo Railway 环境变量配置脚本
echo ===================================
echo.

REM 检查 Railway CLI 是否安装
where railway >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Railway CLI 未安装
    echo.
    echo 请先安装 Railway CLI:
    echo   npm install -g @railway/cli
    echo.
    pause
    exit /b 1
)

echo [成功] Railway CLI 已安装
echo.

REM 检查是否已登录
railway whoami >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未登录 Railway
    echo.
    echo 请先登录:
    echo   railway login
    echo.
    pause
    exit /b 1
)

echo [成功] 已登录 Railway
echo.

REM 读取 DEEPSEEK_API_KEY
echo [提示] 请输入您的 DeepSeek API 密钥:
echo        (可在 https://platform.deepseek.com/api_keys 获取)
set /p DEEPSEEK_KEY="DEEPSEEK_API_KEY: "

if "%DEEPSEEK_KEY%"=="" (
    echo [错误] API 密钥不能为空
    pause
    exit /b 1
)

REM 设置环境变量
echo.
echo [执行] 正在设置环境变量...
echo.

railway variables set DEEPSEEK_API_KEY="%DEEPSEEK_KEY%"
railway variables set SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
railway variables set ENVIRONMENT="production"

echo.
echo [成功] 环境变量设置完成!
echo.
echo [列表] 已设置的变量:
railway variables list
echo.

REM 询问是否立即部署
set /p DEPLOY="是否立即部署到 Railway? (y/n): "

if /i "%DEPLOY%"=="y" (
    echo.
    echo [部署] 开始部署...
    railway up
) else (
    echo.
    echo [提示] 稍后可以使用以下命令部署:
    echo        railway up
)

echo.
echo [成功] 配置完成!
echo.
echo [命令] 查看部署日志:
echo        railway logs
echo.
echo [命令] 打开应用:
echo        railway open
echo.

pause

