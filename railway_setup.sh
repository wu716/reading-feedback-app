#!/bin/bash
# Railway 环境变量一键设置脚本

echo "🚀 Railway 环境变量配置脚本"
echo "================================"
echo ""

# 检查 Railway CLI 是否安装
if ! command -v railway &> /dev/null
then
    echo "❌ Railway CLI 未安装"
    echo ""
    echo "请先安装 Railway CLI:"
    echo "  npm install -g @railway/cli"
    echo ""
    exit 1
fi

echo "✅ Railway CLI 已安装"
echo ""

# 检查是否已登录
if ! railway whoami &> /dev/null
then
    echo "❌ 未登录 Railway"
    echo ""
    echo "请先登录:"
    echo "  railway login"
    echo ""
    exit 1
fi

echo "✅ 已登录 Railway"
echo ""

# 读取 DEEPSEEK_API_KEY
echo "📝 请输入您的 DeepSeek API 密钥:"
echo "   (可在 https://platform.deepseek.com/api_keys 获取)"
read -p "DEEPSEEK_API_KEY: " DEEPSEEK_KEY

if [ -z "$DEEPSEEK_KEY" ]; then
    echo "❌ API 密钥不能为空"
    exit 1
fi

# 设置环境变量
echo ""
echo "🔧 正在设置环境变量..."
echo ""

railway variables set DEEPSEEK_API_KEY="$DEEPSEEK_KEY"
railway variables set SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
railway variables set ENVIRONMENT="production"

echo ""
echo "✅ 环境变量设置完成!"
echo ""
echo "📋 已设置的变量:"
railway variables list
echo ""

# 询问是否立即部署
read -p "是否立即部署到 Railway? (y/n): " DEPLOY

if [ "$DEPLOY" = "y" ] || [ "$DEPLOY" = "Y" ]; then
    echo ""
    echo "🚀 开始部署..."
    railway up
else
    echo ""
    echo "💡 稍后可以使用以下命令部署:"
    echo "   railway up"
fi

echo ""
echo "✅ 配置完成!"
echo ""
echo "📖 查看部署日志:"
echo "   railway logs"
echo ""
echo "🌐 打开应用:"
echo "   railway open"
echo ""

