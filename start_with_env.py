# -*- coding: utf-8 -*-
"""
带环境变量检查的启动脚本
"""
import os
import sys

def main():
    print("🚀 启动读书笔记实践反馈系统")
    print("=" * 40)
    
    # 检查 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "your-deepseek-api-key-here":
        print("❌ 未找到有效的 DeepSeek API Key")
        print("AI 功能是应用的核心功能，必须设置有效的 API Key")
        print()
        print("请设置环境变量:")
        print("PowerShell: $env:DEEPSEEK_API_KEY='your-real-api-key'")
        print("CMD: set DEEPSEEK_API_KEY=your-real-api-key")
        print()
        print("或者运行: python set_api_key.py")
        print()
        
        # 尝试从用户输入获取
        api_key = input("请输入您的 DeepSeek API Key: ").strip()
        if not api_key or api_key == "your-deepseek-api-key-here":
            print("❌ 无效的 API Key，应用无法启动")
            sys.exit(1)
        
        os.environ["DEEPSEEK_API_KEY"] = api_key
        print("✅ API Key 已设置")
    else:
        print("✅ 找到有效的 API Key")
    
    print()
    print("📱 应用将在以下地址启动：")
    print("   前端页面: http://localhost:8000")
    print("   API文档: http://localhost:8000/docs")
    print("   健康检查: http://localhost:8000/health")
    print()
    print("按 Ctrl+C 停止应用")
    print("=" * 40)
    
    # 启动应用
    try:
        import uvicorn
        from main import app
        
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 应用已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
