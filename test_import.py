#!/usr/bin/env python3
"""
测试导入和基本功能
"""
import sys
import traceback

def test_imports():
    print("🔍 测试导入...")
    
    try:
        print("1. 测试基础模块...")
        import os
        import json
        print("   ✅ 基础模块 OK")
        
        print("2. 测试 FastAPI...")
        import fastapi
        print("   ✅ FastAPI OK")
        
        print("3. 测试 SQLAlchemy...")
        import sqlalchemy
        print("   ✅ SQLAlchemy OK")
        
        print("4. 测试 Pydantic...")
        import pydantic
        print("   ✅ Pydantic OK")
        
        print("5. 测试应用配置...")
        from app.config import settings
        print("   ✅ 应用配置 OK")
        
        print("6. 测试数据库...")
        from app.database import create_tables
        print("   ✅ 数据库 OK")
        
        print("7. 测试模型...")
        from app.models import User, Action
        print("   ✅ 模型 OK")
        
        print("8. 测试路由...")
        from app.routers import auth, actions
        print("   ✅ 路由 OK")
        
        print("9. 测试主应用...")
        from main import app
        print("   ✅ 主应用 OK")
        
        print("\n🎉 所有导入测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False

def test_config():
    print("\n🔧 测试配置...")
    try:
        from app.config import settings
        print(f"   应用名称: {settings.app_name}")
        print(f"   环境: {settings.environment}")
        print(f"   数据库: {settings.database_url}")
        print(f"   AI Key: {'已设置' if settings.deepseek_api_key else '未设置'}")
        return True
    except Exception as e:
        print(f"   ❌ 配置测试失败: {e}")
        return False

def main():
    print("🚀 读书笔记实践反馈系统 - 诊断工具")
    print("=" * 50)
    
    # 测试导入
    if not test_imports():
        print("\n❌ 导入测试失败，请检查依赖安装")
        return
    
    # 测试配置
    if not test_config():
        print("\n❌ 配置测试失败")
        return
    
    print("\n✅ 所有测试通过！应用可以正常启动")
    print("\n📝 下一步:")
    print("1. 设置 DeepSeek API Key: $env:DEEPSEEK_API_KEY='your-key'")
    print("2. 启动应用: python run.py")

if __name__ == "__main__":
    main()

