# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "static" / "index.html"
text = p.read_text(encoding="utf-8")

# --- todos ---
todos_start = text.find('                            <div id="todayTodosList"')
todos_end = text.find(
    '\n                        </motion.div>\n                    </motion.div>\n                </motion.div>\n                \n                <!-- 第二行',
    todos_start,
)
if todos_start == -1:
    todos_end = text.find(
        '\n                        </div>\n                    </div>\n                </div>\n                \n                <!-- 第二行',
        todos_start,
    )

if todos_start != -1 and todos_end != -1:
  new_todos = (
      '                            <div id="todayTodosList" class="todos-list"></div>\n'
      '                            <div class="todo-add-row">\n'
      '                                <input type="text" id="newTodoInput" class="todo-add-input" placeholder="添加今日待办…" maxlength="500">\n'
      '                                <button type="button" class="todo-add-btn" onclick="addDailyTodo()">＋ 添加</button>\n'
      '                            </div>'
  )
  text = text[:todos_start] + new_todos + text[todos_end:]
  print("patched todos")
else:
  print("todos markers not found", todos_start, todos_end)

# --- overview ---
ov_start = text.find('                        <div class="overview-stats">')
ov_end = text.find('\n                    </div>\n                    \n                    <!-- 快速操作 -->', ov_start)
if ov_start != -1 and ov_end != -1:
  new_ov = (
      '                        <div class="overview-stats" id="todayOverviewStats">\n'
      '                            <div class="stat-item clickable" id="readingStatItem" onclick="toggleOverviewPanel(\'reading\')">\n'
      '                                <div class="stat-icon">📚</div>\n'
      '                                <div class="stat-content">\n'
      '                                    <div class="stat-value" id="todayReadingTime">--</div>\n'
      '                                    <div class="stat-label">今日阅读时长</div>\n'
      '                                    <div class="reading-duration-hint">滚轮可调时长 · 点击展开阅读内容与笔记</div>\n'
      '                                    <div class="stat-progress"><motion.div class="progress-bar" id="readingProgressBar" style="width: 0%;"></div></div>\n'
      '                                </div>\n'
      '                            </div>\n'
      '                            <div class="overview-panel hidden" id="readingPanel"></div>\n'
      '                            <motion.div class="stat-item clickable" id="actionsStatItem" onclick="toggleOverviewPanel(\'actions\')">\n'
      '                                <div class="stat-icon">✅</div>\n'
      '                                <div class="stat-content">\n'
      '                                    <div class="stat-value" id="completedActions">--</div>\n'
      '                                    <div class="stat-label">今日实践行动项</div>\n'
      '                                    <div class="stat-progress"><div class="progress-bar" id="actionsProgressBar" style="width: 0%;"></motion.div></div>\n'
      '                                </div>\n'
      '                            </div>\n'
      '                            <div class="overview-panel hidden" id="actionsPanel"></div>\n'
      '                            <div class="stat-item clickable" id="practiceStatItem" onclick="toggleOverviewPanel(\'practice\')">\n'
      '                                <div class="stat-icon">🎯</div>\n'
      '                                <div class="stat-content">\n'
      '                                    <div class="stat-value" id="practiceCount">--</div>\n'
      '                                    <div class="stat-label">今日实践记录</div>\n'
      '                                    <div class="stat-progress"><div class="progress-bar" id="practiceProgressBar" style="width: 0%;"></div></div>\n'
      '                                </div>\n'
      '                            </div>\n'
      '                            <div class="overview-panel hidden" id="practicePanel"></div>\n'
      '                        </div>\n'
      '                        <p id="todayOverviewHint" style="font-size:0.8rem;color:#a0aec0;margin-top:8px;">登录后自动加载今日数据</p>'
  )
  new_ov = new_ov.replace("<motion.div", "<div").replace("</motion.div>", "</div>")
  text = text[:ov_start] + new_ov + text[ov_end:]
  print("patched overview")
else:
  print("overview markers not found", ov_start, ov_end)

if "today-dashboard.js" not in text:
  text = text.replace("</body>", '    <script src="/static/js/today-dashboard.js"></script>\n</body>')
  print("added script")

p.write_text(text, encoding="utf-8")
print("finished")
