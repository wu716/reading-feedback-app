# 🚀 快速启动指南

## 📋 启动步骤

### 步骤1：设置 API 密钥

**方法A：使用环境变量（推荐）**
```cmd
set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
```

**方法B：使用 .env 文件**
1. 复制 `env.example` 为 `.env`
2. 编辑 `.env` 文件，填入您的 API 密钥

### 步骤2：启动应用

**方法A：使用批处理文件（最简单）**
```cmd
start_app.cmd
```

**方法B：直接运行 Python**
```cmd
python start_app.py
```

## 📱 访问地址

- **主页面**：http://localhost:8000
- **Self-talk**：http://localhost:8000/static/self_talk/index.html
- **API 文档**：http://localhost:8000/docs

## 🔧 故障排除

### 问题1：提示缺少 DEEPSEEK_API_KEY
**解决方案**：
```cmd
set DEEPSEEK_API_KEY=sk-your-actual-api-key-here
```

### 问题2：端口被占用
**解决方案**：
- 关闭占用 8000 端口的程序
- 或修改 `start_app.py` 中的端口号

### 问题3：Python 模块未找到
**解决方案**：
```cmd
pip install -r requirements.txt
```

### 问题4：PowerShell 权限问题
**解决方案**：使用 CMD 而不是 PowerShell

## 🧪 功能测试

启动成功后，运行测试脚本：
```cmd
python test_app.py
```

## 📖 详细说明

更多详细信息请查看：
- `SECURE_START_GUIDE.md` - 安全启动指南
- `README.md` - 项目说明
