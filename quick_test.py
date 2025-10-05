#!/usr/bin/env python3
"""
快速测试脚本
验证环境变量和AI连接是否正常
"""

import os
import sys
import requests
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_environment():
    """测试环境变量"""
    logger.info("🔍 检查环境变量...")
    
    required_vars = {
        'DEEPSEEK_API_KEY': 'DeepSeek AI API密钥',
        'SECRET_KEY': '应用安全密钥',
        'ENVIRONMENT': '运行环境'
    }
    
    all_good = True
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            if 'KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            logger.info(f"✅ {var}: {display_value}")
        else:
            logger.error(f"❌ {var}: 未设置 ({description})")
            all_good = False
    
    return all_good

def test_ai_connection():
    """测试AI连接"""
    logger.info("🤖 测试AI服务连接...")
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        logger.error("❌ DEEPSEEK_API_KEY 未设置，无法测试AI连接")
        return False
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": "Hello, this is a test message."}
            ],
            "max_tokens": 10
        }
        
        response = requests.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ AI服务连接正常")
            return True
        else:
            logger.error(f"❌ AI服务连接失败: {response.status_code}")
            logger.error(f"响应: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ AI连接测试失败: {e}")
        return False

def main():
    """主函数"""
    logger.info("🚀 快速测试 - 读书笔记应用")
    logger.info("=" * 40)
    
    # 测试环境变量
    env_ok = test_environment()
    
    if not env_ok:
        logger.error("\n❌ 环境变量检查失败")
        logger.error("请按照以下步骤配置环境变量:")
        logger.error("1. Railway: 项目设置 > Variables")
        logger.error("2. 本地: 设置环境变量或创建.env文件")
        logger.error("3. 运行: python railway_env_setup.py")
        return False
    
    # 测试AI连接
    ai_ok = test_ai_connection()
    
    if env_ok and ai_ok:
        logger.info("\n🎉 所有测试通过！应用可以正常使用AI功能")
        return True
    else:
        logger.error("\n❌ 测试失败，请检查配置")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
