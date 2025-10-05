#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单启动脚本 - 避免 PowerShell 权限问题
"""
import os
import sys

def main():
    print("🚀 启动读书反馈应用")
    print("=" * 50)
    
    # 设置环境变量
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 请设置 DEEPSEEK_API_KEY 环境变量")
        print("方法1: 在命令行运行: set DEEPSEEK_API_KEY=your_key")
        print("方法2: 创建 .env 文件并添加: DEEPSEEK_API_KEY=your_key")
        sys.exit(1)
    
    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["SECRET_KEY"] = os.getenv("SECRET_KEY", "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
    os.environ["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "development")
    os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    
    print("✅ 环境变量已设置")
    print()
    print("📱 应用将在以下地址启动：")
    print("   前端页面: http://localhost:8000")
    print("   API文档: http://localhost:8000/docs")
    print("   Self-talk: http://localhost:8000/static/self_talk/index.html")
    print()
    print("按 Ctrl+C 停止应用")
    print("=" * 50)
    print()
    
    # 启动应用
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
