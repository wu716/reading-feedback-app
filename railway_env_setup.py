#!/usr/bin/env python3
"""
Railway 环境变量配置助手
帮助验证和设置必需的环境变量
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
    """检查必需的环境变量"""
    logger.info("🔍 检查环境变量配置...")
    
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
    
    # 检查可选变量
    optional_vars = {
        'DATABASE_URL': '数据库连接URL',
        'PORT': '服务器端口'
    }
    
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}: {value}")
        else:
            logger.info(f"ℹ️  {var}: 未设置 ({description}) - 将使用默认值")
    
    return missing_vars, present_vars

def generate_railway_config():
    """生成Railway配置指令"""
    logger.info("\n🔧 Railway 环境变量配置指令:")
    logger.info("=" * 50)
    logger.info("1. 访问 https://railway.app/")
    logger.info("2. 登录您的账户")
    logger.info("3. 选择您的项目")
    logger.info("4. 点击 'Settings' 标签页")
    logger.info("5. 找到 'Variables' 部分")
    logger.info("6. 点击 'New Variable' 按钮")
    logger.info("7. 添加以下变量:")
    logger.info("")
    logger.info("变量名: DEEPSEEK_API_KEY")
    logger.info("变量值: 您的DeepSeek API密钥")
    logger.info("")
    logger.info("变量名: SECRET_KEY")
    logger.info("变量值: K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
    logger.info("")
    logger.info("变量名: ENVIRONMENT")
    logger.info("变量值: production")
    logger.info("")
    logger.info("8. 保存配置后，Railway会自动重新部署应用")
    logger.info("=" * 50)

def test_ai_connection():
    """测试AI连接"""
    logger.info("\n🤖 测试AI服务连接...")
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        logger.error("❌ DEEPSEEK_API_KEY 未设置，无法测试AI连接")
        return False
    
    try:
        import requests
        
        # 测试API连接
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
            
    except ImportError:
        logger.error("❌ requests库未安装，无法测试AI连接")
        return False
    except Exception as e:
        logger.error(f"❌ AI连接测试失败: {e}")
        return False

def main():
    """主函数"""
    logger.info("🚀 Railway 环境变量配置助手")
    logger.info("=" * 40)
    
    # 检查环境变量
    missing_vars, present_vars = check_environment_variables()
    
    if missing_vars:
        logger.error(f"\n❌ 缺少 {len(missing_vars)} 个必需的环境变量")
        generate_railway_config()
        
        # 提供本地测试选项
        logger.info("\n💡 本地测试选项:")
        logger.info("如果您想在本地测试，可以创建 .env 文件:")
        logger.info("1. 复制 .env.template 为 .env")
        logger.info("2. 填入您的实际API密钥")
        logger.info("3. 运行 python -m dotenv python main.py")
        
        return False
    else:
        logger.info(f"\n✅ 所有必需的环境变量都已设置 ({len(present_vars)}/3)")
        
        # 测试AI连接
        if 'DEEPSEEK_API_KEY' in present_vars:
            ai_working = test_ai_connection()
            if ai_working:
                logger.info("🎉 环境配置完成，AI功能可用！")
                return True
            else:
                logger.warning("⚠️  环境变量已设置，但AI连接失败")
                logger.warning("请检查API密钥是否正确")
                return False
        else:
            logger.info("🎉 环境配置完成！")
            return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

