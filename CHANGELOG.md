# 变更日志 (Changelog)

所有重要的项目变更都将记录在此文件中。

---

## [2.0.0] - 2025-10-08

### 🎉 重大更新：智能行为分析与个性化反馈系统

#### ✨ 新增功能

##### 1. 智能行为分类系统
- 自动识别**情境触发型**和**习惯养成型**两种行为
- 使用`deepseek-reasoner`模型进行深度分析
- 支持后台异步处理，不影响用户操作
- 为不同类型提供差异化的统计维度

##### 2. 复合成功指标
- 引入复合指标计算：`success_score = 客观完成度(60%) + 主观评分(40%)`
- 支持客观完成度(0.0-1.0)和主观评分(1-5)
- 自动为历史数据补全复合指标
- 更准确地反映实践质量

##### 3. AI个性化建议系统
- 每次记录实践后自动生成定制化建议
- 基于行动类型、执行结果和历史数据
- 支持多轮对话深入讨论
- 使用`deepseek-reasoner`模型提升建议质量

##### 4. 分类统计分析
- 按行为类型（trigger/habit）分别统计
- 触发型：成功率统计
- 习惯型：坚持率统计 + 连续天数
- 对比分析功能
- 单个行动详细统计

##### 5. 分析报告导出
- 支持纯文本和Markdown格式
- 包含完整的行动信息和统计数据
- 一键复制到剪贴板
- 包含AI建议和最近记录

#### 🔄 API变更

##### 新增端点
- `POST /actions/{action_id}/advice-chat` - 与AI进行建议对话
- `GET /actions/{action_id}/advice` - 获取行动的AI建议
- `GET /actions/{action_id}/export` - 导出行动分析报告
- `GET /dashboard/stats/by-type` - 按行为类型获取统计
- `GET /dashboard/stats/trigger-vs-habit` - 对比触发型vs习惯型
- `GET /dashboard/stats/action-details/{action_id}` - 单个行动详细统计

##### 修改的端点
- `POST /actions/{action_id}/practice` 
  - 新增：`objective_completion`字段（可选）
  - 新增：自动计算`success_score`
  - 新增：后台异步生成AI建议
  - 响应中包含复合成功指标

- `GET /actions/` 和 `GET /actions/{action_id}`
  - 响应中新增：`action_type`字段
  - 响应中新增：`ai_analysis`字段
  - 响应中新增：`advice_session_id`字段

#### 🗄️ 数据库变更

##### Actions表新增字段
- `action_type` (VARCHAR(20), default='trigger') - 行为类型
- `ai_analysis` (TEXT, nullable) - AI分析和建议
- `advice_session_id` (VARCHAR(50), nullable) - 建议对话会话ID

##### PracticeLogs表新增字段
- `objective_completion` (FLOAT, nullable) - 客观完成度
- `success_score` (FLOAT, nullable) - 复合成功指标

#### 🛠️ 技术改进

##### AI服务增强
- 实现多模型智能路由系统
- `deepseek-chat`用于快速任务（行动抽取）
- `deepseek-reasoner`用于复杂推理（行为分析、建议生成）
- 支持模型超时和回退机制

##### 异步处理架构
- 使用FastAPI的BackgroundTasks机制
- AI分析不阻塞主流程
- 后台任务错误处理和日志记录

##### 向后兼容性
- 所有新字段设置为可空或有默认值
- 自动为现有数据计算复合指标
- 旧API端点保持完全兼容

#### 📝 文档更新
- `IMPLEMENTATION_SUMMARY.md` - 完整实施文档
- `UPGRADE_GUIDE.md` - 升级指南
- `NEW_FEATURES_README.md` - 新功能说明
- `CHANGELOG.md` - 变更日志（本文档）
- `migrate_add_new_features.py` - 数据库迁移脚本

#### 🐛 修复
- 改进了统计计算的准确性
- 优化了数据库查询性能
- 修复了PracticeLog的result字段验证逻辑

---

## [1.0.0] - 2025-XX-XX

### 初始版本

#### 核心功能
- 用户认证和授权
- 读书笔记上传
- AI自动抽取行动项
- 行动项管理（CRUD）
- 实践记录功能
- 基础统计分析
- 仪表盘展示
- 时间管理功能
- Self-talk模块

#### 技术栈
- FastAPI后端框架
- SQLAlchemy ORM
- SQLite数据库
- DeepSeek AI集成
- JWT认证

---

## 版本规范

我们遵循[语义化版本](https://semver.org/lang/zh-CN/)：

- **主版本号**：不兼容的API变更
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

---

## 变更类型说明

- `✨ 新增` - 新功能
- `🔄 变更` - 现有功能的变更
- `🗑️ 废弃` - 即将移除的功能
- `🚫 移除` - 已移除的功能
- `🐛 修复` - Bug修复
- `🔒 安全` - 安全问题修复
- `📝 文档` - 文档变更
- `🛠️ 技术` - 技术改进

---

## 迁移指南

### 从 1.0.0 升级到 2.0.0

1. **备份数据库**
   ```bash
   cp app.db app.db.backup
   ```

2. **执行迁移脚本**
   ```bash
   python migrate_add_new_features.py
   ```

3. **更新环境变量**（如需要）
   ```bash
   # 确保配置了DeepSeek API密钥
   DEEPSEEK_API_KEY=your_key
   ```

4. **重启应用**
   ```bash
   python start_app.py
   ```

详细升级指南请参考 `UPGRADE_GUIDE.md`

---

## 路线图

### v2.1.0 (计划中)
- [ ] 可视化图表系统
  - 折线图：趋势分析
  - 热力图：习惯日历
  - 雷达图：多维度评估
- [ ] 前端组件库
  - 行为类型筛选器
  - AI建议对话界面
  - 分析报告预览

### v2.2.0 (计划中)
- [ ] PDF导出支持
- [ ] 图表快照生成
- [ ] 分享链接机制
- [ ] 移动端适配

### v3.0.0 (规划中)
- [ ] 多用户协作
- [ ] 社区功能
- [ ] 行为模板库
- [ ] 第三方集成（Notion、Todoist等）

---

## 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

---

## 联系方式

- 项目地址：[GitHub仓库链接]
- 问题反馈：[GitHub Issues链接]
- 邮件：[联系邮箱]

---

**最后更新**: 2025-10-08

