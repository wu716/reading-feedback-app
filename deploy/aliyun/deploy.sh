#!/usr/bin/env bash
# 阿里云 ECS 一键部署（需已安装 Docker 与 Docker Compose）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "请先复制 env.production.example 为 .env 并填写配置："
  echo "  cp env.production.example .env"
  exit 1
fi

echo ">>> 构建并启动服务..."
docker compose up -d --build

echo ">>> 等待健康检查..."
sleep 5
curl -sf "http://localhost:${APP_PORT:-8000}/health" && echo "" || true

echo ">>> 部署完成。请配置 Nginx 反向代理与 HTTPS 证书。"
