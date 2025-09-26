# PowerShell 启动脚本
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "🚀 启动读书笔记实践反馈系统" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# 检查 Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python 版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python 未找到，请检查安装" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# 检查 API Key
if (-not $env:DEEPSEEK_API_KEY) {
    Write-Host "⚠️  请先设置 DeepSeek API Key:" -ForegroundColor Yellow
    Write-Host "PowerShell: `$env:DEEPSEEK_API_KEY='your-key'" -ForegroundColor Cyan
    Write-Host "CMD: set DEEPSEEK_API_KEY=your-key" -ForegroundColor Cyan
    Write-Host ""
    $apiKey = Read-Host "请输入你的 API Key"
    if ($apiKey) {
        $env:DEEPSEEK_API_KEY = $apiKey
        Write-Host "✅ API Key 已设置" -ForegroundColor Green
    } else {
        Write-Host "❌ 未设置 API Key，应用可能无法正常工作" -ForegroundColor Red
    }
} else {
    Write-Host "✅ API Key 已配置" -ForegroundColor Green
}

Write-Host ""
Write-Host "📱 应用将在以下地址启动：" -ForegroundColor Cyan
Write-Host "   前端页面: http://localhost:8000" -ForegroundColor White
Write-Host "   API文档: http://localhost:8000/docs" -ForegroundColor White
Write-Host "   健康检查: http://localhost:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "按 Ctrl+C 停止应用" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green

# 启动应用
try {
    python run_utf8.py
} catch {
    Write-Host "❌ 启动失败: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "按回车键退出"
}

