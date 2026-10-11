# 书然：产品与代码交接（给本地 Codex）

交接日期：2026-10-11。目标版本：网页及 Android 源码 1.5.25 / versionCode 41。静态资源版本：`20261010methods1`。

本文件用于继续修改用户自己的书然仓库，完成验证、GitHub 推送和香港服务器发布。产品方向已经确定，应先把可用版本推出去，通过真实使用反馈继续迭代。

## 1. 可以直接给本地 Codex 的任务

> 请先完整阅读本文件和本地仓库的 AGENTS.md。目标项目是书然 `wu716/reading-feedback-app`，不是独立的 reader-app。
>
> 本轮产品路线已经确定：以“情境 + 第一步”的方法卡为首发核心，直接发布可用版本收集市场反馈。不要重新设置“再找到两个人”“达到三个人”“先做七天人工实验”的开发门槛，不要要求用户再次批准已经确定的设计。
>
> 云端工作区已完成一版实现，交付包包含 `shuran-1.5.25.patch`。先检查我的本地仓库、远端、分支、未提交改动和版本，核对补丁；能安全应用时直接应用。若本地已变化，请保留我的改动，将补丁的相关改动合并进去，不要机械覆盖，也不要从零重写整个产品。
>
> 按本文核对产品行为，运行测试，补齐浏览器和 Android WebView 的实际验收，修复本轮相关问题。将本轮变更提交并推送到 `origin/main`，随后 SSH 到香港服务器更新 Docker Compose，核对部署提交、版本、健康检查和核心流程。不要只修改本地代码就宣布完成；真实权限或网络问题阻塞时，明确报告阻塞步骤和可执行补救命令。
>
> 只提交本轮相关文件，不提交密钥、环境文件、APK 或原有无关改动；不强制推送、不清空数据库。结束时分别报告本地代码、GitHub、生产服务器、网页版本和 APK 的状态，并告诉我代码实际在哪个本地目录。

## 2. 项目与交接状态

| 项目 | 准确信息 |
| --- | --- |
| 产品 | 书然 / Shuran，原阅读反馈应用 |
| GitHub | `https://github.com/wu716/reading-feedback-app.git` |
| 用户本地目录 | `D:\projects\reading-feedback-app`；执行前用远端地址确认，路径存在不等于项目正确 |
| 本轮补丁基线 | `1aee89bf339466e87a0e41ac78ea637afe1323da`，原 `origin/main`，提交说明 `Show future task section` |
| 技术结构 | FastAPI、SQLAlchemy、原生 HTML/CSS/JavaScript；开发 SQLite，仓库生产 Compose 使用 PostgreSQL；Android 为 WebView 壳 |
| 服务器 | `ubuntu@43.161.238.165`，项目 `/opt/shuran-app`，Compose 目录 `deploy/aliyun` |
| 现有访问地址 | `http://43.161.238.165:8000`；上线验收后方法入口为 `/#methods` |
| 源码版本 | 网页及 Android 源码 `1.5.25`，Android `versionCode 41` |
| 静态缓存版本 | `20261010methods1`；健康检查同时返回应用版本和静态版本 |
| 云端已做 | 代码修改、自动检查、首发设计说明、发布说明，以及本交接文件 |
| 云端未做 | 未成功推送 GitHub，未更新生产服务器，未构建新 APK，未进行浏览器视觉和 Android 真机验收 |

此前推送预检查报 `could not read Username for 'https://github.com'`，SSH 连接报 `Network is unreachable`。本地 Codex 接手应用补丁、推送和服务器发布；当前线上不能视为已经更新。补丁是实际代码交付，不是“远端已经有这次修改”的通知。

交付包还有：`method-cards-launch.md`（首发设计）、`method-cards-release.md`（原发布步骤）、补丁和校验说明。本文件是接手的主入口。若本地发现远端已有本轮改动，先核对文件和行为，不重复应用。

## 3. 产品思考：这次为什么这样做

### 3.1 从宽泛问题收敛到一个可以使用的场景

