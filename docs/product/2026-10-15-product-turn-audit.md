# 产品转向：清理边界与增量迁移草案

状态：逐文件核对及代码实施记录。基线为 `origin/main` 的 `2bdafaa`（书然 2.0）；生产备份、迁移和部署仍由服务器操作人执行。本稿不授权删除历史数据。

## 逐文件清理范围

| 文件 | 处理 | 依赖与保留边界 |
|---|---|---|
| `app/routers/ebooks.py` | 解除注册并删除 | 仅 EPUB API；保留 `app/models.py` 中 Ebook、Chapter、Note、Progress 归档模型与上传卷。 |
| `static/js/epub-reader.js`、`static/css/epub-reader.css` | 删除 | 移除 `static/index.html` 引用、书架和读书笔记页面；上传文件不清理。 |
| `static/dashboard.html`、`static/dashboard.js` | 删除 | 独立旧看板；不触及 2.0 方法卡的使用反馈。 |
| `app/routers/dashboard.py` | 解除注册并删除 | 现有调用来自旧首页/旧看板；核对后保留 `actions.py` 的行动项及践行写入接口。 |
| `static/index.html` | 局部修改 | 去阅读导航、上传笔记/EPUB、阅读提醒、首页旧统计卡、实践统计和看板入口；保留方法卡、今日待办、日程、时刻、idea、以后想做、行动项及个人中心。 |
| `static/js/today-dashboard.js` | 局部修改 | 去阅读时长和阅读记录交互；保留今日待办、行动与自我对话调用。 |
| `static/js/app-tabbar.js`、`static/js/i18n.js`、`static/css/desktop-split.css` | 局部修改 | 去阅读和旧统计入口/文案/无用样式；保留 2.0 方法卡与日程导航。 |
| `app/routers/today.py` | 局部修改 | 去 `/reading-entries` 与 overview 阅读字段；保留 todos、行动/践行/自我对话 overview。旧客户端只保留仍服务非阅读功能的路由。 |
| `app/routers/actions.py`、`app/schemas.py`、`app/ai_service.py` | 依引用局部修改 | 去读书笔记上传/抽取专用入口和无调用方的旧统计 API；保留 Action CRUD、践行记录、习惯计划与 AI 的其他功能。 |
| `app/scheduler.py`、`app/self_talk/reminder_service.py`、`app/routers/self_talk_reminders.py`、`static/reminder_notification.js` | 局部修改 | 停止产生新阅读提醒；保留待办、自我对话与行动提醒。历史提醒日志仍在库中。 |
| `mobile/android/app/src/main/java/com/shuran/app/ReminderScheduler.java`、`ReminderNotifications.java`、`ReminderAlarmReceiver.java`、`AndroidManifest.xml`、中英 `strings.xml` | 局部修改 | 新 APK 升级时按旧 action/request code 取消已登记阅读闹钟并清除阅读通知，再去掉阅读调度；待办及“记”的原生入口保留。未升级的旧 APK 无法由服务器取消本机闹钟。 |
| `app/models.py`、`app/database.py`、`app/backup.py` | 保留并增量扩展 | `ReadingEntry` 与 EPUB 模型作为历史归档；`Action.book_title`、`PracticeLog`、`HabitProgram`、`DailyTask.action_id` 保持原值与关系；逻辑备份继续包含阅读记录，新结构另加入导出或以完整 PostgreSQL 备份覆盖。 |
| `app/routers/schedule.py`、`static/js/daily-schedule.js`、`static/js/time-log.js`、`static/js/ideas.js` | 保留，后续阶段局部扩展 | `FutureAction` 数据与日程任务数据原样保留；“以后想做”入口移到“记”，不转换成项目下一阶段任务。主工作树的 `static/js/time-log.js` 已有用户改动，不覆盖。 |
| `tests/test_epub_titles.py`、`tests/test_ebook_note_collection.py`、`tests/test_schedule_ui_separation.py` | 更新 | 删除过时 EPUB/阅读入口断言，增加保留业务和路由退出的验证。 |
| `docs/书然使用说明书.md`、`README.md`、现行营销/下载页 | 更新现行文案 | 历史软著、申请和旧发布记录不批量改写。 |

另需检查 `static/ai_advice.html` 的 `book_title` 展示：它仍可显示历史 Action 来源，不能因移除阅读入口而破坏历史行动项详情。2.0 新增 `method_cards`、`method_uses`、`method_visits` 与方法卡页面；交接仅授权删除旧“实践统计/数据看板/首页旧统计”，这些新数据和页面保留。

## 增量迁移草案

