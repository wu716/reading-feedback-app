# 🚀 安全启动指南

## ⚠️ 重要安全提醒

**永远不要在代码中硬编码API密钥！** 这会导致密钥暴露在公共仓库中。

## 🔐 正确的启动方法

### 方法一：使用环境变量（推荐）

#### Windows (PowerShell)
```powershell
# 设置环境变量
$env:DEEPSEEK_API_KEY="your-actual-api-key-here"

# 启动应用
python start_with_env.py
```

#### Windows (CMD)
```cmd
# 设置环境变量
set DEEPSEEK_API_KEY=your-actual-api-key-here

# 启动应用
python start_with_env.py
```

#### Linux/Mac
```bash
# 设置环境变量
export DEEPSEEK_API_KEY="your-actual-api-key-here"

# 启动应用
python start_with_env.py
```

### 方法二：使用启动脚本

#### Windows
```cmd
# 先设置环境变量
set DEEPSEEK_API_KEY=your-actual-api-key-here

# 然后运行启动脚本
start_app.bat
```

#### Linux/Mac
```bash
# 先设置环境变量
export DEEPSEEK_API_KEY="your-actual-api-key-here"

# 然后运行启动脚本
chmod +x start_app.sh
./start_app.sh
```

### 方法三：使用 .env 文件

1. 创建 `.env` 文件（确保在 `.gitignore` 中）：
```env
DEEPSEEK_API_KEY=your-actual-api-key-here
DATABASE_URL=sqlite:///./app.db
```

2. 启动应用：
```bash
python start_with_env.py
```

## 🌐 访问地址

启动成功后，可以通过以下地址访问：

- **主页面**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **Self-talk页面**: http://localhost:8000/static/self_talk/index.html

## 🔒 安全最佳实践

1. **永远不要**在代码中硬编码API密钥
2. **永远不要**将包含密钥的文件提交到Git
3. **使用环境变量**或加密文件存储敏感信息
4. **定期轮换**API密钥
5. **使用不同的密钥**用于开发和生产环境

## 🛠️ 故障排除

如果启动失败，请检查：

1. ✅ API密钥是否正确设置
2. ✅ Python依赖是否已安装：`pip install -r requirements.txt`
3. ✅ 端口8000是否被占用
4. ✅ 数据库文件权限是否正确

## 📞 获取帮助

如果遇到问题，请提供：
- 操作系统信息
- Python版本
- 完整的错误日志（**不要包含API密钥**）