前面的讨论围绕阅读、思考和现实践行：读了书、学过方法、留下笔记，为什么遇到实际问题时仍然用不上？“知而不行”可能来自忘记、找不到、步骤太复杂、方法不适合情境、环境打断等多种原因，不能用一个笼统标签解释所有人。

本次选择一个窄假设：**用户已经学过或试过某个方法；相似问题再次出现时，希望容易找到它，并马上知道先做哪一步。** 让产品先服务这个场景，再观察人们是否真的会回来用。

此前也讨论过阅读整理、观点形成、跨书连接和写作等更宽方向。它们属于探索背景，本次没有被选为首发主线。不能因此把本轮改成知识库重构、写作工具或独立阅读器开发。

### 3.2 当前产品表达

**一句话：让学过的方法，用得上。**

更完整的说明：把阅读获得或自己试过的方法，写成“遇到什么情况”和“先做哪一步”；遇到问题时拿出来试，留下很短的反馈，逐渐知道哪些方法适合自己。

工作中的目标用户描述是：已经有一些方法来源，在相似情境里有调用和尝试需求的人。这个描述用于设计和发布沟通，仍需由真实使用检验，不能写成已经验证的市场细分。

### 3.3 核心闭环及希望出现的价值时刻

阅读或已有经验获得方法 → 压缩成情境与第一步 → 现实中尝试 → 极简反馈 → 修改、暂放或保留为个人可复用方法。

希望出现的价值时刻是：用户再次遇到问题，快速找到一张相关卡片，看到明确的第一步，并实际做了一次。保存很多卡片或页面更漂亮，都不足以证明这个价值已经出现。

“有效”首先指使用者认为在某次情境中有帮助；不是普遍适用、不是客观效果证明，也不是产品已证明能改变行为。当前程序还不会自动识别现实情境并弹出提醒，用户需要主动打开、搜索、选择；是否愿意主动回来调用，也是待验证的问题。

### 3.4 证据与发布路线

当前讨论中明确匹配需要的对象只有 **1 人**。单个人的描述可以提示问题、帮助设计，不能代表市场需求已得到验证。此前更广的案例讨论也不能等同于多名同类产品用户的验证。

用户已经决定直接推出产品看市场反馈。取消“继续找两个人、凑够三个人、完成七天人工实验之后才允许开发”的安排。访谈可以在上线后帮助理解具体障碍，但不再是发布前置条件。

产品判断以实际保存、尝试、再次调用、主动意见以及后续推荐或付费等行为逐步校正。当前版本没有实现推荐、支付或标准留存分析，不能在报告里声称拥有这些数据。一次使用、无人回复、少量访问，都不能单独证明成功或失败。

## 4. 已确定的决策与边界

| 决策 | 接手时应保持的行为与原因 |
| --- | --- |
| 先推出可用版本 | 用实际使用制造新证据；不重新增加人数门槛 |
| 方法卡成为默认首页 | 首次进入就能理解并体验核心任务 |
| 只要求情境和第一步 | 降低写卡成本，让动作具体；标题、来源和摘录选填 |
| 按一次现实尝试反馈 | 同一天可以多次尝试，不改成每天必须完成的打卡任务 |
| 三种结果分开 | “有帮助”“没帮助”表示试过；“没用上”不能计入试过或失败惩罚 |
| 先做自己的方法库 | 支持找回、修订、暂放和恢复，不把收藏数量当作效果 |
| 阅读和旧行动作为来源 | 用户主动选择、核对后保存，不自动迁移全部旧数据 |
| 保留现有工具和数据 | 日程、阅读、行动、Self-talk、账号继续可用；本轮调整核心入口 |
| 允许访客先体验 | 不先强迫注册；体验数据在本浏览器，登录后主动选择导入 |
| 保持真实指标 | 不伪造用户、成功率、连续打卡或示例成绩；体验与正式账号使用分开 |
| 一处只承担一类操作 | 属性、排序、状态分区；遵循 AGENTS.md，不叠加隐蔽手势 |
| 控制本轮开发范围 | 自动情境识别、复杂提醒、社区、支付、全面知识库重构均未纳入首发 |

独立的 `reader-app` 是另一个项目。本轮不改它的数据库、模型、读书总结流程，也不把两个产品合并。

