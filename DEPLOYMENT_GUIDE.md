# 🚀 Google Cloud Run 部署指南

## 📋 部署步骤

### 1. 创建 Google Cloud 项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 记录项目 ID

### 2. 启用必要的 API

在 Google Cloud Console 中启用：
- Cloud Run API
- Cloud Build API
- Container Registry API

### 3. 创建服务账户

1. 转到 IAM 和管理 → 服务账户
2. 创建服务账户，角色选择：
   - Cloud Run 管理员
   - Cloud Build 编辑者
   - 存储管理员
3. 创建密钥（JSON 格式）并下载

### 4. 配置 GitHub Secrets

在 GitHub 仓库设置中添加以下 Secrets：

```
GCP_PROJECT_ID=你的项目ID
GCP_SA_KEY=服务账户密钥JSON内容
DEEPSEEK_API_KEY=你的DeepSeek API密钥
SECRET_KEY=32位随机字符串
```

### 5. 推送代码触发部署

```bash
git add .
git commit -m "Add deployment workflow"
git push origin main
```

### 6. 访问应用

部署完成后，访问 Cloud Run 服务 URL：
- 格式：`https://reading-feedback-app-xxx-uc.a.run.app`
- 在手机浏览器中打开即可使用

## 🔧 手动部署（备选方案）

如果 GitHub Actions 失败，可以手动部署：

### 1. 使用 Google Cloud Console

1. 转到 Cloud Run
2. 点击"创建服务"
3. 选择"从源代码构建"
4. 连接 GitHub 仓库
5. 配置环境变量
6. 部署

### 2. 使用 Cloud Shell

1. 打开 [Cloud Shell](https://shell.cloud.google.com/)
2. 克隆仓库
3. 运行部署命令

## 📱 移动端访问

部署完成后，在手机浏览器中访问：
- 应用会自动适配移动端
- 支持触摸操作
- 响应式设计

## 🔒 安全配置

- API 密钥通过环境变量安全传递
- 使用 HTTPS 加密传输
- 支持 CORS 跨域请求
- 自动健康检查

## 💰 费用说明

- Cloud Run：按使用量计费，有免费额度
- Cloud Build：每月前 120 分钟免费
- 预计月费用：< $5（轻量使用）
