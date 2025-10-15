# Railway 部署故障排查指南

## 🚨 紧急问题：Service Unavailable 错误

### 错误表现

```
Attempt #1 failed with service unavailable. Continuing to retry for 19s
Attempt #2 failed with service unavailable. Continuing to retry for 18s
Attempt #3 failed with service unavailable. Continuing to retry for 16s
Attempt #4 failed with service unavailable. Continuing to retry for 12s
Attempt #5 failed with service unavailable. Continuing to retry for 4s
```

### ✅ 已修复的配置（2025-10-15 更新）

我们已经针对这个问题进行了以下优化：

#### 1. 增加健康检查超时时间

```json
{
  "deploy": {
    "healthcheckTimeout": 300,        // 从 100秒 增加到 300秒
    "healthcheckStartPeriod": 300,    // 从 180秒 增加到 300秒
    "healthcheckInterval": 20         // 保持 20秒
  }
}
```

#### 2. 移除严格的环境变量检查

之前：应用会在环境变量缺失时直接退出  
现在：应用会警告但继续启动，这样可以先看到详细的错误日志

#### 3. 统一启动配置

- ✅ `Dockerfile` CMD: `python start_railway.py`
- ✅ `railway.json` startCommand: 已移除（使用 Dockerfile 的默认命令）

#### 4. 加快启动速度

- ✅ 移除了 2 秒的启动延迟
- ✅ 优化了日志输出
- ✅ 非阻塞式的网络测试

### 🔍 诊断步骤

如果仍然遇到此错误，请按以下步骤诊断：

#### 步骤 1：检查环境变量

```bash
# 使用 Railway CLI
railway variables

# 应该看到：
# DEEPSEEK_API_KEY=sk-...
# SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
# ENVIRONMENT=production
```

**如果缺少，立即添加**：

```bash
railway variables set DEEPSEEK_API_KEY="your-api-key-here"
railway variables set SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
railway variables set ENVIRONMENT="production"
```

#### 步骤 2：查看实时日志

```bash
# 跟踪部署日志
railway logs --follow

# 查找关键信息：
# ✅ "🚀 正在启动 Uvicorn 服务器..." - 表示启动成功
# ❌ "❌ 启动失败" - 表示有错误
# ⚠️  "⚠️  环境变量检查有问题" - 检查环境变量
```

#### 步骤 3：测试健康检查端点

```bash
# 获取应用 URL
railway domain

# 测试健康端点（部署成功后）
curl https://your-app.up.railway.app/health

# 预期响应：
# {"status":"healthy","message":"服务就绪"}
```

#### 步骤 4：本地测试

```bash
# 本地测试 Docker 镜像
docker build -t test-app .

docker run -p 8000:8000 \
  -e DEEPSEEK_API_KEY="your-key" \
  -e SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG" \
  -e ENVIRONMENT="production" \
  -e PORT=8000 \
  test-app

# 在另一个终端测试
curl http://localhost:8000/health
```

### 💡 最可能的原因和解决方案

| 原因 | 如何识别 | 解决方案 |
|------|---------|---------|
| **环境变量缺失** | 日志中看到 "⚠️  环境变量检查有问题" | 在 Railway Dashboard 中添加环境变量 |
| **应用启动太慢** | 健康检查超时前应用未启动 | 已优化：超时时间增加到 300 秒 |
| **依赖安装失败** | 构建日志中有 pip 错误 | 检查网络连接，可能需要重试部署 |
| **端口配置错误** | 应用监听了错误的端口 | 已修复：自动使用 `$PORT` 环境变量 |

### 🚀 快速修复流程

1. **确认环境变量已设置** → Railway Dashboard → Variables
2. **提交最新代码** → `git push origin main`
3. **等待部署完成** → 现在有 5 分钟的启动时间
4. **检查日志** → `railway logs --follow`
5. **测试健康端点** → `curl https://your-app.up.railway.app/health`

---

## 🔧 已优化的配置

### 1. Dockerfile 优化
- ✅ **增加 pip 超时时间**: 从默认 15 秒增加到 300-600 秒
- ✅ **增加重试次数**: 网络失败时自动重试 5-10 次
- ✅ **分阶段安装依赖**: 先安装小包，单独处理 vosk 等大包
- ✅ **添加 ca-certificates**: 确保 HTTPS 连接正常

### 2. 启动脚本优化 (start_railway.py)
- ✅ **网络连接测试**: 启动前测试网络可用性
- ✅ **环境变量检查**: 详细的配置检查和错误提示
- ✅ **超时配置**: 增加 keep-alive 和 graceful shutdown 时间
- ✅ **错误日志增强**: 更详细的错误追踪

### 3. Railway 配置优化 (railway.json)
- ✅ **健康检查超时**: 从 60 秒增加到 100 秒
- ✅ **启动等待时间**: 从 120 秒增加到 180 秒
- ✅ **重试次数**: 从 3 次增加到 5 次

### 4. Docker 构建优化 (.dockerignore)
- ✅ **排除无用文件**: 减少上传时间和构建体积
- ✅ **排除测试文件**: 加快构建速度

## 🚀 部署步骤

### 方法 1: 使用 Railway CLI（推荐）

```bash
# 1. 安装 Railway CLI
npm install -g @railway/cli

# 2. 登录
railway login

# 3. 初始化项目（如果是新项目）
railway init

# 4. 设置环境变量
railway variables set DEEPSEEK_API_KEY="your-api-key-here"
railway variables set SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"
railway variables set ENVIRONMENT="production"

# 5. 部署
railway up

# 6. 查看日志
railway logs
```

