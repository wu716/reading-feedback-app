# Self-talk 提醒功能使用指南

## 📋 功能概述

Self-talk 提醒功能帮助您养成定期自我反思的习惯。系统提供多种提醒方式，让您不会错过重要的反思时刻。

## ✨ 功能特性

### 1. 提醒类型

#### ⏰ 定时提醒
- 每日固定时间提醒
- 自定义提醒时间（如每天晚上8点）
- 选择特定的星期几提醒（如只在工作日）

#### 🎯 行为触发提醒
- **完成行动项后提醒**：当您标记行动项为"完成"时，系统会提醒您记录反思
- **添加新行动项后提醒**：创建新行动项时，提醒您关联 Self-talk
- **长期未记录提醒**：超过设定天数（默认3天）未做 Self-talk 时自动提醒

### 2. 通知方式

#### 📱 浏览器通知
- 桌面通知弹窗
- 点击通知直接跳转到 Self-talk 页面
- 无需打开页面即可收到提醒

#### 📧 邮件通知
- 发送提醒邮件到您的注册邮箱
- 适合长时间不在线的情况
- 需要配置邮件服务（可选）

## 🚀 快速开始

### 第一步：安装依赖

```bash
pip install -r requirements.txt
```

新增的依赖：
- `APScheduler==3.10.4` - 定时任务调度器

### 第二步：运行数据库迁移

```bash
python migrate_self_talk_reminders.py
```

这将创建以下数据表：
- `self_talk_reminder_settings` - 用户提醒设置
- `self_talk_reminder_logs` - 提醒历史记录

### 第三步：配置邮件服务（可选）

在 `.env` 文件中添加邮件配置：

```env
# 邮件服务配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

**Gmail 用户注意**：
1. 启用两步验证
2. 生成应用专用密码
3. 使用应用专用密码作为 `SMTP_PASSWORD`

### 第四步：启动应用

```bash
python main.py
```

应用启动时会自动：
- 加载定时任务调度器
- 每5分钟检查一次每日提醒
- 每小时检查一次非活跃用户

## 📖 使用指南

### 访问提醒设置

有两种方式访问提醒设置：

#### 方式一：通过个人中心
1. 点击左侧导航栏的"👤 个人中心"
2. 在"🔔 Self-talk 提醒设置"卡片中配置

#### 方式二：通过 Self-talk 页面
1. 进入 Self-talk 页面
2. 点击右上角的"🔔 提醒设置"按钮

### 配置提醒

#### 1. 启用提醒功能
- 打开总开关启用所有提醒
- 关闭后将不会收到任何提醒

#### 2. 配置定时提醒
1. 开启"每日定时提醒"
2. 设置提醒时间（如 20:00）
3. 选择提醒日期（可多选）
   - 周日到周六任意组合
   - 示例：只在工作日（周一到周五）

#### 3. 配置行为触发提醒
- **完成行动项后提醒**：建议开启
- **添加新行动项后提醒**：建议开启
- **长期未记录提醒**：设置天数阈值（1-30天）

#### 4. 选择通知方式
- **浏览器通知**：需要授权浏览器通知权限
- **邮件通知**：需要配置邮件服务

#### 5. 保存设置
点击"💾 保存设置"按钮

### 测试提醒

点击"🔔 测试提醒"按钮，系统会立即发送一条测试通知。

## 🔔 浏览器通知

### 授权通知权限

首次使用时，浏览器会询问是否允许通知：
1. 点击"允许"
2. 如果误点了"阻止"，可以在浏览器设置中重新授权

### Chrome 浏览器
1. 点击地址栏左侧的锁图标
2. 找到"通知"设置
3. 选择"允许"

### Firefox 浏览器
1. 点击地址栏左侧的信息图标
2. 找到"权限"
3. 勾选"通知"

### Edge 浏览器
类似 Chrome 的操作流程

## 📧 邮件通知配置

### Gmail 配置

1. **启用两步验证**
   - 访问 Google 账户设置
   - 安全 → 两步验证
   - 按照指引设置

2. **生成应用专用密码**
   - 安全 → 应用专用密码
   - 选择"邮件"和"其他设备"
   - 复制生成的16位密码

3. **配置 .env**
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-16-digit-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

### QQ 邮箱配置

1. **开启 SMTP 服务**
   - 登录 QQ 邮箱网页版
   - 设置 → 账户
   - POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务
   - 开启"SMTP服务"
   - 生成授权码

2. **配置 .env**
```env
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your-qq-number@qq.com
SMTP_PASSWORD=your-authorization-code
SMTP_FROM_EMAIL=your-qq-number@qq.com
```

### 163 邮箱配置

```env
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USE_TLS=False
SMTP_USERNAME=your-email@163.com
SMTP_PASSWORD=your-authorization-code
SMTP_FROM_EMAIL=your-email@163.com
```

## 🔧 技术架构

### 后端架构

```
app/
├── models.py                           # 数据模型
│   ├── SelfTalkReminderSetting        # 提醒设置
│   └── SelfTalkReminderLog            # 提醒日志
├── routers/
│   └── self_talk_reminders.py         # 提醒 API
└── self_talk/
    ├── reminder_schemas.py            # Pydantic 模型
    └── reminder_service.py            # 提醒服务逻辑
