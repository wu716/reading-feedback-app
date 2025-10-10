import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    # 应用配置
    app_name: str = "读书反馈系统"
    
    # 基础配置
    ENV: str = "development"
    DEBUG: bool = True
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./app.db"
    
    # 安全配置
    REQUIRE_AUTH: bool = False  # 开发环境可关闭认证
    secret_key: str = "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7天 = 7 * 24 * 60
    
    # API密钥
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    environment: str = "development"
    database_url: str = "sqlite:///./app.db"
    
    # 邮件服务配置（可选）
    SMTP_HOST: str = ""  # 如 "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    
    # Pydantic v2 配置
    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"  # 忽略额外字段而不是报错
    )

# 根据环境选择配置
def get_settings():
    env = os.getenv("ENV", "development")
    if env == "production":
        return ProductionSettings()
    else:
        return DevelopmentSettings()

class DevelopmentSettings(Settings):
    DEBUG: bool = True
    REQUIRE_AUTH: bool = False  # 开发环境不强制认证

class ProductionSettings(Settings):
    DEBUG: bool = False
    REQUIRE_AUTH: bool = True  # 生产环境强制认证

settings = get_settings()