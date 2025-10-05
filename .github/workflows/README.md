# GitHub Actions 工作流配置指南

## 必需的 Secrets 配置

为了成功部署到 Google Cloud Run，您需要在 GitHub 仓库中配置以下 secrets：

### 1. 访问 Secrets 设置
1. 进入您的 GitHub 仓库
2. 点击 **Settings** 标签
3. 在左侧菜单中找到 **Secrets and variables** > **Actions**
4. 点击 **New repository secret** 按钮

### 2. 需要配置的 Secrets

#### GCP_SA_KEY
- **描述**: Google Cloud 服务账号的 JSON 密钥
- **获取方法**:
  1. 在 Google Cloud Console 中创建服务账号
  2. 为服务账号分配必要的权限（Cloud Run Admin, Storage Admin 等）
  3. 创建并下载 JSON 密钥文件
  4. 将整个 JSON 文件内容复制到 secret 中

#### GCP_PROJECT_ID
- **描述**: Google Cloud 项目 ID
- **获取方法**:
  1. 在 Google Cloud Console 中查看项目 ID
  2. 复制项目 ID（格式通常为：`your-project-name-123456`）

#### DEEPSEEK_API_KEY
- **描述**: DeepSeek AI API 密钥
- **获取方法**:
  1. 访问 [DeepSeek 官网](https://platform.deepseek.com/)
  2. 注册账号并获取 API 密钥
  3. 复制 API 密钥

#### SECRET_KEY
- **描述**: 应用程序的加密密钥
- **生成方法**:
  ```bash
  # 使用 Python 生成随机密钥
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  
  # 或使用 OpenSSL
  openssl rand -base64 32
  ```

### 3. 验证配置

配置完成后，您可以通过以下方式验证：

1. **手动触发工作流**:
   - 进入 **Actions** 标签
   - 选择 **Deploy to Google Cloud Run** 工作流
   - 点击 **Run workflow** 按钮

2. **推送代码触发**:
   - 推送到 `main` 分支会自动触发部署

### 4. 故障排除

如果部署失败，请检查：

1. **Secrets 是否正确配置**:
   - 确保所有 4 个 secrets 都已设置
   - 检查 secret 值是否正确（特别是 JSON 格式的服务账号密钥）

2. **Google Cloud 权限**:
   - 确保服务账号有足够的权限
   - 检查项目 ID 是否正确

3. **API 密钥有效性**:
   - 验证 DeepSeek API 密钥是否有效
   - 检查 API 密钥是否有足够的配额

### 5. 安全注意事项

- **永远不要**在代码中硬编码这些敏感信息
- **定期轮换**API 密钥和 secret keys
- **限制**服务账号的权限到最小必需范围
- **监控**API 使用情况，防止滥用

## 工作流说明

### 触发条件
- 推送到 `main` 分支
- 手动触发（workflow_dispatch）

### 部署流程
1. **代码检出**: 获取最新代码
2. **身份验证**: 使用服务账号密钥验证 Google Cloud
3. **环境验证**: 检查所有必需的 secrets 是否配置
4. **Docker 构建**: 构建应用镜像
5. **镜像推送**: 推送到 Google Container Registry
6. **Cloud Run 部署**: 部署到 Google Cloud Run

### 环境变量
部署时会自动设置以下环境变量：
- `DEEPSEEK_API_KEY`: DeepSeek AI API 密钥
- `SECRET_KEY`: 应用程序密钥
- `ENVIRONMENT`: 设置为 `production`