import os
import base64
from cryptography.fernet import Fernet
from typing import Optional

class SecureConfig:
    """安全配置管理 - 保护 API Key"""
    
    def __init__(self):
        # 从环境变量获取加密密钥
        self.encryption_key = os.getenv("ENCRYPTION_KEY")
        if not self.encryption_key:
            # 生成新的加密密钥（仅用于开发）
            self.encryption_key = Fernet.generate_key().decode()
            print(f"⚠️  开发环境加密密钥: {self.encryption_key}")
            print("请将此密钥添加到环境变量 ENCRYPTION_KEY 中")
    
    def encrypt_api_key(self, api_key: str) -> str:
        """加密 API Key"""
        f = Fernet(self.encryption_key.encode())
        encrypted = f.encrypt(api_key.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt_api_key(self, encrypted_key: str) -> str:
        """解密 API Key"""
        f = Fernet(self.encryption_key.encode())
        encrypted = base64.b64decode(encrypted_key.encode())
        return f.decrypt(encrypted).decode()
    
    def get_deepseek_api_key(self) -> Optional[str]:
        """安全获取 DeepSeek API Key"""
        # 1. 优先从环境变量读取
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            return api_key
        
        # 2. 从加密文件读取
        encrypted_file = "encrypted_api_key.txt"
        if os.path.exists(encrypted_file):
            try:
                with open(encrypted_file, 'r') as f:
                    encrypted_key = f.read().strip()
                return self.decrypt_api_key(encrypted_key)
            except Exception as e:
                print(f"解密 API Key 失败: {e}")
        
        # 3. 提示用户输入
        print("⚠️  未找到 DeepSeek API Key")
        print("请选择以下方式之一：")
        print("1. 设置环境变量: $env:DEEPSEEK_API_KEY='your-key'")
        print("2. 使用加密存储（推荐）")
        
        return None

# 全局安全配置实例
secure_config = SecureConfig()

