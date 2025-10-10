# 系统升级指南

## 概述
本指南帮助您将应用升级到新版本，添加智能行为分析和个性化反馈功能。

---

## 升级步骤

### 1. 备份数据库 ⚠️
```bash
# 备份当前数据库
cp app.db app.db.backup_$(date +%Y%m%d_%H%M%S)
```

### 2. 更新代码
如果使用Git：
```bash
git pull origin main
```

或手动替换修改的文件：
- `app/models.py`
- `app/schemas.py`
- `app/ai_service.py`
- `app/routers/actions.py`
- `app/routers/dashboard.py`

### 3. 执行数据库迁移 ✅
```bash
python migrate_add_new_features.py
```

**预期输出**：
```
============================================================
数据库迁移脚本：添加行为分析和复合指标功能
============================================================
开始数据库迁移...

1. 检查Action表...
  添加 action_type 字段...
  ✓ action_type 字段已添加
  ...

✓ 数据库迁移成功完成！
```

### 4. 验证环境变量
确保`.env`文件包含必要的配置：
```bash
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### 5. 重启应用
```bash
# 如果使用start_app.py
python start_app.py

# 或使用uvicorn
uvicorn main:app --reload
```

### 6. 验证升级 ✓
访问API文档查看新端点：
```bash
http://localhost:8000/docs
```

应该看到新增的端点：
- `/actions/{action_id}/advice`
- `/actions/{action_id}/advice-chat`
- `/actions/{action_id}/export`
- `/dashboard/stats/by-type`
- `/dashboard/stats/trigger-vs-habit`

---

## 功能验证清单

### ✅ 基础功能测试

1. **记录实践（带复合指标）**：
   ```bash
   curl -X POST "http://localhost:8000/actions/1/practice" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "date": "2025-10-08",
       "result": "success",
       "rating": 4,
       "objective_completion": 0.9
     }'
   ```
   
   **验证点**：响应中应包含`success_score`字段

2. **获取AI建议**：
   ```bash
   curl -X GET "http://localhost:8000/actions/1/advice" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
   
   **验证点**：返回AI生成的建议文本

3. **按类型统计**：
   ```bash
   curl -X GET "http://localhost:8000/dashboard/stats/by-type?action_type=habit" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
   
   **验证点**：返回习惯型行为的统计数据

4. **导出报告**：
   ```bash
   curl -X GET "http://localhost:8000/actions/1/export?format=markdown" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
   
   **验证点**：返回Markdown格式的分析报告

---

## 常见问题

### Q1: 迁移脚本报错"数据库文件不存在"
**A**: 确保在项目根目录执行脚本，且`app.db`文件存在。

### Q2: AI建议生成失败
**A**: 检查以下几点：
1. `DEEPSEEK_API_KEY`是否正确配置
2. API密钥是否有足够额度
3. 查看应用日志获取详细错误信息

### Q3: 现有数据的action_type都是null
**A**: 这是正常的，新创建的行动项会自动分析类型。可以通过以下方式手动触发分析：
```python
# 在Python shell中
from app.routers.actions import background_analyze_action_type_task
from app.database import SessionLocal
import asyncio

db = SessionLocal()
asyncio.run(background_analyze_action_type_task(action_id, db))
```

### Q4: 复合指标计算结果异常
**A**: 检查输入数据：
- `objective_completion`应在0.0-1.0范围
- `rating`应在1-5范围
- 确保`result`值正确（success/fail/partial/skipped）

---

## 回滚方案

如果升级后遇到严重问题，可以回滚：

### 1. 恢复数据库
```bash
cp app.db.backup_YYYYMMDD_HHMMSS app.db
```

### 2. 切换回旧版本代码
```bash
git checkout previous_version_tag
```

### 3. 重启应用
```bash
python start_app.py
```

**注意**：回滚后，新版本记录的数据（如AI建议）将丢失。

---

## 性能优化建议

### 1. 数据库索引
为新字段添加索引以提升查询性能：
```python
# 在数据库中执行
CREATE INDEX idx_action_type ON actions(action_type);
CREATE INDEX idx_success_score ON practice_logs(success_score);
```

### 2. AI调用限流
如果用户量大，建议添加限流机制：
```python
# 在config.py中添加
AI_RATE_LIMIT = 100  # 每小时最多100次AI调用
```

### 3. 缓存配置
为统计数据添加Redis缓存（可选）：
```python
# 安装Redis依赖
pip install redis

# 在dashboard.py中添加缓存装饰器
from functools import lru_cache
```

---

## 监控建议

### 关键指标监控
1. **AI服务调用成功率**
2. **复合指标计算性能**
3. **后台任务队列长度**
4. **数据库查询响应时间**

### 日志配置
在`app/config.py`中调整日志级别：
```python
LOGGING_LEVEL = "INFO"  # 生产环境使用INFO
```

---

## 后续步骤

升级完成后，建议：

1. **用户培训**：
   - 向用户介绍新功能
   - 提供使用示例和最佳实践

2. **数据迁移**：
   - 为现有行动项触发行为类型分析
   - 补充历史数据的复合指标

3. **前端更新**（如适用）：
   - 添加行为类型筛选器
   - 实现分析报告导出UI
   - 添加AI建议对话界面

4. **监控与优化**：
   - 监控AI服务使用情况
   - 根据用户反馈优化建议质量
   - 调整复合指标权重配置

---

## 技术支持

如遇到问题，请检查：
1. 应用日志：`logs/app.log`（如有）
2. 数据库状态：`python migrate_add_new_features.py`查看统计
3. API文档：`http://localhost:8000/docs`

或参考：
- `IMPLEMENTATION_SUMMARY.md`：详细实施说明
- `README.md`：项目总体说明
- GitHub Issues：提交问题

---

**升级版本**: v1.0 → v2.0  
**文档更新**: 2025-10-08  
**估计升级时间**: 5-10分钟

