#!/usr/bin/env python3
"""阿里云 ECS / 容器服务生产启动脚本"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def check_environment() -> bool:
    required = {
        "DEEPSEEK_API_KEY": "DeepSeek API 密钥",
        "SECRET_KEY": "JWT 签名密钥",
        "DATABASE_URL": "数据库连接串（PostgreSQL 或 SQLite）",
    }
    missing = [f"{k} ({v})" for k, v in required.items() if not os.getenv(k)]
    if missing:
        logger.error("缺少必需环境变量: %s", ", ".join(missing))
        return False

    if os.getenv("SECRET_KEY") == "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG":
        logger.warning("SECRET_KEY 仍为默认值，生产环境请更换为随机长字符串")

    if not os.getenv("SMTP_HOST"):
        logger.warning("未配置 SMTP，邮件提醒功能将不可用")

    return True


def main():
    logger.info("=" * 60)
    logger.info("启动读书反馈应用（阿里云生产环境）")
    logger.info("=" * 60)

    os.environ.setdefault("ENVIRONMENT", "production")

    os.makedirs("uploads/self_talks", exist_ok=True)

    if not check_environment():
        sys.exit(1)

    port = int(os.getenv("PORT", "8000"))
    host = "0.0.0.0"

    logger.info("Host: %s  Port: %s  ENV: production", host, port)

    try:
        import uvicorn
        from main import app

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            timeout_keep_alive=75,
            timeout_graceful_shutdown=30,
        )
    except Exception as e:
        logger.error("启动失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
