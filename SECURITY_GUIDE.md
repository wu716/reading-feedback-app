# 🔒 API密钥安全配置指南

## ⚠️ 重要安全提醒

**API密钥绝对不能提交到代码仓库中！**

## 🔑 获取新的DeepSeek API密钥

由于之前的API密钥已泄露，您需要：

1. **登录DeepSeek控制台**：https://platform.deepseek.com/
2. **撤销旧密钥**：在API密钥管理页面删除泄露的密钥
3. **生成新密钥**：创建新的API密钥
4. **记录新密钥**：安全保存新密钥（不要写在代码中）

## 🛠️ 安全配置步骤

### 1. 在Railway中设置环境变量

**不要**在代码中硬编码API密钥，而是在Railway项目设置中添加：

```
DEEPSEEK_API_KEY = 您的新API密钥
SECRET_KEY = K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
ENVIRONMENT = production
```

### 2. 验证配置

运行以下命令检查环境变量是否正确设置：

```bash
python check_env.py
```

### 3. 本地开发配置

创建 `.env` 文件（不要提交到Git）：

```bash
# .env 文件（本地开发使用）
DEEPSEEK_API_KEY=您的新API密钥
SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
ENVIRONMENT=development
```

**重要**：将 `.env` 添加到 `.gitignore` 文件中！

## 🚨 安全最佳实践

1. **永远不要在代码中硬编码API密钥**
2. **使用环境变量存储敏感信息**
3. **定期轮换API密钥**
4. **监控API使用情况**
5. **使用最小权限原则**

## 📞 如果密钥已泄露

1. **立即撤销泄露的密钥**
2. **生成新的API密钥**
3. **更新所有环境变量**
4. **检查是否有未授权使用**
5. **考虑更换所有相关密钥**

## ✅ 验证修复

修复完成后，确保：
- [ ] 代码中没有任何硬编码的API密钥
- [ ] 所有环境变量都正确设置
- [ ] 应用能够正常启动
- [ ] AI服务功能正常
