import os
from pydantic_settings import BaseSettings  # pyright: ignore[reportMissingImports]
from typing import Optional
import base64
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    # 应用配置
    app_name: str = "Reading Feedback App"
    debug: bool = False
    environment: str = "development"
    
    # 数据库配置
    database_url: str = "sqlite:///./app.db"
    
    # JWT 配置
    secret_key: str = "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # AI 配置 - 从环境变量或加密文件读取
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 从环境变量获取配置
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.database_url = os.getenv("DATABASE_URL", self.database_url)
        self.secret_key = os.getenv("SECRET_KEY", self.secret_key)
        
        # 安全获取 API Key
        self.deepseek_api_key = self._get_deepseek_api_key()
        
        # 生产环境设置
        if self.environment == "production":
            self.debug = False
            # 确保生产环境有必要的配置
            if not self.secret_key or self.secret_key == "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG":
                raise ValueError("生产环境必须设置 SECRET_KEY 环境变量")
    
    def _get_deepseek_api_key(self) -> str:
        """安全获取 DeepSeek API Key"""
        # 1. 优先从环境变量获取
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key and api_key != "your-deepseek-api-key-here":
            return api_key
        
        # 2. 从加密文件获取
        try:
            encrypted_file = "encrypted_api_key.txt"
            key_file = "encryption.key"
            
            if os.path.exists(encrypted_file) and os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    key = f.read()
                
                with open(encrypted_file, 'r') as f:
                    encrypted_b64 = f.read().strip()
                
                f = Fernet(key)
                encrypted = base64.b64decode(encrypted_b64.encode())
                decrypted = f.decrypt(encrypted)
                return decrypted.decode()
        except Exception as e:
            print(f"⚠️  从加密文件读取 API Key 失败: {e}")
        
        # 3. 从 .env 文件获取（开发环境）
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if api_key and api_key != "your-deepseek-api-key-here":
                return api_key
        except:
            pass
        
        # 4. 提示用户设置
        print("⚠️  未找到有效的 DeepSeek API Key")
        print("请运行: python manage_api_key.py 设置 API Key")
        return ""
    
    # 匿名化配置
    anonymize_after_days: int = 30  # 用户删除后30天进行匿名化
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# 全局设置实例
settings = Settings()