## 5. 首发范围与关键交互

### 5.1 方法卡

- 必填：`situation`（遇到什么情境）、`first_step`（先做哪一步），各 1–500 字。
- 选填：标题（最多 120 字）、来源名称（最多 255 字）、摘录（最多 2000 字）。无标题时由第一步生成简短标题。
- 支持创建、编辑、关键词搜索、使用中/暂放筛选、暂放、恢复和移除。移除为服务端软删除。
- 登录用户搜索针对自己的服务端卡片；列表最多返回 100 张，超过时说明数量。访客体验最多保存 100 张。
- 示例仅帮助填写，必须主动选择和保存；不预置使用次数或帮助效果。

情境应尽量具体，比如“讨论时开始急着反驳”；第一步应是可执行动作，比如“先复述对方刚才最在意的一点，再确认自己理解得对不对”。这是写法示例，不代表已验证的需求或效果。

### 5.2 来源带入

已有行动可从编辑器选择，EPUB 的流程类笔记可点“做成方法卡”。程序带入动作、来源或摘录，用户补充并检查情境后保存。不改写原行动或 EPUB 笔记，不进行全量自动转卡。

| 原有模块 | 本轮关系 |
| --- | --- |
| 阅读 / EPUB | 获得方法与保留出处；增加流程类笔记带入方法卡的入口 |
| 行动 Action | 保留原行动能力，可手动带入；方法卡不沿用每日目标语义 |
| 日程 | 保留安排事情的能力；本轮没有自动把卡片排入日程 |
| Self-talk | 保留原反思和提醒功能；新闭环不要求先写完整日复盘 |
| 随手记 | 保留原捕捉入口；没有自动把所有随手记变成方法卡 |

### 5.3 一次尝试和反馈

1. 点“遇到了，先试一下”，创建待反馈尝试，展示当时的情境与第一步。
2. 用户实际尝试后选择“试了有帮助”“试了没帮助”或“这次没用上”。开始按钮本身不能视为已执行。
3. 没帮助或没用上时，可选原因：忘了、动作太难、被打断、不适合、其他；备注可选，最多 500 字。
4. 最近尝试可以补充或改正结果；同一天允许新的独立尝试。
5. 每张卡片最多有一条未反馈尝试；已有待反馈时回到它，双窗口并发开始也不重复创建。
6. 编辑卡片不会改写历史尝试，历史保留启动时的情境与动作快照。

页面不要求每日完成率、连续打卡、漏用惩罚或强制长复盘。没有用上是理解使用障碍的线索。

### 5.4 访客、登录与注册

访客无需登录即可保存和尝试体验卡片，卡片及体验尝试只保存在当前浏览器 `localStorage`，清理浏览器或更换设备可能丢失，界面需要明确说明。

登录后，用户可以主动把体验卡片存入当前账号；导入采用稳定的 `client_key`，部分失败后重试不会重复，已确认保存的卡片才从本地体验区移除。**体验尝试不迁入正式账号的尝试数据。** 暂放状态目前也没有随体验导入迁移，导入创建为使用中的账号卡片，不要声称这是完整跨端同步。

注册仍沿用一次性邀请码。访客先体验已经实现，“任何人都能直接注册”尚未实现。发布时由站长使用原有开通入口发码；若邀请码成为主要障碍，下一阶段再针对门槛做决定，不能悄悄重写账号系统。

手机主导航为“方法、日程、阅读、记、我的”，旧行动和 Self-talk 从“我的”进入；桌面侧栏保留原工具并加入方法。Android 返回键应先关闭方法弹窗，再交给原页面返回逻辑。

### 5.5 产品意见和站长页面

访客与账号用户都可以主动提交“使用问题 / 改进建议 / 有帮助的地方”，正文 3–1500 字。提交失败保留内容，成功后才提示已发送。

站长通过“我的 → 站长开通”进入，查看近 7 天汇总和最多 50 条近期主动意见。普通账号不能读这个接口。市场反馈接口不展示私人卡片、书籍摘录和尝试备注；原有站长导出备份仍具有管理数据访问能力，不能笼统声称管理员完全无法接触业务数据。

