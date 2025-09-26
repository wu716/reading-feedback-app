#!/usr/bin/env python3
"""
部署前检查脚本
确保所有必要的配置都已准备好
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 8):
        print("❌ Python版本过低，需要3.8+")
        return False
    print(f"✅ Python版本: {sys.version}")
    return True

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        print("✅ 核心依赖已安装")
        return True
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return False

def check_files():
    """检查必要文件"""
    required_files = [
        "main.py",
        "start_production.py",
        "requirements.txt",
        "app/",
        "static/"
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ 缺少文件: {', '.join(missing_files)}")
        return False
    
    print("✅ 所有必要文件存在")
    return True

def check_environment():
    """检查环境变量"""
    required_vars = ["DEEPSEEK_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  缺少环境变量: {', '.join(missing_vars)}")
        print("部署时需要在平台设置中添加这些变量")
        return False
    
    print("✅ 环境变量检查通过")
    return True

def main():
    """主检查函数"""
    print("🔍 部署前检查")
    print("=" * 40)
    
    checks = [
        check_python_version(),
        check_dependencies(),
        check_files(),
        check_environment()
    ]
    
    if all(checks):
        print("\n🎉 所有检查通过！可以开始部署")
        print("\n📋 部署步骤:")
        print("1. 提交代码到Git仓库")
        print("2. 在Railway/Render等平台创建项目")
        print("3. 连接Git仓库")
        print("4. 设置环境变量")
        print("5. 等待部署完成")
        return True
    else:
        print("\n❌ 检查失败，请修复问题后重试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
