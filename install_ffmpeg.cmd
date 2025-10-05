@echo off
echo 正在安装 ffmpeg...
echo.

echo 方法 1: 尝试使用 winget 安装
winget install ffmpeg
if %errorlevel% equ 0 (
    echo ✅ ffmpeg 安装成功！
    goto :verify
)

echo.
echo 方法 1 失败，尝试方法 2...
echo 请手动下载并安装 ffmpeg：
echo 1. 访问 https://ffmpeg.org/download.html
echo 2. 下载 Windows 版本
echo 3. 解压到任意目录，如 D:\tools\ffmpeg
echo 4. 将解压后的 bin 目录添加到系统 PATH
echo.
echo 或者使用 Chocolatey:
echo choco install ffmpeg
echo.

:verify
echo 验证安装...
ffmpeg -version
if %errorlevel% equ 0 (
    echo ✅ ffmpeg 验证成功！
    echo 现在可以重启应用并测试 Self-talk 功能了。
) else (
    echo ❌ ffmpeg 未正确安装
    echo 请按照上述步骤手动安装
)

pause