## 6. 市场反馈的口径与发布沟通

窗口为北京时间近 7 个自然日，从第一个日期零点起算。当前看板是分项计数，不是同一获客队列的完整漏斗。

| 字段 / 展示 | 实际含义 | 判断时的限制 |
| --- | --- | --- |
| `visit_sessions` 访问会话 | `opened` 匿名事件的去重页面会话数 | UUID 存在 `sessionStorage`；不是人数或 UV，同一会话同类事件只记一次 |
| `demo_sessions` 体验事件 | 保存、开始、反馈分别发生过的会话数 | 只报事件，不传卡片与反馈内容；不是正式账号试过人数 |
| `created_users` 保存卡片账号 | 窗口内创建了仍未移除卡片的不同账号数 | 表示保存，不等于在现实中使用 |
| `started_users` 发起尝试账号 | 窗口内有开始记录的不同账号数 | 不等于动作已执行 |
| `tried_users` 记录试过账号 | 窗口内完成 helpful / not_helpful 反馈的不同账号数 | 依据用户自报，不含 not_used |
| `returning_users` 不同日期试过 | 在窗口内启动且完成上述反馈，并有至少两个北京时间启动日期的账号数 | 不是标准 D7 留存；反馈完成时间也需在窗口内 |
| 帮助 / 没帮助 / 没用上 | 窗口内对应反馈记录的次数 | 可以改正，计数随现存数据变化；不是固定实验数据或客观效果 |
| 主动意见 | 用户明确选择发送的产品意见 | 与私有的某次尝试备注不同 |

所有方法汇总排除已移除卡片；移除卡片、注销、改正反馈可能改变历史窗口计数。匿名事件按首次记录时间归入窗口，不是每次点击的次数。当前没有来源归因、标准队列留存、渠道转化率或自动剔除技术测试账号；上线烟雾测试也可能进入看板，分析时应标注。不要把各项直接相除后称为转化率。

第一轮看真实行为和具体阻碍：有人写自己的情境吗？只是保存还是实际试过？之后会回来吗？说没帮助时，到底是哪一步或哪个场景不合适？没人用时，先辨别曝光不足、注册门槛、入口不清楚、不会写卡、找不到方法或没有价值，不单靠一个总数下结论。

上线验证后可使用的简短发布文案：

> 我做了一个叫“书然”的小工具：把学过的方法写成“什么时候用、先做哪一步”。遇到相似问题时拿出来试，顺手记一下有帮助、没帮助，还是这次没用上。现在可以直接在浏览器体验；如果有卡住的地方，点“反馈”告诉我具体发生了什么。

这是一段待用户自行发送的文案；本轮没有替用户发送消息或招募。链接只有在生产验收通过后才用于发布，注册说明要如实标注邀请码。

## 7. 后续规划与优先级

以下是基于本轮方向的执行规划，尚未实现的内容应保持“待判断 / 待开发”状态。

| 阶段 | 要做的事 | 进入下一步的依据 |
| --- | --- | --- |
| 首发收尾，当前优先 | 本地合并补丁、验证核心流程、真实浏览器与 WebView 验收、推送并部署，确保访客体验、发码和意见入口可用 | 可以真实打开并完成核心流程，数据保存可靠，发布状态可核对 |
| 上线后连续观察 | 看保存、试过、跨日调用和主动意见；必要时对具体反馈做简短追问 | 真实使用暴露出的具体障碍；不等待规定人数或固定人工试验结束 |
| 先修阻碍 | 根据证据改善填写引导、搜索找回、第一步大小、来源带入和体验到账号的衔接 | 同一障碍有实际案例或阻塞核心流程；一次改动对应一个可观察改善 |
| 再增强复用 | 如果用户确实回来调用，再考虑更清晰的个人方法整理、历史查看、分页或低负担提醒 | 用户的调用需求与现有能力不足，不凭理论一次扩充全部功能 |
| 评估扩展与经营 | 若后续出现推荐、支付意愿或更强场景需求，再考虑收费、分发和扩展 | 使用证据与经营反馈；当前不声称已验证付费需求 |

