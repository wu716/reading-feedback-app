#!/bin/bash
echo "========================================"
echo "🚀 启动读书反馈应用"
echo "========================================"
echo

# 检查环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ 未找到 DEEPSEEK_API_KEY 环境变量"
    echo
    echo "请先设置环境变量："
    echo "export DEEPSEEK_API_KEY=your-api-key-here"
    echo
    echo "或者运行：python set_api_key.py"
    echo
    exit 1
fi

echo "✅ 找到有效的 API Key"
echo
echo "📱 应用将在以下地址启动："
echo "   前端页面: http://localhost:8000"
echo "   API文档: http://localhost:8000/docs"
echo "   Self-talk: http://localhost:8000/static/self_talk/index.html"
echo
echo "按 Ctrl+C 停止应用"
echo "========================================"
echo

# 启动应用
python start_with_env.py
