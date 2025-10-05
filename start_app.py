#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户友好的启动脚本 - 安全且简单
"""
import os
import sys
import uvicorn
import logging
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
env_file = ".env.development"  # 默认开发环境
if len(sys.argv) > 1 and sys.argv[1] == "production":
    env_file = ".env.production"

load_dotenv(env_file)

# 启动应用
from main import app
import uvicorn

def main():
    print("🚀 启动读书反馈应用")
    print("=" * 50)
    
    # 确保在正确的项目目录下运行
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    logger.info(f"📁 切换到项目目录: {project_root}")
    logger.info(f"✅ 当前目录: {os.getcwd()}")

    # 检查环境变量
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 请设置 DEEPSEEK_API_KEY 环境变量")
        print()
        print("🔧 快速设置方法：")
        print("1. 在 CMD 中运行以下命令（替换为您的实际密钥）：")
        print("   set DEEPSEEK_API_KEY=sk-your-actual-api-key-here")
        print()
        print("2. 然后重新运行此脚本")
        print()
        print("💡 或者创建 .env 文件（推荐）：")
        print("   在项目根目录创建 .env 文件，内容如下：")
        print("   DEEPSEEK_API_KEY=sk-your-actual-api-key-here")
        print()
        print("📖 详细说明请查看：SECURE_START_GUIDE.md")
        sys.exit(1)
    
    # 设置环境变量
    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["SECRET_KEY"] = os.getenv("SECRET_KEY", "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
    os.environ["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "development")
    os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    
    logger.info("✅ 环境变量已设置")
    
    # 检查关键文件
    logger.info("🔍 检查关键文件...")
    critical_files = [
        "main.py",
        "app/models.py",
        "app/database.py",
        "app/config.py",
        "app/self_talk/router.py",
        "app/self_talk/speech_recognition.py",
        "static/index.html",
        "static/self_talk/index.html"
    ]
    
    missing_files = []
    for file_path in critical_files:
        if os.path.exists(file_path):
            logger.info(f"✅ {file_path}")
        else:
            logger.error(f"❌ {file_path} 不存在")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ 缺少关键文件: {', '.join(missing_files)}")
        print("请检查项目完整性")
        sys.exit(1)
    
    # 检查 Vosk 模型
    vosk_model_path = "models/vosk-model-small-cn-0.22"
    if os.path.exists(vosk_model_path):
        logger.info(f"✅ Vosk 模型存在: {vosk_model_path}")
    else:
        logger.warning(f"⚠️ Vosk 模型不存在: {vosk_model_path}")
        logger.info("语音识别功能将不可用，但不影响其他功能")
    
    # 检查 uploads 目录
    uploads_dir = "uploads"
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir)
        logger.info(f"✅ 创建 uploads 目录: {uploads_dir}")
    
    uploads_self_talks_dir = "uploads/self_talks"
    if not os.path.exists(uploads_self_talks_dir):
        os.makedirs(uploads_self_talks_dir)
        logger.info(f"✅ 创建 uploads/self_talks 目录: {uploads_self_talks_dir}")
    
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
        logger.error(f"❌ 启动失败: {e}")
        print("\n🔧 故障排除：")
        print("1. 检查端口 8000 是否被占用")
        print("2. 检查 Python 环境是否正确")
        print("3. 检查所有依赖是否已安装: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
