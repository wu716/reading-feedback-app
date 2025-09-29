#!/usr/bin/env python3
"""
Railway 最小化启动脚本
不依赖AI服务，专注于基本功能
"""

import os
import sys
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    logger.info("🚀 启动读书笔记应用 (最小化版本)")
    
    # 设置环境变量
    os.environ['ENVIRONMENT'] = 'production'
    
    # 如果没有 DATABASE_URL，使用 SQLite
    if not os.getenv('DATABASE_URL'):
        os.environ['DATABASE_URL'] = 'sqlite:///./app.db'
        logger.info("📁 使用 SQLite 数据库")
    else:
        logger.info("🐘 使用 PostgreSQL 数据库")
    
    # 获取端口
    port = int(os.getenv('PORT', 8000))
    host = '0.0.0.0'
    
    logger.info(f"🌐 启动服务器: {host}:{port}")
    logger.info(f"🔧 环境变量检查:")
    logger.info(f"   PORT: {port}")
    logger.info(f"   DATABASE_URL: {'已设置' if os.getenv('DATABASE_URL') else '未设置'}")
    logger.info(f"   DEEPSEEK_API_KEY: {'已设置' if os.getenv('DEEPSEEK_API_KEY') else '未设置'}")
    
    try:
        import uvicorn
        from main import app
        
        # 启动应用
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
