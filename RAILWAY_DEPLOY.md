# Railway 部署配置
# 用于在 Railway 平台部署读书笔记实践反馈系统

# 环境变量配置
# 在 Railway 项目设置中添加以下环境变量：

# 必需的环境变量：
# DEEPSEEK_API_KEY=your-deepseek-api-key-here
# SECRET_KEY=your-secret-key-here
# ENVIRONMENT=production

# 可选的环境变量：
# DATABASE_URL=sqlite:///./app.db  # Railway 会自动提供 PostgreSQL
# ACCESS_TOKEN_EXPIRE_MINUTES=30
# DEEPSEEK_MODEL=deepseek-chat
# DEEPSEEK_BASE_URL=https://api.deepseek.com

# 部署步骤：
# 1. 访问 https://railway.app
# 2. 使用 GitHub 登录
# 3. 点击 "New Project" -> "Deploy from GitHub repo"
# 4. 选择您的仓库
# 5. 在项目设置中添加环境变量
# 6. 等待部署完成

# 注意事项：
# - Railway 会自动提供 PostgreSQL 数据库
# - 需要更新代码以支持 PostgreSQL（当前使用 SQLite）
# - 确保 API Key 安全存储
