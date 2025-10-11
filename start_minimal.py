#!/usr/bin/env python3
"""
Railway 最小化启动脚本
不依赖AI服务，专注于基本功能
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

def main():
    """主函数"""
    logger.info("🚀 启动读书笔记应用 (Railway版本)")
    
    # 检查环境变量
    logger.info("🔍 检查环境变量...")
    required_vars = {
        'DEEPSEEK_API_KEY': 'DeepSeek AI API密钥',
        'SECRET_KEY': '应用安全密钥',
        'ENVIRONMENT': '运行环境'
    }
    
    missing_vars = []
    present_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # 隐藏敏感信息
            if 'KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            logger.info(f"✅ {var}: {display_value}")
            present_vars.append(var)
        else:
            logger.warning(f"❌ {var}: 未设置 ({description})")
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"\n❌ 缺少 {len(missing_vars)} 个必需的环境变量")
        logger.error("\n🔧 Railway 环境变量配置指南:")
        logger.error("1. 访问 https://railway.app/")
        logger.error("2. 登录您的账户")
        logger.error("3. 选择您的项目")
        logger.error("4. 点击 'Settings' 标签页")
        logger.error("5. 找到 'Variables' 部分")
        logger.error("6. 点击 'New Variable' 按钮")
        logger.error("7. 添加以下变量:")
        logger.error("")
        logger.error("变量名: DEEPSEEK_API_KEY")
        logger.error("变量值: 您的DeepSeek API密钥")
        logger.error("")
        logger.error("变量名: SECRET_KEY")
        logger.error("变量值: K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
        logger.error("")
        logger.error("变量名: ENVIRONMENT")
        logger.error("变量值: production")
        logger.error("")
        logger.error("8. 保存配置后，Railway会自动重新部署应用")
        logger.error("\n💡 提示: 您也可以运行 'python railway_env_setup.py' 获取详细配置指南")
        sys.exit(1)
    
    logger.info(f"✅ 环境变量检查通过 ({len(present_vars)}/3)")
    
    # 测试AI连接
    # if 'DEEPSEEK_API_KEY' in present_vars:
    #     logger.info("🤖 测试AI服务连接...")
    #     try:
    #         import requests
    #         
    #         api_key = os.getenv('DEEPSEEK_API_KEY')
    #         headers = {
    #             'Authorization': f'Bearer {api_key}',
    #             'Content-Type': 'application/json'
    #         }
    #         
    #         data = {
    #             "model": "deepseek-chat",
    #             "messages": [{"role": "user", "content": "Hello"}],
    #             "max_tokens": 5
    #         }
    #         
    #         response = requests.post(
    #             'https://api.deepseek.com/v1/chat/completions',
    #             headers=headers,
    #             json=data,
    #             timeout=10
    #         )
    #         
    #         if response.status_code == 200:
    #             logger.info("✅ AI服务连接正常")
    #         else:
    #             logger.warning(f"⚠️  AI服务连接失败: {response.status_code}")
    #             logger.warning("应用将继续运行，但AI功能可能不可用")
    #             
    #     except Exception as e:
    #         logger.warning(f"⚠️  AI连接测试失败: {e}")
    #         logger.warning("应用将继续运行，但AI功能可能不可用")
    
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
    
    # 减少启动等待时间
    logger.info("⏳ 等待应用初始化完成...")
    time.sleep(1)
    
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
