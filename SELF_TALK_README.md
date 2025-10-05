# Self-talk 模块使用指南

## 概述

Self-talk 模块是读书反馈应用的新增功能，允许用户录制语音并进行离线语音识别转写，记录内心对话和思考过程。

## 功能特性

- 🎤 **语音录制**: 支持浏览器端实时录音
- 📁 **文件上传**: 支持上传音频文件（WAV、MP3、M4A、OGG）
- 🧠 **离线识别**: 使用 Vosk 中文模型进行离线语音识别
- 💾 **本地存储**: 音频文件保存在本地，数据库只存储路径
- 🔗 **关联功能**: 可选择关联读书行动项
- 📱 **响应式设计**: 支持桌面和移动端

## 技术架构

### 后端架构

```
app/self_talk/
├── __init__.py              # 模块初始化
├── schemas.py               # Pydantic 数据模型
├── speech_recognition.py    # Vosk 语音识别服务
└── router.py               # FastAPI 路由
```

### 数据库表结构

```sql
CREATE TABLE self_talks (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    action_id INT REFERENCES actions(id), -- 可选，关联读书行动项
    audio_path TEXT NOT NULL,             -- 本地音频文件路径
    transcript TEXT,                      -- 转写文字
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP DEFAULT NULL     -- 软删除
);
```

### API 接口

#### 1. 上传 Self-talk
```
POST /api/self_talks/
Content-Type: multipart/form-data

参数:
- file: 音频文件
- action_id: 可选的关联行动项ID

返回:
{
  "id": 1,
  "user_id": 1,
  "action_id": null,
  "audio_path": "/uploads/self_talks/xxx.wav",
  "transcript": "这是识别结果",
  "created_at": "2024-01-01T00:00:00"
}
```

#### 2. 获取 Self-talk 列表
```
GET /api/self_talks/?skip=0&limit=20

返回:
{
  "self_talks": [...],
  "total": 10
}
```

#### 3. 获取单个 Self-talk
```
GET /api/self_talks/{id}
```

#### 4. 删除 Self-talk
```
DELETE /api/self_talks/{id}
```

#### 5. 检查语音识别服务状态
```
GET /api/self_talks/health/recognition

返回:
{
  "speech_recognition_available": true,
  "message": "语音识别服务正常"
}
```

## 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 下载 Vosk 中文模型

运行模型下载脚本：
```bash
python download_vosk_model.py
```

或手动下载：
1. 访问 https://alphacephei.com/vosk/models
2. 下载 `vosk-model-small-cn-0.22.zip`
3. 解压到项目根目录

### 3. 创建必要目录

```bash
mkdir -p uploads/self_talks
mkdir -p static/self_talk
```

### 4. 启动应用

```bash
python main.py
```

## 使用指南

### 1. 访问 Self-talk 页面

1. 打开浏览器访问 `http://localhost:8000`
2. 登录或注册账户
3. 点击 "🎤 开始 Self-talk" 按钮

### 2. 录制语音

1. 点击 "🎤 开始录音" 按钮
2. 允许浏览器访问麦克风
3. 开始说话
4. 点击 "⏹️ 停止录音" 按钮
5. 系统会自动上传并转写

### 3. 上传音频文件

1. 点击 "选择文件" 按钮
2. 选择音频文件（支持 WAV、MP3、M4A、OGG）
3. 点击 "上传音频" 按钮
4. 等待上传和转写完成

### 4. 查看历史记录

- 页面会显示最近的 Self-talk 记录
- 可以播放音频文件
- 可以查看转写文字
- 可以删除不需要的记录

## 文件存储

### 音频文件存储

- **Web 端**: 保存在 `uploads/self_talks/` 目录
- **桌面/移动端**: 可配置保存到用户本地目录
- **数据库**: 只存储文件路径，不存储音频二进制数据

### 文件命名规则

```
{user_id}_{uuid}.{extension}
```

例如：`1_a1b2c3d4e5f6.wav`

## 语音识别

### Vosk 模型

- **模型名称**: vosk-model-small-cn-0.22
- **语言**: 中文
- **大小**: 约 50MB
- **精度**: 适合日常对话识别

### 支持的音频格式

- **采样率**: 16000Hz（推荐）
- **声道**: 单声道
- **位深**: 16-bit PCM
- **格式**: WAV、MP3、M4A、OGG

### 识别流程

1. 接收音频文件
2. 检查文件格式
3. 加载 Vosk 模型
4. 分块处理音频
5. 返回转写结果

## 错误处理

### 常见错误

1. **语音识别服务不可用**
   - 检查 Vosk 模型是否正确安装
   - 查看日志中的错误信息

2. **音频格式不支持**
   - 确保音频文件格式正确
   - 检查采样率和声道设置

3. **文件上传失败**
   - 检查文件大小（限制 50MB）
   - 确保有足够的磁盘空间

4. **权限问题**
   - 确保 `uploads/self_talks/` 目录可写
   - 检查用户认证状态

## 开发说明

### 添加新功能

1. 在 `app/self_talk/schemas.py` 中定义数据模型
2. 在 `app/self_talk/router.py` 中添加 API 路由
3. 在 `static/self_talk/index.html` 中添加前端功能
4. 更新数据库模型（如需要）

### 扩展语音识别

1. 支持更多语言模型
2. 集成在线语音识别服务
3. 添加语音情感分析
4. 支持实时语音识别

### 性能优化

1. 音频文件压缩
2. 批量处理
3. 缓存机制
4. 异步处理

## 故障排除

### 语音识别不工作

1. 检查 Vosk 模型文件是否存在
2. 查看应用日志
3. 测试音频文件格式
4. 检查系统资源

### 前端录音失败

1. 确保使用 HTTPS 或 localhost
2. 检查浏览器权限设置
3. 测试麦克风是否正常
4. 查看浏览器控制台错误

### 文件上传失败

1. 检查网络连接
2. 验证用户认证
3. 检查文件大小限制
4. 确保服务器有足够空间

## 更新日志

### v1.0.0 (2024-01-01)
- 初始版本发布
- 支持语音录制和上传
- 集成 Vosk 中文语音识别
- 提供完整的 CRUD API
- 响应式前端界面

## 许可证

本项目遵循与主项目相同的许可证。