自动情境提醒、AI 生成卡片、复杂方法分类、社区、完整重构和商店上架均不是这次必须补齐的内容。Android 新 APK 可按现有构建流程单独发布；本次先让服务器网页版本可用，不能为没有生成的包改写下载元数据。

保持产品判断和代码任务相连：用户写不出第一步，就改善写卡；保存后找不到，就改善调用；方法太难，就帮助缩小动作。不要因为另一套理论更漂亮而把整个产品再次推翻。

## 8. 本轮代码地图

| 文件 | 修改目的 |
| --- | --- |
| `app/models.py` | 新增 MethodCard、MethodUse、MethodVisit、ProductFeedback 与用户关系、去重和待反馈唯一索引 |
| `app/routers/methods.py`（新增） | 方法 CRUD、来源、尝试反馈、匿名事件、主动意见、站长统计 |
| `main.py` | 注册路由、1.5.25 版本、静态版本、方法接口禁用缓存、健康检查版本 |
| `app/backup.py` | 逻辑备份增加方法卡、尝试和产品意见 CSV |
| `app/anonymization.py` | 注销清理方法及尝试快照、用户主动意见，匿名化访问记录关联 |
| `static/index.html` | 默认方法页、弹窗、访客说明、我的入口、站长反馈、登录事件及返回逻辑 |
| `static/css/methods.css`（新增） | 方法页面与弹窗的响应式样式 |
| `static/js/methods.js`（新增） | 服务端交互、访客体验、导入重试、反馈、账号切换、市场看板 |
| `static/js/app-tabbar.js` | 新手机主导航 |
| `static/js/epub-reader.js` | 流程类 EPUB 笔记做成方法卡的入口 |
| `static/js/i18n.js` | 导航等相关文字 |
| `mobile/android/app/build.gradle` | 源码 versionName 1.5.25、versionCode 41；保留原 CRLF 行尾 |
| `tests/test_methods.py`（新增） | 10 项 HTTP、数据库、权限、并发及统计检查 |
| `tests/frontend/*`（新增） | jsdom 依赖定义与 4 项模拟交互检查；不进入生产依赖 |
| `tests/test_schedule_ui_separation.py` | 手机导航断言按新入口更新，继续检查原工具入口存在 |
| `README.md`、`CHANGELOG.md` | 定位与实际更新说明 |
| `docs/product/*.md`（新增） | 首发设计、发布说明、本交接 |

`releases/latest.json` 未更新，旧 Android 下载继续描述实际已有 APK。没有修改旧日程排序实现、APK 下载业务实现或生产环境文件。

### 8.1 数据与正确性要求

| 表 | 核心职责 |
| --- | --- |
| `method_cards` | 账号、client_key、情境、第一步、来源、active/paused 状态及软删除 |
| `method_uses` | 账号、卡片、client_key、启动时快照、结果、原因、备注、起止时间 |
| `method_visits` | 随机会话 UUID、事件名称、可选账号关联和首次时间；无卡片内容 |
| `product_feedback` | 用户主动意见、分类、会话 UUID、可选账号和时间 |

新增表由现有 `ensure_schema()` → `Base.metadata.create_all()` 追加创建。本轮没有重写旧表、旧 Action / PracticeLog，也没有独立的新 Alembic 迁移；不要照搬 reader-app 的迁移方案。此前创建过部分新表的本地环境，需要实际核对表与索引，不假设 create_all 会修复已有表结构。

`(user_id, client_key)` 保证卡片或尝试的请求幂等；`uq_method_pending_card` 用 SQLite/PostgreSQL 部分唯一索引约束同一账号、同一卡片只有一条未反馈尝试。只靠前端禁用按钮不能替代数据库约束。

所有卡片、尝试、来源查询按当前账号限制；来源笔记需验证所有权。方法接口响应与前端 fetch 禁用缓存，切换账号清空旧显示，并丢弃过期的卡片响应。匿名统计只报随机 UUID 和事件，不带账号认证头或私有内容；正文展示必须转义。

