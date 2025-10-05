# 🚀 快速部署指南

## 🎯 解决您的问题

**问题**: Railway线上部署需要配置AI密钥环境变量，同时确保软件能正常使用AI功能。

**解决方案**: 按照以下步骤配置Railway环境变量。

## ⚡ 快速开始

### 1. 配置Railway环境变量

访问 https://railway.app/ → 您的项目 → Settings → Variables

添加以下环境变量：

```
DEEPSEEK_API_KEY = 您的DeepSeek API密钥
SECRET_KEY = K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
ENVIRONMENT = production
```

### 2. 验证配置

运行以下命令验证配置：

```bash
# 检查环境变量和AI连接
python quick_test.py

# 或使用详细配置助手
python railway_env_setup.py
```

### 3. 部署应用

Railway会自动重新部署应用。部署成功后，您将看到：

```
✅ 环境变量检查通过 (3/3)
✅ AI服务连接正常
🚀 启动读书笔记应用 (Railway版本)
```

## 📚 详细文档

- [完整部署指南](DEPLOYMENT_GUIDE.md)
- [Railway环境变量配置](RAILWAY_ENV_SETUP.md)

## 🆘 需要帮助？

如果遇到问题，请运行：
```bash
python railway_env_setup.py
```

这个工具会提供详细的配置指导和故障排除建议。
