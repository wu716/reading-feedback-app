#!/bin/bash
# 生产环境密钥设置脚本 - 完全安全

echo "🔐 生产环境密钥设置"
echo "===================="

# 检查是否在 Google Cloud 环境
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "❌ 请设置 GOOGLE_CLOUD_PROJECT 环境变量"
    exit 1
fi

# 创建 DeepSeek API Key 密钥
echo "📝 设置 DeepSeek API Key..."
read -s -p "请输入 DeepSeek API Key: " DEEPSEEK_API_KEY
echo

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ API Key 不能为空"
    exit 1
fi

# 创建 Google Secret Manager 密钥
echo "🔑 创建 Google Secret Manager 密钥..."
echo "$DEEPSEEK_API_KEY" | gcloud secrets create deepseek-api-key \
    --data-file=- \
    --replication-policy="automatic" \
    --labels="app=reading-feedback,env=production"

if [ $? -eq 0 ]; then
    echo "✅ DeepSeek API Key 已安全存储到 Google Secret Manager"
else
    echo "❌ 密钥创建失败"
    exit 1
fi

# 创建应用密钥
echo "🔑 创建应用密钥..."
APP_SECRET=$(openssl rand -base64 32)
echo "$APP_SECRET" | gcloud secrets create app-secret-key \
    --data-file=- \
    --replication-policy="automatic" \
    --labels="app=reading-feedback,env=production"

echo "✅ 应用密钥已创建"

# 设置 Cloud Run 服务账户权限
echo "🔐 设置服务账户权限..."
SERVICE_ACCOUNT="reading-feedback-sa@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"

gcloud secrets add-iam-policy-binding deepseek-api-key \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding app-secret-key \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

echo "✅ 权限设置完成"
echo "🎉 生产环境密钥配置完成！"

