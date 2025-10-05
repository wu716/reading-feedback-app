import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    # 基础配置
    ENV: str = "development"
    DEBUG: bool = True
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./app.db"
    
    # 安全配置
    REQUIRE_AUTH: bool = False  # 开发环境可关闭认证
    
    class Config:
        env_file = ".env"

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