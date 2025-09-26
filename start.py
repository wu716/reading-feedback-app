#!/usr/bin/env python3
"""
启动脚本 - 读书笔记实践反馈系统
"""
import os
import sys
import subprocess
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_python_version():
    """检查 Python 版本"""
    if sys.version_info < (3, 8):
        logger.error("需要 Python 3.8 或更高版本")
        sys.exit(1)
    logger.info(f"Python 版本: {sys.version}")

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import fastapi
        import sqlalchemy
        import pydantic
        logger.info("核心依赖检查通过")
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.info("请运行: pip install -r requirements.txt")
        sys.exit(1)

def setup_environment():
    """设置环境变量"""
    if not os.path.exists('.env'):
        if os.path.exists('.env.example'):
            logger.info("复制 .env.example 到 .env")
            subprocess.run(['cp', '.env.example', '.env'], check=True)
        else:
            logger.warning("未找到 .env 文件，将使用默认配置")
    
    # 设置默认环境变量
    os.environ.setdefault('ENVIRONMENT', 'development')
    os.environ.setdefault('DEBUG', 'true')
    os.environ.setdefault('DATABASE_URL', 'sqlite:///./app.db')

def create_directories():
    """创建必要的目录"""
    directories = ['logs', 'data']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    logger.info("目录结构检查完成")

def start_application():
    """启动应用"""
    logger.info("正在启动读书笔记实践反馈系统...")
    
    try:
        # 启动 FastAPI 应用
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
        logger.info("应用已停止")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("读书笔记实践反馈系统启动器")
    logger.info("=" * 50)
    
    # 检查环境
    check_python_version()
    check_dependencies()
    
    # 设置环境
    setup_environment()
    create_directories()
    
    # 启动应用
    start_application()

if __name__ == "__main__":
    main()