备份新增 `method_cards.csv`、`method_uses.csv`、`product_feedback.csv`，没有纳入匿名事件表，也不是完整可自动恢复的数据库备份。发布前数据库完整备份与原录音/上传文件保留仍按生产部署方式处理，不能把 CSV 导出当成完整恢复能力。

### 8.2 接口清单

以下均以 `/api/methods` 为前缀。

| 方法与路径 | 权限 | 功能 |
| --- | --- | --- |
| `POST /visits` | 访客或账号 | opened / demo_saved / demo_started / demo_feedback；同会话同事件去重 |
| `POST /product-feedback` | 访客或账号 | 主动提交意见；按 IP 限流 |
| `GET /market` | 站长 | 近 7 天分项汇总和近期意见 |
| `GET /sources` | 当前账号 | 最多 50 条自己的已有行动作为来源 |
| `GET` 空路径 | 当前账号 | 卡片列表、搜索、状态、计数、待反馈和最近 5 次已反馈尝试 |
| `POST` 空路径 | 当前账号 | 幂等创建卡片 |
| `PUT /{card_id}` | 所属账号 | 修改内容或 active/paused |
| `DELETE /{card_id}` | 所属账号 | 软移除，不再出现在正常列表 |
| `POST /{card_id}/uses` | 所属账号 | 开始或返回现有待反馈尝试 |
| `PUT /uses/{use_id}` | 所属账号 | 反馈、补充或改正 |

## 9. 已验证的结果与剩余验收

交接时新增 **10 项后端测试、4 项前端模拟交互测试均通过**。全套 Python 测试为 **46 通过、3 失败**。这 3 项已在未修改的基线 `1aee89b` 上复现：

- `tests/test_legacy_origin.py::LegacyOriginTests::test_build_info_min_is_floor_not_latest`
- `tests/test_legacy_origin.py::LegacyOriginTests::test_singapore_update_info_stays_on_singapore`
- `tests/test_schedule_ui_separation.py::ScheduleUiSeparationTests::test_design_mode_contains_attributes_but_no_ordering_controls`

前两项涉及旧 APK 下载信息与断言，第三项涉及旧日程设计模式。应如实报告既有失败，不把全套测试说成全绿；本轮没有改这些业务实现，也不要单纯删除断言来变绿。如果本地出现新增失败，应定位并修复本轮造成的问题。

已检查：应用导入、添加新表、首页、访客与认证接口、健康检查版本、PostgreSQL 表和部分索引 DDL 编译、修改的外部与内联 JavaScript 语法、新增方法 ID 唯一性、diff 空白检查。PostgreSQL 编译不等于在真实生产数据库执行成功；jsdom 不代替视觉、触屏或 WebView 验收。

本地环境独立运行测试，不能直接使用文档中云端 venv 路径。可在发布 worktree 内使用以下 PowerShell 命令；依赖安装应使用现有可用 Python 环境，生产 requirements 不因 TestClient 兼容问题而改动。

```powershell
python -m venv .venv-methods-check
$releasePython = Join-Path (Get-Location) '.venv-methods-check\Scripts\python.exe'
& $releasePython -m pip install -r requirements.txt pytest 'httpx<0.28'
if ($LASTEXITCODE -ne 0) { throw '安装测试依赖失败。' }
& $releasePython -m pytest -q tests/test_methods.py --disable-warnings
if ($LASTEXITCODE -ne 0) { throw '方法卡测试失败，请修复。' }
& $releasePython -m pytest -q --disable-warnings
# 全套测试的已知 3 项失败见上文；核对输出，不能忽略新增失败。

Push-Location tests/frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw '前端测试依赖安装失败。' }
    npm test
    if ($LASTEXITCODE -ne 0) { throw '前端模拟交互测试失败。' }
} finally { Pop-Location }
```

不要暂存 `.venv-methods-check`。前端 `node_modules` 和锁文件由本轮测试目录的 `.gitignore` 忽略。

本地 Codex 必须补齐以下实际验收并报告：