### 方法 2: 使用 Railway Dashboard

1. **访问**: https://railway.app/dashboard
2. **创建项目**: New Project → Deploy from GitHub Repo
3. **连接仓库**: 选择您的 GitHub 仓库
4. **设置环境变量**:
   - 点击项目 → Variables 标签
   - 添加以下变量:
     ```
     DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
     SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
     ENVIRONMENT=production
     ```
5. **触发部署**: Settings → Redeploy

## 🔍 常见网络问题及解决方案

### 问题 1: pip install 超时

**症状**:
```
ERROR: Could not install packages due to an OSError: 
HTTPSConnectionPool: Read timed out.
```

**已解决方案**:
- ✅ Dockerfile 中已设置 `--timeout=300` 和 `--retries=5`
- ✅ vosk 包单独安装，超时时间 600 秒

**如仍失败，尝试**:
```dockerfile
# 在 Dockerfile 中使用 PyPI 镜像（国内）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题 2: Docker 构建超时

**症状**:
```
Build failed: timeout after 15 minutes
```

**解决方案**:
1. 检查 Railway 项目设置 → Build Settings
2. 增加 Build Timeout 到 30 分钟
3. 使用 `.dockerignore` 减少构建内容（已添加）

### 问题 3: 健康检查失败

**症状**:
```
Health check failed: GET /health returned 404
```

**检查**:
```bash
# 确认 /health 端点存在
railway logs | grep "health"
```

**验证本地**:
```bash
# 本地测试健康检查
python start_railway.py
curl http://localhost:8000/health
```

### 问题 4: 环境变量缺失

**症状**:
```
❌ 缺少环境变量: DEEPSEEK_API_KEY
```

**解决**:
```bash
# 使用 CLI 检查
railway variables

# 添加缺失的变量
railway variables set DEEPSEEK_API_KEY="your-key"
```

### 问题 5: 端口绑定错误

**症状**:
```
Error: Address already in use
```

**已解决**:
- ✅ `start_railway.py` 自动读取 `$PORT` 环境变量
- ✅ Railway 自动设置正确的端口

## 📊 监控部署状态

### 实时日志监控

```bash
# 跟踪部署日志
railway logs --follow

# 只看错误
railway logs | grep ERROR

# 查看最近 100 行
railway logs --lines 100
```

### 关键日志标记

✅ **成功标记**:
```
🚀 启动读书笔记应用 (Railway 优化版)
✅ DEEPSEEK_API_KEY: 已设置
✅ 网络连接正常
🚀 正在启动 Uvicorn 服务器...
```

❌ **失败标记**:
```
❌ 缺少环境变量
❌ 启动失败
⚠️  网络测试失败
```

## 🐛 调试技巧

### 1. 本地模拟 Railway 环境

```bash
# 设置环境变量
export PORT=8000
export ENVIRONMENT=production
export DEEPSEEK_API_KEY="your-key"
export SECRET_KEY="K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG"

# 使用 Railway 启动脚本
python start_railway.py
```

### 2. 使用 Railway Run

```bash
# 在 Railway 环境中运行命令
railway run python start_railway.py

# 进入 Railway Shell
railway shell
```

### 3. 检查构建日志

```bash
# 查看最近一次构建
railway logs --deployment latest

# 查看特定部署
railway logs --deployment <deployment-id>
```

## 🔄 重新部署流程

### 快速重新部署

```bash
# 方法 1: 推送代码触发
git add .
git commit -m "fix: railway deployment"
git push origin main

# 方法 2: 手动触发
railway redeploy

# 方法 3: 强制重建
railway up --detach
```

### 清理并重新部署

```bash
# 1. 删除旧的构建缓存
railway down

# 2. 重新部署
railway up
```

## 📋 部署检查清单

部署前确认：

- [ ] 所有环境变量已在 Railway 中设置
- [ ] `railway.json` 配置正确
- [ ] `Dockerfile` 没有语法错误
- [ ] `.dockerignore` 存在且有效
- [ ] `start_railway.py` 可以在本地运行
- [ ] `/health` 端点可访问
- [ ] 代码已推送到 GitHub

部署后验证：

- [ ] 部署成功（无错误日志）
- [ ] 健康检查通过
- [ ] 应用可以访问
- [ ] API 端点正常响应
- [ ] 数据库连接正常

## 🆘 获取帮助

### Railway 官方资源
- 文档: https://docs.railway.app/
- Discord: https://discord.gg/railway
- 状态页: https://status.railway.app/

### 项目特定问题

如果问题持续存在：

1. **收集日志**:
   ```bash
   railway logs > deployment.log
   ```

2. **检查网络**:
   ```bash
   railway shell
   curl -I https://pypi.org/
   ping 8.8.8.8
   ```

3. **验证 Docker**:
   ```bash
   docker build -t test-app .
   docker run -p 8000:8000 test-app
   ```

## 🎯 优化建议

### 减少部署时间
1. 使用 Railway 的构建缓存
2. 优化 Dockerfile 层级
3. 减少依赖包数量

### 提高稳定性
1. 添加数据库迁移脚本
2. 使用持久化存储（Railway Volumes）
3. 配置自动扩展

### 成本优化
1. 使用 SQLite 代替 PostgreSQL（小型应用）
2. 设置休眠策略
3. 监控资源使用

---

**最后更新**: 2025-10-13
**适用版本**: Railway V2
**维护者**: AI Assistant

