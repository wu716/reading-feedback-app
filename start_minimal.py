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
    
    # 检查环境变量
    logger.info("🔍 检查环境变量...")
    required_vars = ['DEEPSEEK_API_KEY', 'SECRET_KEY', 'ENVIRONMENT']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("❌ 缺少必需的环境变量:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        logger.error("\n🔧 请在Railway项目设置中添加这些环境变量:")
        logger.error("1. 登录 https://railway.app/")
        logger.error("2. 选择您的项目")
        logger.error("3. 进入 Settings > Variables")
        logger.error("4. 添加以下变量:")
        logger.error("   DEEPSEEK_API_KEY = YOUR_DEEPSEEK_API_KEY_HERE")
        logger.error("   SECRET_KEY = K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
        logger.error("   ENVIRONMENT = production")
        sys.exit(1)
    
    logger.info("✅ 环境变量检查通过")
    
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