1. 上线前由服务器操作人对 PostgreSQL 做自定义格式 `pg_dump`，对 `uploads_data` 做完整 tar 备份；验证备份可列出内容。`app/backup.py` 的 CSV 压缩包缺 EPUB 文件、删除行与部分表，不能代替全量备份。记录所有业务表行数、关键表按用户行数、索引/外键及上传文件清单；部署后再次核对。
2. 项目骨架只新增 `goals`、`projects`、`project_stages`、`project_tasks`、`task_dependencies` 和必要索引；`daily_tasks.project_task_id` 可空，旧行保持 `NULL`。项目任务有稳定 ID、用户归属、阶段与状态；前置关系加同项目与同用户校验、唯一边、自依赖及环检测。阶段/任务采用软删除或受限制删除，不能级联删除历史工作片。
3. 时间反馈新增 `work_sessions`：用户、稳定项目任务（简单日程任务可选）、起止时间、工作/休息类型、计时/手动/确认时刻来源、状态、更正原因。估时分别保存初始估计与当前估计或修订记录；旧 `TimeLogNode.duration_seconds` 及 `DailyTask.priority`、`parallel_group` 不回填成实际工作、重要性或依赖。工作片允许跨天；任务实耗按不重叠的工作区间累加，“记”的日/周回看在边界处裁切。重叠片段拒绝写入或要求用户先更正，避免重复累计。
4. 活动评价单独关联实际活动区间：三级重要性可空，另存可选“有趣”、评价时目标 ID 与目标文字快照、评价时间。目标改名不能改写历史判断。检查项、验收结果、预演笔记和流程模板分别用新增表；模板复制为任务实例，历史实例不随模板更新。
5. `ensure_schema()` 只能做幂等新增，PostgreSQL 迁移放在事务中，异常必须回滚；SQLite 测试验证已有库升级。任何阶段都不执行 `DROP TABLE`、`TRUNCATE`、批量 `DELETE`、卷清理或自动历史重写。

## 分阶段验收门槛

- 阶段一：保留工作区原有改动；用户确认服务器备份和基线快照已完成后，才允许生产部署与自动迁移。
- 阶段二：阅读和三处旧统计入口/API 退出；行动、习惯、自我对话、待办、日程、“记”、账户、方法卡正常；新版 Android 不再安排阅读提醒。
- 阶段三：A 是 B 前置时 B 受阻，C 可同阶段推进；禁止环，简单任务仍可直接入日程。
- 阶段四：`A 20 → B 20 → A 20` 汇总为 A 40、B 20；休息不计，重叠补记不给虚假总时长。
- 阶段五：未标记重要性保持空值；原估计与实耗并列，检查项和验收分开。
- 阶段六：空白流程和从任务保存均可用，修改模板不追改历史实例。

生产部署由用户执行。每次可见版本更新同步更新版本名、`versionCode` 与网页静态版本号；提交与推送只包含本阶段文件。

## 六阶段代码实施与实际验证

1. **基线与保护**：在独立工作树实施，原 `D:\projects\reading-feedback-app` 的既有未提交改动没有暂存、覆盖或删除。生产行数、上传文件数与备份尚待服务器操作人执行。
2. **旧功能退出**：EPUB/阅读记录写入、读书笔记抽取、旧实践统计和独立看板路由与页面资源已解除注册/移除；阅读历史模型仍保留。Android 新版启动时取消旧阅读闹钟、清除通知与本机旧偏好，未升级旧 APK 不受服务器远程控制。Action、Practice、Habit、自我对话、待办、方法卡和账户数据不删。
3. **项目骨架**：新增目标、项目、当前/下一阶段、任务、检查项与同项目真实前置依赖。项目任务可选写入当天 `DailyTask`；既有日程行的关联仍为 `NULL`。
4. **执行与反馈**：工作/休息片、切换、暂停、手动补记和用户确认的时刻来源；单用户片段禁止重叠，单片超过 24 小时须填写实际结束时间或拆段。任务保留原估计和当前估计，实耗只算已完成的工作片。
5. **质量与反思**：验收结果、偏差原因、预演和难点、检查项分区；“记 → 时间日志”按日/周回看实际活动和三级目标相对重要性，未标记为 `NULL`，评价时的目标标题另存快照。计时片到时给一次克制的困难提示。
6. **流程库与长期计划**：目标期限由用户逐步延长；流程可从空白或任务建立，生成独立任务实例。主动伴随任务经复核暂不增加：当前缺少不重复记时的直观输入方式；保留单主任务时间片规则，日后如需支持应把伴随角色关联同一工作区间，并对自然时间取并集。

已运行 SQLite 幂等增量迁移测试：模拟旧 `daily_tasks` 行，连续两次升级后原日程、阅读、待办行仍在，新增项目表和可空外键存在。项目接口、历史阅读/EPUB 逻辑备份、UI 分区及旧功能退出测试通过。浏览器加载了首页、项目页与“记”的活动回看，没有页面脚本异常。完整测试结果见提交报告；Android 本地 Gradle 编译与生产 PostgreSQL/上传卷核验不在此测试结果内。

**生产前置检查**：服务器操作人先按交接文档第 6 节完成 `pg_dump -Fc` 与 uploads 卷 tar 并验证归档，再保留部署前后关键表行数与上传文件清单。迁移只执行 `CREATE TABLE`、`ADD COLUMN`、`CREATE INDEX`，不执行表/行/卷删除。发布 Android 更新前应确认 `android-2.0.1` 签名包与 `versionCode 43` 匹配；`/download/info` 在包未就绪时会显示不可下载。
