#!/usr/bin/env python3
"""
生产环境启动脚本
用于 Railway、Render 等云平台部署
"""

import os
import sys
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """检查环境变量"""
    required_vars = ['DEEPSEEK_API_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"缺少必需的环境变量: {', '.join(missing_vars)}")
        logger.error("请在 Railway 项目设置中添加这些环境变量")
        sys.exit(1)
    
    logger.info("✅ 环境变量检查通过")

def get_database_url():
    """获取数据库URL"""
    # Railway 会自动提供 DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        logger.info("使用 PostgreSQL 数据库")
        return database_url
    else:
        logger.info("使用 SQLite 数据库")
        return "sqlite:///./app.db"

def main():
    """主函数"""
    logger.info("🚀 启动读书笔记实践反馈系统 (生产环境)")
    logger.info("=" * 50)
    
    # 检查环境变量
    check_environment()
    
    # 设置环境变量
    os.environ['DATABASE_URL'] = get_database_url()
    os.environ['ENVIRONMENT'] = os.getenv('ENVIRONMENT', 'production')
    
    # 导入并启动应用
    try:
        import uvicorn
        from main import app
        
        # 获取端口（Railway 等平台会设置 PORT 环境变量）
        port = int(os.getenv('PORT', 8000))
        host = os.getenv('HOST', '0.0.0.0')
        
        logger.info(f"📱 应用将在以下地址启动：")
        logger.info(f"   本地访问: http://localhost:{port}")
        logger.info(f"   外部访问: https://your-app.railway.app")
        logger.info("=" * 50)
        
        # 启动应用
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except ImportError as e:
        logger.error(f"导入错误: {e}")
        logger.error("请确保已安装所有依赖: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
