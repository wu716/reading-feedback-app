# 🚂 Railway 部署指南

> **最新更新**: 2025-10-13 - 已优化网络连接和部署配置

## ⚡ 快速开始

### 方法 1: 自动化脚本（推荐 - Windows）

```bash
# Windows 用户
railway_setup.bat

# Linux/Mac 用户
chmod +x railway_setup.sh
./railway_setup.sh
```

### 方法 2: 手动配置

## 📋 详细部署步骤

### 1. 注册 Railway 账户
- 访问：https://railway.app/
- 使用 GitHub 账户登录（推荐）

### 2. 安装 Railway CLI（可选但推荐）

```bash
# 使用 npm 安装
npm install -g @railway/cli

# 验证安装
railway --version

# 登录
railway login
```

### 3. 连接 GitHub 仓库

#### 方法 A: 通过 Dashboard（网页界面）
1. 访问 https://railway.app/dashboard
2. 点击 "New Project"
3. 选择 "Deploy from GitHub repo"
4. 选择您的仓库：`reading-feedback-app`
5. Railway 会自动开始构建

#### 方法 B: 通过 CLI（命令行）
```bash
# 在项目目录中
railway init

# 连接到 GitHub
railway link
```

### 4. 配置环境变量 ⚙️

#### 必需的环境变量：

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek AI API 密钥 | `sk-xxxxxxxxxxxxxx` |
| `SECRET_KEY` | 应用安全密钥 | `K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG` |
| `ENVIRONMENT` | 运行环境 | `production` |

#### 设置方式 A: Dashboard
1. 进入项目页面
2. 点击 "Variables" 标签
3. 点击 "New Variable"
4. 逐个添加上述变量

#### 设置方式 B: CLI
```bash
railway variables set DEEPSEEK_API_KEY="your-api-key-here"
railway variables set SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
railway variables set ENVIRONMENT="production"

# 验证
railway variables list
```

### 5. 部署应用 🚀

#### 自动部署（推荐）
- 推送代码到 GitHub 后自动触发：
```bash
git add .
git commit -m "deploy: update to railway"
git push origin main
```

#### 手动部署
```bash
# 使用 CLI
railway up

# 或重新部署
railway redeploy
```

### 6. 监控部署状态 📊

```bash
# 查看实时日志
railway logs --follow

# 查看最近 100 行
railway logs --lines 100

# 只看错误
railway logs | grep ERROR
```

## ✅ 部署验证

### 成功标志：

在日志中看到以下信息表示成功：
```
🚀 启动读书笔记应用 (Railway 优化版)
✅ DEEPSEEK_API_KEY: 已设置
✅ SECRET_KEY: 已设置
✅ 网络连接正常
🚀 正在启动 Uvicorn 服务器...
```

### 访问应用：

```bash
# 自动打开浏览器
railway open

# 或获取 URL
railway domain
```

典型 URL 格式：
```
https://reading-feedback-app-production.up.railway.app
```

## 🔧 优化配置说明

### 已优化的网络配置

本项目已针对 Railway 部署进行了以下优化：

1. **Dockerfile 优化**:
   - ✅ pip 超时时间: 300-600 秒
   - ✅ 自动重试: 5-10 次
   - ✅ 分阶段安装依赖
   - ✅ 添加 .dockerignore 减少构建时间

2. **启动脚本优化** (`start_railway.py`):
   - ✅ 网络连接预检
   - ✅ 环境变量验证
   - ✅ 详细错误日志
   - ✅ 超时配置优化

3. **Railway 配置** (`railway.json`):
   - ✅ 健康检查超时: 100 秒
   - ✅ 启动等待期: 180 秒
   - ✅ 自动重启: 最多 5 次

## 🐛 常见问题解决

### 问题 1: 部署时网络超时

**症状**:
```
ERROR: Read timed out
```

**解决方案**:
- 已在 Dockerfile 中配置超时和重试
- 如仍失败，可在 Railway Settings → Build Settings 中增加构建超时时间

### 问题 2: 环境变量未生效

**检查**:
```bash
railway variables
```

**重新设置**:
```bash
railway variables set DEEPSEEK_API_KEY="new-value"
```

### 问题 3: 构建失败

**查看详细日志**:
```bash
railway logs --deployment latest
```

**本地测试 Docker**:
```bash
docker build -t test-app .
docker run -p 8000:8000 \
  -e DEEPSEEK_API_KEY="your-key" \
  -e SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG" \
  -e ENVIRONMENT="production" \
  test-app
```

### 问题 4: 健康检查失败

**验证健康端点**:
```bash
# 部署后测试
curl https://your-app.up.railway.app/health
```

**本地测试**:
```bash
python start_railway.py
# 另一个终端
curl http://localhost:8000/health
```

## 💰 费用说明

### Railway 定价
- **免费额度**: 每月 $5 信用额度
- **Hobby 计划**: $5/月（适合个人项目）
- **Pro 计划**: $20/月（适合团队）

### 本项目预估成本
- **轻量使用**: 完全免费（免费额度足够）
- **中度使用**: ~$2-5/月
- **无需信用卡**（免费额度内）

### 成本优化建议
1. 使用 SQLite（无需额外数据库服务）
2. 设置休眠策略（无流量时自动休眠）
3. 监控资源使用情况

## 📚 相关文档

- [Railway 故障排查指南](./RAILWAY_TROUBLESHOOTING.md) - 详细的问题诊断和解决方案
- [Railway 官方文档](https://docs.railway.app/)
- [Docker 优化指南](https://docs.docker.com/develop/dev-best-practices/)

## 🔄 更新部署

### 推送更新
```bash
git add .
git commit -m "update: feature xyz"
git push origin main
# Railway 自动重新部署
```

### 强制重新部署
```bash
railway redeploy
```

### 回滚到之前版本
```bash
# 在 Dashboard 中
Project → Deployments → 选择之前的部署 → Redeploy
```

## 🆘 获取帮助

### 查看日志
```bash
# 实时日志
railway logs --follow

# 保存日志到文件
railway logs > deployment.log
```

### 进入容器调试
```bash
railway shell
```

### 联系支持
- Railway Discord: https://discord.gg/railway
- 官方文档: https://docs.railway.app/
- 状态页: https://status.railway.app/

## 🎯 下一步

部署成功后，您可以：

1. **配置自定义域名**
   ```bash
   railway domain
   ```

2. **设置 CI/CD 流程**
   - GitHub Actions 自动部署
   - 自动化测试

3. **添加数据库**
   ```bash
   railway add
   # 选择 PostgreSQL
   ```

4. **监控和分析**
   - 查看应用指标
   - 设置告警

---

**最后更新**: 2025-10-13  
**维护者**: AI Assistant  
**支持**: 如遇问题请查看 [RAILWAY_TROUBLESHOOTING.md](./RAILWAY_TROUBLESHOOTING.md)
