# -*- coding: utf-8 -*-
"""
安全的 API Key 设置脚本
"""
import os
import sys

def main():
    print("🔐 DeepSeek API Key 设置工具")
    print("=" * 40)
    
    # 获取用户输入
    api_key = input("请输入您的 DeepSeek API Key: ").strip()
    
    if not api_key:
        print("❌ 未输入 API Key")
        sys.exit(1)
    
    if api_key == "your-deepseek-api-key-here":
        print("❌ 请使用真实的 API Key，不是示例值")
        sys.exit(1)
    
    # 设置环境变量
    os.environ["DEEPSEEK_API_KEY"] = api_key
    
    print("✅ API Key 已设置到当前会话")
    print()
    print("📝 永久设置方法：")
    print("PowerShell: $env:DEEPSEEK_API_KEY='your-real-api-key'")
    print("CMD: set DEEPSEEK_API_KEY=your-real-api-key")
    print()
    print("🚀 现在可以启动应用了：")
    print("python start_with_env.py")

if __name__ == "__main__":
    main()
