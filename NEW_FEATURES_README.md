# 新功能说明文档

## 🎉 版本 2.0 - 智能行为分析与个性化反馈系统

---

## 核心功能

### 1. 🔍 智能行为分类

系统自动识别两种行为类型：

#### 情境触发型 (Trigger-Based)
- **特点**：在特定情境下执行
- **示例**：遇到压力时深呼吸、感到焦虑时写日记
- **统计维度**：成功率（成功次数/总尝试次数）

#### 习惯养成型 (Habit-Formation)
- **特点**：需要定期重复的行为
- **示例**：每天锻炼、每天阅读
- **统计维度**：坚持率（完成天数/目标天数）

**AI自动分析** + **用户可手动修正**

---

### 2. 📊 复合成功指标

不再只看"成功/失败"，而是综合评估：

```
成功分数 = 客观完成度(60%) + 主观评分(40%)
```

**示例**：
- 客观完成度：90%（完成了大部分任务）
- 主观评分：4/5（感觉还不错）
- 成功分数：0.9×0.6 + 0.8×0.4 = 0.86

这样能更准确反映实际情况！

---

### 3. 🤖 AI个性化建议

每次记录实践后，AI自动生成定制化建议：

**针对成功**：
- 正面激励
- 巩固策略
- 下一步建议

**针对失败**：
- 原因分析
- 改进方案
- 鼓励支持

**支持深入对话**：
- 可以追问AI
- 多轮对话
- 持续改进

---

### 4. 📈 分类统计分析

#### 按类型查看统计
- 触发型行为总览
- 习惯型行为总览
- 对比分析

#### 单个行动详细分析
- 总尝试次数
- 成功率趋势
- 平均成功分数
- 当前连续天数
- 最长连续记录

---

### 5. 📤 分析报告导出

一键导出完整分析报告：

**支持格式**：
- 纯文本（便于复制）
- Markdown（便于整理）

**包含内容**：
- 行动基本信息
- 统计数据
- AI建议
- 最近记录
- 生成时间

---

## 使用场景

### 场景1：培养晨练习惯

1. **创建行动**："每天早上7点晨练30分钟"
2. **AI识别类型**：习惯养成型
3. **每次记录**：
   - 客观：完成了25分钟（0.83完成度）
   - 主观：感觉不错（4/5分）
   - 成功分数：0.82
4. **AI建议**："坚持了25分钟已经很棒了！建议设置闹钟提醒，逐步增加到30分钟。"
5. **查看统计**：本周完成5/7天，坚持率71%

### 场景2：压力应对策略

1. **创建行动**："感到压力时做3次深呼吸"
2. **AI识别类型**：情境触发型
3. **记录实践**：
   - 今天工作压力大，做了深呼吸
   - 客观：完成3次（1.0完成度）
   - 主观：有效缓解（5/5分）
   - 成功分数：0.96
4. **AI建议**："深呼吸帮助你有效缓解了压力，建议在压力来临前就开始练习。"
5. **查看统计**：最近10次尝试，成功率90%

---

## API使用示例

### 记录实践（带复合指标）

```bash
POST /actions/1/practice
Content-Type: application/json

{
  "date": "2025-10-08",
  "result": "success",
  "rating": 4,
  "objective_completion": 0.9,
  "notes": "今天完成得不错"
}
```

**响应**：
```json
{
  "id": 123,
  "success_score": 0.86,
  "created_at": "2025-10-08T10:00:00Z"
}
```

### 获取AI建议

```bash
GET /actions/1/advice
```

**响应**：
```json
{
  "advice": "你在这个行动上表现很好！建议...",
  "session_id": "uuid-xxx"
}
```

### 与AI深入对话

```bash
POST /actions/1/advice-chat
Content-Type: application/json

{
  "message": "我应该如何提高完成度？"
}
```

### 按类型统计

```bash
GET /dashboard/stats/by-type?action_type=habit&days=30
```

**响应**：
```json
{
  "action_type": "habit",
  "total_actions": 5,
  "success_rate": 75.5,
  "average_score": 0.82,
  "completion_days": 23
}
```

### 导出分析报告

