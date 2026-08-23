import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator


def _is_production() -> bool:
    """统一判断生产环境（兼容 ENV / ENVIRONMENT 两种写法）"""
    env = os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development"
    return env.lower() == "production"


class Settings(BaseSettings):
    # 应用配置
    app_name: str = "读书反馈系统"

    # 环境
    ENV: str = "development"
    DEBUG: bool = True
    environment: str = "development"

    # 数据库（优先 DATABASE_URL，兼容 database_url）
    DATABASE_URL: str = "sqlite:///./app.db"
    database_url: str = "sqlite:///./app.db"

    # 安全
    REQUIRE_AUTH: bool = False
    secret_key: str = "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 20160  # 14天

    # AI
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ai_daily_limit: int = 3
    ai_extract_daily_limit: int = 2

    # 注册控制（生产默认关闭公开注册，见 ProductionSettings）
    registration_open: bool = True
    invite_code: str = ""

    # 邮件（国内推荐阿里云 DirectMail / 腾讯企业邮）
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    # 跨域（生产环境填写实际域名，逗号分隔）
    CORS_ORIGINS: str = "*"

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def effective_database_url(self) -> str:
        url = self.DATABASE_URL or self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_registration_allowed(self) -> bool:
        if (self.invite_code or "").strip():
            return True
        return self.registration_open


def get_settings() -> Settings:
    if _is_production():
        return ProductionSettings()
    return DevelopmentSettings()


class DevelopmentSettings(Settings):
    DEBUG: bool = True
    REQUIRE_AUTH: bool = False
    environment: str = "development"


class ProductionSettings(Settings):
    DEBUG: bool = False
    REQUIRE_AUTH: bool = True
    environment: str = "production"
    registration_open: bool = False
    ai_daily_limit: int = 3
    ai_extract_daily_limit: int = 2


settings = get_settings()
