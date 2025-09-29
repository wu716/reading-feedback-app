# 🚂 Railway 部署指南

## 📋 部署步骤

### 1. 注册 Railway 账户
- 访问：https://railway.app/
- 使用 GitHub 账户登录

### 2. 连接 GitHub 仓库
- 点击 "New Project"
- 选择 "Deploy from GitHub repo"
- 选择您的仓库：`wu716/reading-feedback-app`

### 3. 配置环境变量
在 Railway 项目设置中添加：
```
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY_HERE
SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
ENVIRONMENT=production
```

### 4. 自动部署
- Railway 会自动检测 Dockerfile
- 自动构建和部署
- 获得公网访问 URL

## 💰 费用
- **免费额度**：每月 $5 信用额度
- **轻量使用**：完全免费
- **无需信用卡**

## 📱 访问
部署完成后获得 URL：
```
https://reading-feedback-app-production.up.railway.app
```