```bash
GET /actions/1/export?format=markdown
```

---

## 前端集成建议

### 1. 行为类型展示

```html
<div class="action-card">
  <span class="type-badge">
    {{ action.action_type === 'habit' ? '习惯养成' : '情境触发' }}
  </span>
  <h3>{{ action.action_text }}</h3>
</div>
```

### 2. 复合指标可视化

```javascript
// 使用进度环显示成功分数
<CircularProgress 
  value={practiceLog.success_score} 
  color={getScoreColor(practiceLog.success_score)}
/>

function getScoreColor(score) {
  if (score >= 0.8) return 'green';
  if (score >= 0.6) return 'yellow';
  return 'red';
}
```

### 3. AI建议卡片

```html
<div class="ai-advice-card">
  <h4>💡 AI建议</h4>
  <p>{{ action.ai_analysis }}</p>
  <button @click="openAdviceChat">深入讨论</button>
</div>
```

### 4. 分类统计仪表盘

```html
<div class="stats-dashboard">
  <div class="trigger-stats">
    <h3>情境触发型</h3>
    <p>成功率: {{ triggerStats.success_rate }}%</p>
  </div>
  <div class="habit-stats">
    <h3>习惯养成型</h3>
    <p>坚持率: {{ habitStats.completion_rate }}%</p>
  </div>
</div>
```

### 5. 一键复制功能

```javascript
async function copyAnalysis() {
  const response = await fetch(`/actions/${actionId}/export?format=plain_text`);
  const data = await response.json();
  
  await navigator.clipboard.writeText(data.content);
  showToast('分析报告已复制到剪贴板');
}
```

---

## 配置说明

### 环境变量

```bash
# .env 文件
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### 复合指标权重调整（可选）

如需调整权重，修改`app/routers/actions.py`中的`calculate_success_score`函数：

```python
# 默认：60%客观 + 40%主观
success_score = obj_score * 0.6 + subj_score * 0.4

# 可改为其他权重，如：
# 70%客观 + 30%主观
success_score = obj_score * 0.7 + subj_score * 0.3
```

---

## 最佳实践

### 1. 记录实践时
- **尽量填写客观完成度**：即使部分完成也有价值
- **诚实评分**：主观评分帮助AI理解你的真实感受
- **添加备注**：简短备注能帮助AI生成更好的建议

### 2. 查看建议时
- **及时查看**：实践后尽快查看AI建议
- **主动提问**：有疑问就使用建议对话功能
- **定期回顾**：每周查看一次统计报告

### 3. 导出报告时
- **定期导出**：建议每月导出一次
- **选择合适格式**：
  - 分享给他人：使用Markdown
  - 个人记录：使用纯文本
- **保存历史**：导出的报告可作为进步记录

---

## 技术架构

### 异步处理流程
```
用户记录实践 → 立即返回响应
                ↓
            后台任务队列
                ↓
         AI分析 & 建议生成
                ↓
            更新数据库
```

### AI模型选择
- **行动抽取**：deepseek-chat（快速）
- **行为分析**：deepseek-reasoner（深度）
- **建议生成**：deepseek-reasoner（个性化）

---

## FAQ

**Q: 为什么我的行动没有AI建议？**  
A: AI建议在你第一次记录实践后自动生成，可能需要几秒钟。如果长时间没有，请检查API密钥配置。

**Q: 能否修改行为类型？**  
A: 目前AI自动识别，未来版本将支持手动修改。

**Q: 复合指标如何计算？**  
A: 60%客观完成度 + 40%主观评分。即使没填写主观评分，系统也会根据结果推断。

**Q: 导出的报告包含哪些内容？**  
A: 包含行动基本信息、完整统计数据、AI建议和最近5次记录。

**Q: AI建议对话有次数限制吗？**  
A: 取决于你的API密钥配额，建议合理使用。

---

## 反馈与建议

如果你有任何建议或发现问题，欢迎：
- 提交GitHub Issue
- 发送邮件反馈
- 加入用户讨论群

---

**版本**: 2.0  
**发布日期**: 2025-10-08  
**下一个里程碑**: 可视化图表系统

