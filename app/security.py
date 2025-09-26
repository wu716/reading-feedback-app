import os
import base64
from cryptography.fernet import Fernet
from typing import Optional

class SecureConfig:
    """安全配置管理"""
    
    def __init__(self):
        self.encryption_key = os.getenv("ENCRYPTION_KEY")
        if not self.encryption_key:
            # 生成新的加密密钥（仅用于开发环境）
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
    
    def get_api_key(self) -> Optional[str]:
        """获取 API Key（支持多种方式）"""
        # 1. 优先从环境变量读取
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            return api_key
        
        # 2. 从加密文件读取
        encrypted_file = os.getenv("ENCRYPTED_API_KEY_FILE")
        if encrypted_file and os.path.exists(encrypted_file):
            try:
                with open(encrypted_file, 'r') as f:
                    encrypted_key = f.read().strip()
                return self.decrypt_api_key(encrypted_key)
            except Exception as e:
                print(f"解密 API Key 失败: {e}")
        
        return None

# 全局安全配置实例
secure_config = SecureConfig()

