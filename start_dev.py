#!/usr/bin/env python3
"""
开发环境启动脚本 - 自动配置并启动应用
"""
import os
import sys
import subprocess
import getpass

def setup_environment():
    """设置开发环境"""
    print("🚀 读书笔记实践反馈系统 - 开发环境启动")
    print("=" * 50)
    
    # 检查是否已设置 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠️  未检测到 DeepSeek API Key")
        print("\n请选择设置方式：")
        print("1. 手动设置环境变量")
        print("2. 现在输入 API Key（临时设置）")
        
        choice = input("\n请选择 (1/2): ").strip()
        
        if choice == "2":
            api_key = getpass.getpass("请输入你的 DeepSeek API Key: ")
            if api_key:
                os.environ["DEEPSEEK_API_KEY"] = api_key
                print("✅ API Key 已设置（仅当前会话有效）")
            else:
                print("❌ API Key 不能为空")
                sys.exit(1)
        else:
            print("\n请手动设置环境变量：")
            print("PowerShell: $env:DEEPSEEK_API_KEY='your-key'")
            print("CMD: set DEEPSEEK_API_KEY=your-key")
            sys.exit(1)
    else:
        print("✅ DeepSeek API Key 已配置")

def check_dependencies():
    """检查依赖"""
    print("\n🔍 检查依赖...")
    try:
        import fastapi
        import sqlalchemy
        import openai
        print("✅ 核心依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("正在安装依赖...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ 依赖安装完成")

def start_application():
    """启动应用"""
    print("\n🚀 启动应用...")
    try:
        import uvicorn
        from main import app
        
        print("📱 应用将在以下地址启动：")
        print("   主页: http://localhost:8000")
        print("   API文档: http://localhost:8000/docs")
        print("   健康检查: http://localhost:8000/health")
        print("\n按 Ctrl+C 停止应用")
        print("=" * 50)
        
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

def main():
    """主函数"""
    setup_environment()
    check_dependencies()
    start_application()

if __name__ == "__main__":
    main()
