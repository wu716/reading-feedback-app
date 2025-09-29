#!/usr/bin/env python3
"""
环境变量验证脚本
用于检查Railway环境变量是否正确设置
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

def check_environment_variables():
    """检查环境变量"""
    logger.info("🔍 检查环境变量配置...")
    
    required_vars = {
        'DEEPSEEK_API_KEY': 'DeepSeek API密钥',
        'SECRET_KEY': '应用密钥',
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
            logger.info(f"✅ {var}: {display_value} ({description})")
            present_vars.append(var)
        else:
            logger.error(f"❌ {var}: 未设置 ({description})")
            missing_vars.append(var)
    
    # 检查可选变量
    optional_vars = {
        'PORT': '端口号',
        'DATABASE_URL': '数据库URL',
        'HOST': '主机地址'
    }
    
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            logger.info(f"ℹ️  {var}: {value} ({description})")
        else:
            logger.info(f"ℹ️  {var}: 未设置，将使用默认值 ({description})")
    
    return len(missing_vars) == 0, missing_vars, present_vars

def main():
    """主函数"""
    logger.info("🚀 Railway环境变量验证工具")
    logger.info("=" * 50)
    
    success, missing_vars, present_vars = check_environment_variables()
    
    logger.info("=" * 50)
    
    if success:
        logger.info("🎉 所有必需的环境变量都已正确设置！")
        logger.info("✅ 应用应该能够正常启动")
        
        # 测试AI服务配置
        try:
            from app.config import settings
            if settings.deepseek_api_key:
                logger.info("🤖 AI服务已配置，可以进行智能分析")
            else:
                logger.warning("⚠️  AI服务未配置，将使用基础功能")
        except Exception as e:
            logger.error(f"❌ 配置加载失败: {e}")
            
    else:
        logger.error("❌ 缺少必需的环境变量:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        
        logger.error("\n🔧 请在Railway项目设置中添加这些环境变量:")
        logger.error("1. 登录 https://railway.app/")
        logger.error("2. 选择您的项目")
        logger.error("3. 进入 Settings > Variables")
        logger.error("4. 添加以下变量:")
        logger.error("   DEEPSEEK_API_KEY = sk-ea8257f565da4484b9f50a9e4bf10c00")
        logger.error("   SECRET_KEY = K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
        logger.error("   ENVIRONMENT = production")
        
        sys.exit(1)

if __name__ == "__main__":
    main()
