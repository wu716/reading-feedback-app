#!/bin/bash
# Google Cloud Run 部署脚本

echo "🚀 Google Cloud Run 部署脚本"
echo "=============================="

# 检查 gcloud 是否安装
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI 未安装"
    echo "请访问: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# 检查是否已登录
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ 请先登录 Google Cloud"
    echo "运行: gcloud auth login"
    exit 1
fi

# 获取项目 ID
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ 请设置 Google Cloud 项目"
    echo "运行: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "📋 项目 ID: $PROJECT_ID"

# 启用必要的 API
echo "🔧 启用必要的 API..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com

# 构建 Docker 镜像
echo "🏗️ 构建 Docker 镜像..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/reading-feedback-app

if [ $? -ne 0 ]; then
    echo "❌ Docker 镜像构建失败"
    exit 1
fi

echo "✅ Docker 镜像构建成功"

# 部署到 Cloud Run
echo "🚀 部署到 Cloud Run..."
gcloud run deploy reading-feedback-app \
    --image gcr.io/$PROJECT_ID/reading-feedback-app \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --port 8000 \
    --memory 512Mi \
    --cpu 1 \
    --max-instances 10 \
    --set-env-vars ENVIRONMENT=production

if [ $? -ne 0 ]; then
    echo "❌ Cloud Run 部署失败"
    exit 1
fi

echo "✅ Cloud Run 部署成功"

# 获取服务 URL
SERVICE_URL=$(gcloud run services describe reading-feedback-app --region=asia-east1 --format="value(status.url)")
echo "🌐 服务 URL: $SERVICE_URL"

echo "🎉 部署完成！"
echo "📱 在手机浏览器中访问: $SERVICE_URL"
echo ""
echo "⚠️  注意: 请确保已设置环境变量和密钥"
echo "运行: ./deploy/setup-secrets.sh"