1. 桌面浏览器与手机窄屏：初次访问能进入方法；弹窗、按钮、输入、键盘和滚动可用，没有遮挡。
2. 访客：写两项保存，刷新保留，开始、三类反馈、搜索、编辑、暂放和恢复正常；示例无伪造成绩。
3. 登录：选择导入；部分失败重试没有重复，不把体验尝试混入账号；退出并切换账号不露出前一账号内容。
4. 账号尝试：开始不算试过，反馈后计数更新，同日多次允许；修改卡片不改旧快照，双窗口不重复待反馈。
5. 来源与旧工具：已有行动带入、EPUB 流程笔记带入正常；日程、阅读、行动、Self-talk 和账号原功能没有被入口调整阻断。
6. 意见与看板：提交失败保留文字、成功后出现；普通账号无站长权限，站长实际能查看汇总与意见。
7. Android 已有 WebView：服务器更新后拉取新页面，返回键先关闭弹窗；真实安装包的版本与下载元数据一致。

## 10. 本地应用与提交推送

### 10.1 执行顺序

1. 读取当前仓库 AGENTS.md，核对 `git remote -v`、分支、HEAD、状态和版本，不打印环境文件或凭据。
2. 下载并解压交付包，核对补丁基线；检查远端是否已经包含这次变更。
3. 有本地未提交改动时，使用独立 worktree 合并本轮，不覆盖或自动清理用户工作区。
4. `git apply --check` 成功后应用；失败则针对当前代码合并，不用跳过检查或强制重置来解决。
5. 运行自动检查与实际验收，审阅 diff，确认只包含本轮变更后提交。
6. 推送并核对远端提交；成功后才部署服务器。

如果本地或远端版本已经超过 1.5.25 / 41，不能降级版本；保留新版本序列，并按 AGENTS.md 递增实际发布版本及缓存版本，同步所有文档与验收预期。若只是同一补丁重新应用，避免无理由重复递增。

### 10.2 可执行的 PowerShell 参考流程

下面假定已把 `shuran-1.5.25.patch` 放到下载目录。若使用完整交付包，解压后修改 `$releasePatchPath` 为里面的补丁路径。这组命令保留原工作区，创建独立发布目录；任何 Git 命令失败都会停止。

```powershell
$releasePatchPath = Join-Path $env:USERPROFILE 'Downloads\shuran-1.5.25.patch'
$releaseWorktreePath = 'D:\projects\shuran-method-cards-1.5.25'

function Invoke-ReleaseGit {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw 'Git 操作失败，请检查上方错误后再继续。' }
}

if (-not (Test-Path $releasePatchPath)) { throw '请下载补丁或修正 releasePatchPath。' }
Set-Location 'D:\projects\reading-feedback-app'
Invoke-ReleaseGit remote -v
Invoke-ReleaseGit branch --show-current
Invoke-ReleaseGit status --short
Invoke-ReleaseGit diff --stat
Invoke-ReleaseGit fetch origin
Invoke-ReleaseGit worktree add -b release/method-cards-1.5.25 $releaseWorktreePath origin/main
Set-Location $releaseWorktreePath
Invoke-ReleaseGit apply --check $releasePatchPath
Invoke-ReleaseGit apply --index $releasePatchPath
Invoke-ReleaseGit status --short
Invoke-ReleaseGit diff --cached --stat
Invoke-ReleaseGit -c core.whitespace=cr-at-eol diff --cached --check

# 在这里完成第 9 节的测试、浏览器验收与相关修复，再执行下方提交。
# --index 已暂存补丁文件；后续修复请只 git add 相关文件，先逐项审阅。
Invoke-ReleaseGit commit -m 'Launch method cards with usage feedback'
Invoke-ReleaseGit push origin HEAD:main
Invoke-ReleaseGit rev-parse HEAD
Invoke-ReleaseGit ls-remote origin refs/heads/main
```

提交与远端 main 哈希应一致。若同名 worktree/分支已经存在，先检查现状并复用干净目录或另取名，不能覆盖；若补丁已应用，不重复执行。推送出现远端新提交时，获取并合并或变基本轮未发布提交，重跑相关检查，禁止 `--force`。

需要 GitHub 登录时使用本地已有 Git/GitHub 正常认证流程，不把 token 写进补丁或终端输出。提交不使用 `--amend`、`--no-verify` 或 `--no-gpg-sign`。

