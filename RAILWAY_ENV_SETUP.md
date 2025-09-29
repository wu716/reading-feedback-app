# 🔑 Railway 环境变量配置指南

## 📋 必需的环境变量

在Railway项目中，您需要设置以下环境变量：

### 1. DEEPSEEK_API_KEY
```
DEEPSEEK_API_KEY = sk-163b19ba581a46a69d2fa5afd454772e
```
**说明**: DeepSeek AI服务的API密钥，用于智能分析读书笔记

### 2. SECRET_KEY
```
SECRET_KEY = K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
```
**说明**: 应用的安全密钥，用于JWT令牌加密

### 3. ENVIRONMENT
```
ENVIRONMENT = production
```
**说明**: 运行环境标识，设置为production

## 🛠️ 配置步骤

### 方法1：通过Railway Web界面
1. 访问 https://railway.app/
2. 登录您的账户
3. 选择您的项目："读书笔记应用"
4. 点击 "Settings" 标签页
5. 找到 "Variables" 部分
6. 点击 "New Variable" 按钮
7. 逐个添加上述环境变量

### 方法2：通过Railway CLI
```bash
# 安装Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 链接项目
railway link

# 设置环境变量
railway variables set DEEPSEEK_API_KEY=sk-163b19ba581a46a69d2fa5afd454772e
railway variables set SECRET_KEY=K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG
railway variables set ENVIRONMENT=production
```

## ✅ 验证配置

配置完成后，Railway会自动重新部署应用。您可以通过以下方式验证：

1. **查看部署日志**：在Railway项目页面查看"Logs"标签
2. **检查健康状态**：应用应该显示"Healthy"状态
3. **访问应用**：使用Railway提供的URL访问应用

## 🚨 常见问题

### 问题1：环境变量未生效
**解决方案**：
- 确保变量名称完全正确（区分大小写）
- 确保没有多余的空格
- 重新部署应用

### 问题2：API密钥无效
**解决方案**：
- 检查DeepSeek API密钥是否正确
- 确认API密钥有足够的额度
- 测试API密钥是否有效

### 问题3：应用启动失败
**解决方案**：
- 查看Railway部署日志
- 检查所有必需的环境变量是否已设置
- 确认应用代码没有语法错误

## 📞 获取帮助

如果遇到问题，可以：
1. 查看Railway官方文档
2. 检查GitHub仓库的Issues
3. 联系技术支持
