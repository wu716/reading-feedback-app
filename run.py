#!/usr/bin/env python3
"""
简单启动脚本
"""
import os
import sys

def main():
    print("🚀 启动读书笔记实践反馈系统")
    print("=" * 40)
    
    # 检查 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠️  请先设置 DeepSeek API Key:")
        print("PowerShell: $env:DEEPSEEK_API_KEY='your-key'")
        print("CMD: set DEEPSEEK_API_KEY=your-key")
        print("\n或者直接输入你的 API Key:")
        api_key = input("API Key: ").strip()
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key
            print("✅ API Key 已设置")
        else:
            print("❌ 未设置 API Key，应用可能无法正常工作")
    
    print("\n📱 应用将在以下地址启动：")
    print("   前端页面: http://localhost:8000")
    print("   API文档: http://localhost:8000/docs")
    print("   健康检查: http://localhost:8000/health")
    print("\n按 Ctrl+C 停止应用")
    print("=" * 40)
    
    # 启动应用
    try:
        import uvicorn
        from main import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 应用已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
