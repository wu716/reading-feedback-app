# 使用 Python 3.11 官方镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖 - 使用国内镜像加速
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 分阶段安装依赖 - 先安装小包，再安装大包
RUN pip install --no-cache-dir --timeout=300 --retries=5 \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    sqlalchemy==2.0.35 \
    alembic==1.12.1 \
    python-multipart==0.0.6 \
    python-jose[cryptography]==3.3.0 \
    passlib[bcrypt]==1.7.4 \
    pydantic>=2.9.2 \
    pydantic-settings>=2.0.3 \
    openai==1.3.7 \
    python-dotenv==1.0.0 \
    tenacity==8.2.3 \
    email-validator>=2.2.0 \
    cryptography==41.0.7 \
    requests==2.31.0 \
    APScheduler==3.10.4

# 单独安装 vosk 和 pydub（可能较大）
RUN pip install --no-cache-dir --timeout=600 --retries=10 \
    vosk==0.3.45 \
    pydub==0.25.1

# 复制应用代码
COPY . .

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# 暴露端口
EXPOSE 8000

# 健康检查 - 简化版本，让Railway自己处理
# HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
#     CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 启动命令
CMD ["python", "start_railway.py"]