若原 `D:\projects\reading-feedback-app` 工作区干净、当前 main 没有独有提交，在成功推送后可安全同步原目录：

```powershell
Set-Location 'D:\projects\reading-feedback-app'
Invoke-ReleaseGit status --short
# 仅在已确认工作区干净且适合快进时继续。
Invoke-ReleaseGit switch main
Invoke-ReleaseGit pull --ff-only origin main
```

如果原目录有用户尚未整合的修改，不替用户强行覆盖；本轮代码已在发布 worktree 中，应明确告知路径及原目录尚需合并的状态。

## 11. 服务器更新、验收与恢复

推送校验完成后，在本机登录：

```powershell
ssh ubuntu@43.161.238.165
```

服务器 Linux shell 中执行。先检查当前部署提交、工作区和 Compose 状态；发现服务器有未提交改动，应保留并处理差异后再更新。

```bash
sudo -i
set -e
cd /opt/shuran-app
git status --short
git rev-parse HEAD
cd deploy/aliyun
docker compose ps
```

记录旧提交以便恢复，保留现有 `.env`、uploads、backups、releases 和数据库卷。若生产使用仓库中的 PostgreSQL `db` 服务，可先做完整数据库备份；实际部署不同则使用该部署已有备份方式，不能对不匹配的服务盲目执行。

```bash
# 以下仅用于当前 Compose 中确有 PostgreSQL db 服务的部署。
mkdir -p /opt/shuran-release-backups
releaseBackupPath="/opt/shuran-release-backups/method-cards-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$releaseBackupPath"
test -s "$releaseBackupPath"
```

随后更新应用：

```bash
cd /opt/shuran-app
git pull --ff-only origin main
git rev-parse HEAD
cd deploy/aliyun
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/health
```

启动可能尚未完成，健康检查暂时失败时先查看容器状态与日志，等待启动后再检查。若版本未调整，成功响应必须包含 `status: healthy`、`version: 1.5.25`、`ui_version: 20261010methods1`。新版本序列已调整时，核对本轮实际约定的值。只看到旧版本返回 healthy，不能证明本次更新成功。

继续核对服务器 HEAD 与 GitHub main 一致，并检查应用日志、数据库四张新表及 `uq_method_pending_card` 索引。必要时查看：

```bash
cd /opt/shuran-app/deploy/aliyun
docker compose ps
docker compose logs --tail=100 app
```

在浏览器实际打开 `http://43.161.238.165:8000/#methods`，完成访客和账号核心流程，确认静态资源没有仍在使用旧缓存。确认站长有能力发邀请码、意见确实可读，才对外发布链接。技术验收使用的数据应在产品分析时标注，不能当作市场用户的认可。

若本轮变更导致无法服务，保留日志与旧提交信息，在本地对本轮提交创建普通 revert 提交、推送后再按上述流程更新；不要通过强制推送、`git reset --hard`、删表或 `docker compose down -v` 恢复。新表追加创建，回退应用时保留数据。涉及其他版本改动的恢复应先审阅具体差异，不机械回退所有后续提交。

## 12. 接手完成时的报告格式

本地 Codex 最后应清楚写出以下内容：

- 本地代码所在目录、当前分支、提交哈希，本轮主要改变了什么；原工作区是否已经同步。
- 自动检查和实际验收结果；既有 3 项失败及是否出现新失败；未完成项必须单独列出。
- GitHub 是否推送成功，以及 `origin/main` 的提交哈希。
- 香港服务器是否部署成功，服务器 HEAD、健康检查版本及核心流程的验收结果。
- 网页 / Android 源码版本和 versionCode；是否实际构建新 APK，实际下载元数据是否对应真实产物。
- 对外可访问的方法页地址，以及下一阶段依据真实使用继续修改的重点。

本地提交、远端推送、生产发布、APK 构建是四个独立状态。没有实际完成的步骤不能用“已经上线”概括。本轮不再要求用户找额外的人才能继续开发；本地 Codex 应把授权的合并、验证、推送和发布执行到完成，遇到真实阻塞则交付可继续执行的结果。
