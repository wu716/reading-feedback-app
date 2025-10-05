# 🔒 安全启动指南

## ⚠️ 重要安全提醒

**请勿将 API 密钥硬编码到任何文件中！** 所有敏感信息都应该通过环境变量或 `.env` 文件管理。

## 🚀 安全启动方法

### 方法1：使用环境变量（推荐）

#### CMD 方式：
```cmd
cd /d D:\projects\reading-feedback-app
set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
start_secure.cmd
```

#### PowerShell 方式：
```powershell
cd D:\projects\reading-feedback-app
$env:DEEPSEEK_API_KEY="sk-your-actual-api-key-here"
.\start_secure.cmd
```

### 方法2：使用 .env 文件

1. **创建 `.env` 文件**（在项目根目录）：
```env
DEEPSEEK_API_KEY=sk-your-actual-api-key-here
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
DATABASE_URL=sqlite:///./app.db
```

2. **启动应用**：
```cmd
cd /d D:\projects\reading-feedback-app
"C:\Users\冉冉\AppData\Local\Programs\Python\Python313\python.exe" start_secure.py
```

### 方法3：直接运行 Python 脚本

```cmd
cd /d D:\projects\reading-feedback-app
set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
"C:\Users\冉冉\AppData\Local\Programs\Python\Python313\python.exe" start_secure.py
```

## 📱 访问地址

- **主页面**：http://localhost:8000
- **Self-talk**：http://localhost:8000/static/self_talk/index.html
- **API 文档**：http://localhost:8000/docs

## 🔧 环境变量说明

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `DEEPSEEK_API_KEY` | ✅ | 无 | DeepSeek API 密钥 |
| `SECRET_KEY` | ❌ | 随机生成 | JWT 签名密钥 |
| `ENVIRONMENT` | ❌ | development | 运行环境 |
| `DATABASE_URL` | ❌ | sqlite:///./app.db | 数据库连接 |

## 🧪 功能测试

启动应用后，运行测试脚本：

```cmd
set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
"C:\Users\冉冉\AppData\Local\Programs\Python\Python313\python.exe" test_app.py
```

## 🔒 安全最佳实践

1. **永远不要**将 API 密钥提交到 Git 仓库
2. **使用环境变量**或 `.env` 文件管理敏感信息
3. **定期轮换**API 密钥
4. **限制 API 密钥权限**，只授予必要的访问权限
5. **监控 API 使用情况**，发现异常及时处理

## 📁 文件说明

- `start_secure.py` - 安全的 Python 启动脚本
- `start_secure.cmd` - 安全的 CMD 批处理文件
- `test_app.py` - 功能测试脚本
- `.env` - 环境变量文件（已加入 .gitignore）

## ⚠️ 注意事项

1. **PowerShell 问题**：如果遇到权限问题，请使用 CMD
2. **端口占用**：确保 8000 端口未被占用
3. **Vosk 模型**：确保 `models/vosk-model-small-cn-0.22/` 目录存在
4. **环境变量**：确保在启动前设置了 `DEEPSEEK_API_KEY`

## 🎉 预期结果

启动成功后，您应该看到：
- 应用在 http://localhost:8000 正常运行
- 可以正常登录和使用所有功能
- 行动板块可以正常输入和保存
- Self-talk 模块可以录音和转写
- AI 服务可以正常抽取行动项

## 📞 如果还有问题

如果启动后仍有问题，请：
1. 检查环境变量是否正确设置
2. 运行 `test_app.py` 查看具体错误
3. 检查 CMD 中的错误信息
4. 确认所有文件都存在且完整
