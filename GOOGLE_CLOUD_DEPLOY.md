# 🚀 Google Cloud Run 部署指南

## 📋 前置要求

1. **Google Cloud 账户** - 有免费额度
2. **gcloud CLI** - 已安装并配置
3. **项目 ID** - 已创建 Google Cloud 项目

## 🔧 安装和配置

### 1. 安装 gcloud CLI
```bash
# Windows (使用 PowerShell)
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe
```

### 2. 登录和配置
```bash
# 登录 Google Cloud
gcloud auth login

# 设置项目 ID
gcloud config set project YOUR_PROJECT_ID

# 验证配置
gcloud config list
```

## 🚀 部署步骤

### 方法1: 使用部署脚本（推荐）
```bash
# 给脚本执行权限
chmod +x deploy-gcloud.sh

# 运行部署脚本
./deploy-gcloud.sh
```

### 方法2: 手动部署
```bash
# 1. 启用 API
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com

# 2. 构建镜像
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/reading-feedback-app

# 3. 部署到 Cloud Run
gcloud run deploy reading-feedback-app \
    --image gcr.io/YOUR_PROJECT_ID/reading-feedback-app \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --port 8000 \
    --memory 512Mi \
    --cpu 1
```

## 🔐 设置环境变量和密钥

### 1. 创建密钥
```bash
# 设置项目环境变量
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID

# 运行密钥设置脚本
chmod +x deploy/setup-secrets.sh
./deploy/setup-secrets.sh
```

### 2. 手动设置密钥
```bash
# 创建 DeepSeek API Key 密钥
echo "your-deepseek-api-key" | gcloud secrets create deepseek-api-key --data-file=-

# 创建应用密钥
openssl rand -base64 32 | gcloud secrets create app-secret-key --data-file=-
```

## 📱 访问应用

部署完成后，您会获得一个 HTTPS URL：
```
https://reading-feedback-app-xxxxx-uc.a.run.app
```

在手机浏览器中访问此链接即可使用应用。

## 🔧 故障排除

### 常见问题
1. **权限错误**: 确保已启用必要的 API
2. **构建失败**: 检查 Dockerfile 和 requirements.txt
3. **部署失败**: 检查项目 ID 和区域设置

### 查看日志
```bash
# 查看 Cloud Run 日志
gcloud logs read --service=reading-feedback-app --limit=50
```

## 💰 费用说明

- **Cloud Run**: 按使用量计费，有免费额度
- **Cloud Build**: 每月前 120 分钟免费
- **Secret Manager**: 每月前 6 个密钥免费

## 🎯 下一步优化

1. **自定义域名**: 绑定自己的域名
2. **CDN 加速**: 使用 Cloud CDN
3. **监控告警**: 设置 Cloud Monitoring
4. **自动备份**: 配置 Cloud SQL 备份

