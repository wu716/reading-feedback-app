#!/usr/bin/env python3
"""
Railway 专用启动脚本
优化网络连接和启动流程
"""

import os
import sys
import logging
import time

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """检查环境变量"""
    logger.info("🔍 检查环境变量...")
    
    required_vars = {
        'DEEPSEEK_API_KEY': 'DeepSeek API密钥',
        'SECRET_KEY': '应用安全密钥'
    }
    
    missing = []
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"{var} ({desc})")
            logger.warning(f"⚠️  {var}: 未设置")
        else:
            # 隐藏敏感信息
            if 'KEY' in var and len(value) > 12:
                display_value = f"{value[:8]}...{value[-4:]}"
            else:
                display_value = "***"
            logger.info(f"✅ {var}: {display_value}")
    
    if missing:
        logger.warning(f"⚠️  缺少环境变量: {', '.join(missing)}")
        logger.warning("\n📝 Railway 环境变量配置步骤:")
        logger.warning("1. 访问 https://railway.app/dashboard")
        logger.warning("2. 选择您的项目")
        logger.warning("3. 进入 'Variables' 标签")
        logger.warning("4. 添加以下变量:")
        logger.warning("   DEEPSEEK_API_KEY=<您的API密钥>")
        logger.warning("   SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
        logger.warning("   ENVIRONMENT=production")
        logger.warning("\n⚠️  应用将继续启动，但某些功能可能不可用")
        return False
    
    return True

def test_network():
    """测试网络连接"""
    logger.info("🌐 测试网络连接...")
    try:
        import socket
        socket.setdefaulttimeout(10)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        logger.info("✅ 网络连接正常")
        return True
    except Exception as e:
        logger.warning(f"⚠️  网络测试失败: {e}")
        logger.warning("应用将继续启动...")
        return False

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🚀 启动读书笔记应用 (Railway 优化版)")
    logger.info("=" * 60)
    
    # 检查环境变量（但不阻止启动）
    env_ok = check_environment()
    if not env_ok:
        logger.warning("⚠️  环境变量检查有问题，但继续启动...")
    
    # 测试网络（非阻塞）
    test_network()
    
    # 设置环境变量
    os.environ.setdefault('ENVIRONMENT', 'production')
    
    # 数据库配置
    if not os.getenv('DATABASE_URL'):
        os.environ['DATABASE_URL'] = 'sqlite:///./app.db'
        logger.info("📁 数据库: SQLite (本地)")
    else:
        logger.info("🐘 数据库: PostgreSQL (云端)")
    
    # 获取端口（Railway 自动设置）
    port = int(os.getenv('PORT', 8000))
    host = '0.0.0.0'
    
    logger.info(f"🌐 服务器配置:")
    logger.info(f"   Host: {host}")
    logger.info(f"   Port: {port}")
    logger.info(f"   Environment: {os.getenv('ENVIRONMENT')}")
    logger.info("=" * 60)
    
    # 移除启动延迟，加快启动速度
    # logger.info("⏳ 等待服务初始化...")
    # time.sleep(2)
    
    try:
        logger.info("🚀 正在启动 Uvicorn 服务器...")
        import uvicorn
        from main import app
        
        # 启动应用 - 增加超时配置
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            timeout_keep_alive=75,
            timeout_graceful_shutdown=30
        )
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
