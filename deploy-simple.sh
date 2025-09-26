#!/bin/bash
# 简化的 Google Cloud 部署脚本

echo "🚀 开始部署到 Google Cloud Run"
echo "=================================="

# 检查必要的环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ 错误: 请设置 DEEPSEEK_API_KEY 环境变量"
    echo "Windows PowerShell: \$env:DEEPSEEK_API_KEY='your-api-key'"
    exit 1
fi

if [ -z "$GCP_PROJECT_ID" ]; then
    echo "❌ 错误: 请设置 GCP_PROJECT_ID 环境变量"
    echo "Windows PowerShell: \$env:GCP_PROJECT_ID='your-project-id'"
    exit 1
fi

echo "✅ 环境变量检查通过"
echo "项目ID: $GCP_PROJECT_ID"
echo "API Key: ${DEEPSEEK_API_KEY:0:10}..."

# 生成随机密钥
SECRET_KEY=$(openssl rand -hex 32)
echo "✅ 生成随机密钥"

echo ""
echo "📋 部署配置:"
echo "- 项目: $GCP_PROJECT_ID"
echo "- 服务: reading-feedback-app"
echo "- 区域: asia-east1"
echo "- 端口: 8000"
echo ""

echo "🔧 开始构建和部署..."
echo "请确保已安装 Google Cloud CLI 并已登录"
echo ""

# 构建镜像
echo "1. 构建 Docker 镜像..."
docker build -t gcr.io/$GCP_PROJECT_ID/reading-feedback-app:latest .

# 推送镜像
echo "2. 推送镜像到 Google Container Registry..."
docker push gcr.io/$GCP_PROJECT_ID/reading-feedback-app:latest

# 部署到 Cloud Run
echo "3. 部署到 Cloud Run..."
gcloud run deploy reading-feedback-app \
  --image gcr.io/$GCP_PROJECT_ID/reading-feedback-app:latest \
  --platform managed \
  --region asia-east1 \
  --allow-unauthenticated \
  --set-env-vars DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY \
  --set-env-vars SECRET_KEY=$SECRET_KEY \
  --set-env-vars ENVIRONMENT=production \
  --port 8000

echo ""
echo "🎉 部署完成！"
echo "访问应用: https://reading-feedback-app-xxx-uc.a.run.app"
echo "在手机浏览器中打开即可使用"