```

### 前端架构

```
static/
├── user_center.html                   # 个人中心（含提醒设置）
├── reminder_notification.js           # 浏览器通知服务
└── index.html                         # 主页面（引入通知服务）
```

### API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/self_talk_reminders/settings` | 获取提醒设置 |
| POST | `/api/self_talk_reminders/settings` | 创建/更新提醒设置 |
| PATCH | `/api/self_talk_reminders/settings` | 部分更新设置 |
| GET | `/api/self_talk_reminders/logs` | 获取提醒历史 |
| POST | `/api/self_talk_reminders/trigger` | 手动触发提醒（测试用） |
| GET | `/api/self_talk_reminders/pending` | 获取待处理提醒 |
| POST | `/api/self_talk_reminders/dismiss/{log_id}` | 标记提醒已处理 |

## 🎯 使用场景

### 场景1：养成每日反思习惯
**配置**：
- 开启每日定时提醒
- 设置时间：晚上 20:00
- 选择：每天

**效果**：每天晚上8点收到提醒，记录当天的思考和感悟。

### 场景2：工作日专注模式
**配置**：
- 开启每日定时提醒
- 设置时间：下班时间 18:00
- 选择：周一到周五

**效果**：工作日下班时提醒反思，周末不打扰。

### 场景3：行动后即时反思
**配置**：
- 开启"完成行动项后提醒"
- 关闭定时提醒

**效果**：完成行动项后立即提醒，趁热打铁记录感悟。

### 场景4：防止遗忘
**配置**：
- 开启"长期未记录提醒"
- 设置阈值：3天

**效果**：超过3天未做 Self-talk 时提醒，避免中断习惯。

## 📊 提醒统计

### 查看提醒历史

个人中心页面会显示：
- 提醒发送次数
- 响应率（用户采取行动的比例）
- 最近的提醒记录

### 日志记录

每条提醒都会记录：
- 提醒类型（定时/行为触发）
- 触发时间
- 通知方式
- 是否响应

## ⚙️ 定时任务说明

### 任务调度

应用启动时会创建两个后台任务：

1. **每日提醒检查**
   - 频率：每5分钟
   - 功能：检查是否到达用户设定的提醒时间
   - 精度：±5分钟

2. **非活跃用户检查**
   - 频率：每1小时
   - 功能：检查超过阈值未记录的用户
   - 每天最多提醒一次

### 任务日志

定时任务的执行日志会记录在应用日志中：
```
[INFO] 开始检查每日提醒...
[INFO] 已为用户 张三 发送每日提醒
[INFO] 每日提醒检查完成，共发送 3 条提醒
```

## 🐛 故障排除

### 问题1：收不到浏览器通知

**检查步骤**：
1. 确认浏览器权限已授权
2. 确认提醒设置中"浏览器通知"已开启
3. 检查浏览器是否支持通知（现代浏览器都支持）
4. 打开浏览器控制台查看错误信息

### 问题2：收不到邮件通知

**检查步骤**：
1. 确认 `.env` 中邮件配置正确
2. 确认 SMTP 密码是应用专用密码（不是登录密码）
3. 查看应用日志中的邮件发送错误
4. 测试邮箱服务是否可用

### 问题3：定时提醒不准时

**说明**：
- 定时任务每5分钟检查一次，存在±5分钟误差
- 这是性能和精度的平衡
- 如需更精确，可修改 `main.py` 中的轮询间隔

### 问题4：数据库迁移失败

**解决方法**：
```bash
# 回滚迁移
python migrate_self_talk_reminders.py rollback

# 重新迁移
python migrate_self_talk_reminders.py
```

## 📝 开发说明

### 添加新的提醒类型

1. 在 `reminder_service.py` 中添加检查逻辑
2. 在 `reminder_schemas.py` 中添加配置字段
3. 在数据库模型中添加对应字段
4. 在前端界面添加配置选项

### 自定义提醒消息

修改 `reminder_service.py` 中的 `get_reminder_message` 方法：

```python
messages = {
    "daily": ("标题", "消息内容"),
    # 添加新类型
}
```

### 调整轮询频率

修改 `static/reminder_notification.js`：

```javascript
this.pollInterval = 1 * 60 * 1000; // 改为1分钟
```

## 📄 数据隐私

- 所有提醒设置仅对用户自己可见
- 提醒日志不会被分享给其他用户
- 邮件通知仅发送到用户注册邮箱
- 可以随时删除提醒历史记录

## 🔄 更新日志

### v1.0.0 (2024-10-10)
- ✅ 实现定时提醒功能
- ✅ 实现行为触发提醒
- ✅ 支持浏览器通知
- ✅ 支持邮件通知
- ✅ 集成 APScheduler 定时任务
- ✅ 创建个人中心页面
- ✅ 提醒设置界面
- ✅ 提醒历史记录

## 📞 技术支持

如遇到问题，请：
1. 查看应用日志
2. 查看浏览器控制台
3. 参考本文档的故障排除章节

## 🎉 总结

Self-talk 提醒功能帮助您：
- 养成定期反思的好习惯
- 不错过重要的反思时刻
- 灵活配置符合自己节奏的提醒方式
- 追踪自己的反思频率和习惯

开始使用，让自我反思成为习惯！🚀

