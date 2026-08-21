# 使用 Python 3.11 官方镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ffmpeg：pydub/Vosk 转写 m4a、webm 等非 WAV 格式时必需
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 与 requirements.txt 保持一致（避免 openai/httpx 版本冲突）
RUN pip install --no-cache-dir --timeout=600 --retries=5 -r requirements.txt

# 复制应用代码
COPY . .

# 录音上传目录。不要 USER app：compose 会把 named volume 挂到 /app/uploads，
# 非 root 进程写不进去，Self-talk 上传会直接 500。
RUN mkdir -p /app/uploads/self_talks

# 暴露端口
EXPOSE 8000

# 健康检查 - 简化版本，让Railway自己处理
# HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
#     CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 启动命令
CMD ["python", "start_railway.py"]

