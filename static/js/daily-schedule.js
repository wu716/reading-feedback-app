/**
 * 日程安排：直接写任务，就近标记难度、记录用时；排序单独操作。
 */
(function () {
    let day = null;
    let loadSerial = 0;
    let data = { date: null, designed_at: null, tasks: [] };
    let mode = 'list';
    const expandedTasks = new Set();
    const timeDrafts = new Map();
    const splitDrafts = new Map();
    let sortReturnMode = 'list';
    let addingTask = false;
    let newTaskFamiliarity = null;
    let newTaskDifficulty = null;
    let newTaskImportance = null;
    let newTaskPriority = 0;
    let newTaskDuration = '';
    let newTaskColor = null;
    const taskColors = [['雾蓝','#7894a6'],['天青','#75a9bd'],['湖蓝','#4f89a0'],['墨蓝','#416580'],['薄荷绿','#79aa96'],['鼠尾草绿','#789879'],['森林绿','#527b65'],['柠檬黄','#d1bb64'],['暖琥珀','#c5954f'],['珊瑚橙','#d18b68'],['陶土红','#bb7166'],['莓果红','#a95f70'],['薰衣草紫','#a18ab7'],['柔紫','#927f9f'],['玫瑰粉','#d19aaa'],['石墨灰','#8b9295']];

    function safeColor(value) {
        return /^#[0-9a-f]{6}$/i.test(value || '') ? value.toLowerCase() : null;
    }

    function colorStyle(task) {
        const color = safeColor(task.color);
        return color ? ` style="--task-color:${color};--task-tint:${color}12" data-has-color` : '';
    }

    function renderColorPicker(value) {
        const color = safeColor(value);
        return `<details class="schedule-color"><summary>${color ? `<span class="schedule-color-dot" style="background:${color}"></span>` : ''}颜色${color ? '' : ' · 未标记'}</summary>
            <div class="schedule-color-panel"><p>常用颜色</p><div class="schedule-color-swatches">${taskColors.map(([name,hex]) => `<button type="button" class="schedule-color-swatch" style="background:${hex}" data-color-value="${hex}" aria-label="${name}" title="${name}" aria-pressed="${color === hex}">${color === hex ? '✓' : ''}</button>`).join('')}</div>
            <button type="button" data-color-clear>清除颜色</button><span class="schedule-color-status" role="status"></span></div></details>`;
    }
    let splitFor = null;
    let editingId = null;
    let dragTaskId = null;
    let dragPressTimer = null;
    let dragActive = false;
    let dragArmed = false;
    let suppressClickUntil = 0;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragPointerId = null;
    let dragScrollTimer = null;

    function t(key, fallback) {
        if (window.shuranI18n && typeof window.shuranI18n.t === 'function') {
            return window.shuranI18n.t(key, fallback);
        }
        return fallback;
    }

    function format(template, values) {
        return String(template).replace(/\{(\w+)\}/g, (match, key) => (
            Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
        ));
    }

    function withCount(template, count) {
        return format(template, { count });
    }

    function todayISO() {
        const now = new Date();
        const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 10);
    }

    function shiftDay(iso, delta) {
        const d = new Date(iso + 'T00:00:00');
        d.setDate(d.getDate() + delta);
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 10);
    }

    function escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function flatten(tasks, acc) {
        (tasks || []).forEach((task) => {
            acc.push(task);
            flatten(task.children || [], acc);
        });
        return acc;
    }

    function executionLeaves(tasks, parents, acc) {
        const path = parents || [];
        const output = acc || [];
        (tasks || []).forEach((task) => {
            const children = task.children || [];
            if (children.length) {
                executionLeaves(children, path.concat(task.text || ''), output);
                return;
            }
            output.push(Object.assign({}, task, {
                parent_path: path.filter(Boolean),
            }));
        });
        return output.sort((a, b) => (
            (a.flow_order ?? a.sort_order ?? 0) - (b.flow_order ?? b.sort_order ?? 0)
            || a.id - b.id
        ));
    }

    function priorityLabel(value) {
        if (Number(value) >= 2) return t('schedule.priority.high', '最高');
        if (Number(value) === 1) return t('schedule.priority.important', '重要');
        return t('schedule.priority.normal', '普通');
    }

    function familiarityLabel(value) {
        if (value === 'familiar') return t('schedule.familiar', '熟悉');
        if (value === 'unfamiliar') return t('schedule.unfamiliar', '陌生');
        return '';
    }

    function minutesLabel(mins) {
        if (mins == null) return '';
        const m = parseInt(mins, 10);
        if (!m) return t('schedule.unestimated', '未估时');
        if (m < 60) return withCount(t('schedule.minutes', '{count} 分钟'), m);
        const h = Math.floor(m / 60);
        const r = m % 60;
        return r
            ? format(t('schedule.hoursMinutes', '{hours} 小时 {minutes} 分'), { hours: h, minutes: r })
            : withCount(t('schedule.hours', '{count} 小时'), h);
    }

    function durationInputValue(mins) {
        if (mins == null) return '';
        return minutesLabel(mins);
    }

    function parseDuration(value, limit = 1440) {
        const raw = String(value || '').trim().toLowerCase();
        if (!raw) return null;
        if (/^\d+(?:\.\d+)?$/.test(raw)) return Math.min(limit, Number(raw));
        if (!/^(?:(?:\d+(?:\.\d+)?)\s*(?:小时|小時|hrs?|h)\s*)?(?:(?:\d+(?:\.\d+)?)\s*(?:分钟|分鐘|mins?|分|m)\s*)?$/.test(raw)) return NaN;
        const hours = raw.match(/(\d+(?:\.\d+)?)\s*(?:小时|小時|h|hr|hrs)/);
        const minutes = raw.match(/(\d+(?:\.\d+)?)\s*(?:分钟|分鐘|分|min|mins|m)/);
        const h = hours ? Number(hours[1]) * 60 : 0;
        const m = minutes ? Number(minutes[1]) : 0;
        if (!hours && !minutes) return NaN;
        return Math.min(limit, h + m);
    }

    async function api(path, options) {
        if (typeof apiRequest !== 'function') throw new Error(t('schedule.signInRequired', '请先登录'));
        return apiRequest(`/api/schedule${path}`, options || {});
    }

    function currentDay() {
        return day || todayISO();
    }

    function dayLabel(iso) {
        const today = todayISO();
        if (iso === today) return t('schedule.today', '今天');
        const parts = String(iso).split('-');
        if (parts.length < 3) return iso;
        return format(t('schedule.monthDay', '{month}月{day}日'), {
            month: Number(parts[1]),
            day: Number(parts[2]),
        });
    }

    function setHint() {
        const hint = document.getElementById('scheduleHint');
        if (!hint) return;
        if (mode === 'sort') {
            hint.textContent = t('schedule.hint.sort', '这里只调整顺序和并行关系');
            return;
        }
        if (mode === 'flow' && data.designed_at) {
            hint.textContent = allDone()
                ? t('schedule.hint.done', '今日已完成')
                : t('schedule.hint.flow', '点任务内容即可修改，难度与用时直接记在任务下面');
            return;
        }
        hint.textContent = allDone()
            ? t('schedule.hint.done', '今日已完成')
            : t('schedule.hint.list', '写下要做的事，按回车添加');
    }

    function allDone() {
        const tasks = executionLeaves(data.tasks || []);
        return tasks.length > 0 && tasks.every((task) => task.completed);
    }

    function renderDoneBtn(task) {
        if (task.project_task_id && task.project_id && !task.project_day_plan) {
            return `<a class="flow-project-finish" href="/static/projects.html?task=${task.project_task_id}&finish=1#taskDetail">${task.completed ? '已验收' : '验收'}</a>`;
        }
        const doneLabel = escapeHtml(task.project_day_plan ? '今日完成' : t('schedule.done', '完成'));
        if (task.completed) {
            const undoLabel = escapeHtml(task.project_day_plan ? '取消今日完成' : t('schedule.undoDone', '取消完成'));
            return `<button type="button" class="flow-done-btn is-on" data-act="toggle" aria-pressed="true" aria-label="${undoLabel}">${undoLabel}</button>`;
        }
        return `<button type="button" class="flow-done-btn" data-act="toggle" aria-pressed="false" aria-label="${doneLabel}">${doneLabel}</button>`;
    }

    function renderNote(task) {
        const label = escapeHtml(t('schedule.note', '执行反馈'));
        return `<div class="flow-feedback"><label class="flow-feedback-label">${label}<input type="text" class="flow-note" maxlength="500" placeholder="记一句实际进展（选填）" value="${escapeHtml(task.note || '')}" data-act="note" aria-label="${label}"></label></div>`;
    }

    function renderTaskLinks(task) {
        if ((task.children || []).length) return '';
        const date = encodeURIComponent(currentDay());
        const project = task.project_id ? `<a href="/static/projects.html?task=${task.project_task_id}#taskDetail">${escapeHtml(task.project_title || '所属项目')}</a>` : `<a href="/static/projects.html?daily=${task.id}&date=${date}">纳入项目</a>`;
        return `<div class="flow-detail-group"><h3>归属与开始</h3><div class="flow-project-links">${project}<button type="button" data-act="conditions">开始条件与约束</button><button type="button" data-act="reminder">${task.remind_time ? '提醒 ' + escapeHtml(task.remind_time) : '设置提醒'}</button>${task.priority ? `<span>旧优先级：${escapeHtml(priorityLabel(task.priority))}</span>` : ''}</div></div>`;
    }

    function renderTaskLaunch(task) {
        const execute = task.completed || task.children?.length ? '' : task.readiness?.can_start === false ? `<span class="schedule-blocked">${escapeHtml(task.readiness.summary || '条件待核对')}</span>` : `<a class="schedule-execute-link" href="/static/projects.html?view=execution&date=${encodeURIComponent(currentDay())}&execute=daily:${task.id}">加入执行</a>`;
        return `<div class="flow-task-launch">${execute}<button type="button" data-act="split" aria-expanded="${splitFor === task.id}">${splitFor === task.id ? '收起拆分' : '拆开'}</button><button type="button" data-act="expand" aria-expanded="${expandedTasks.has(task.id)}" aria-controls="scheduleDetail-${task.id}">${expandedTasks.has(task.id) ? '收起更多' : '更多'}</button>${renderDoneBtn(task)}</div>`;
    }

    function renderMethod(task) {
        if (task.project_task_id) return ''; // The linked project owns its steps and checks.
        if (!(task.steps?.length || task.checklist?.length || task.acceptance_criteria || task.common_problems)) return '';
        return `<details class="flow-method"><summary>步骤与完成检查</summary>${task.steps?.length ? `<ol>${task.steps.map(text=>`<li>${escapeHtml(text)}</li>`).join('')}</ol>` : ''}${(task.checklist || []).map((item,index)=>`<label><input type="checkbox" data-act="method-check" data-check-index="${index}" ${item.done ? 'checked' : ''}>${item.group==='preparation'?'准备核对：':'交付核对：'}${escapeHtml(item.text)}${item.not_applicable?'（不适用：'+escapeHtml(item.not_applicable)+'）':''}</label>`).join('')}${task.common_problems ? `<p>常见难点：${escapeHtml(task.common_problems)}</p>` : ''}${task.acceptance_criteria ? `<p>验收标准：${escapeHtml(task.acceptance_criteria)}</p>` : ''}</details>`;
    }

    function renderToolbar() {
        const label = document.getElementById('scheduleDateLabel');
        if (label) label.textContent = dayLabel(currentDay());
        const dateInput = document.getElementById('scheduleDateInput');
        if (dateInput) dateInput.value = currentDay();
        const sortBtn = document.getElementById('scheduleSortBtn');
        const flowBtn = document.getElementById('scheduleFlowBtn');
        const addRow = document.getElementById('scheduleAddRow');
        if (sortBtn) {
            sortBtn.textContent = mode === 'sort'
                ? t('schedule.finishDesign', '完成设计')
                : t('schedule.designFlow', '设计流程');
            sortBtn.setAttribute('aria-pressed', String(mode === 'sort'));
        }
        if (flowBtn) flowBtn.textContent = mode === 'flow' ? '回到清单' : '查看流程';
        if (addRow) addRow.hidden = false;
        updateAddComposer();
    }

    function updateAddComposer() {
        const addRow = document.getElementById('scheduleAddRow');
        if (!addRow) return;
        let colorEntry = document.getElementById('scheduleNewColor');
        if (!colorEntry) {
            colorEntry = document.createElement('div');
            colorEntry.id = 'scheduleNewColor';
            addRow.appendChild(colorEntry);
        }
        colorEntry.innerHTML = renderColorPicker(newTaskColor);
        addRow.querySelectorAll('[data-new-act="fam"]').forEach((button) => {
            const active = button.dataset.value === newTaskFamiliarity;
            button.classList.toggle('active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        addRow.querySelectorAll('[data-new-act="priority"]').forEach((button) => {
            const active = Number(button.dataset.value) === newTaskPriority;
            button.classList.toggle('active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        for (const [act, value] of [['difficulty', newTaskDifficulty], ['importance', newTaskImportance]]) {
            addRow.querySelectorAll(`[data-new-act="${act}"]`).forEach(button => {
                const active = button.dataset.value === value;
                button.classList.toggle('active', active);
                button.setAttribute('aria-pressed', String(active));
            });
        }
    }

    function renderTitle(task) {
        if (editingId === task.id) {
            return `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(task.text)}" data-act="text" aria-label="${escapeHtml(t('schedule.editStepAria', '修改这一步'))}">`;
        }
        return `<button type="button" class="flow-task-text" data-act="edit" aria-label="编辑任务：${escapeHtml(task.text)}">${escapeHtml(task.text)}</button>`;
    }

    function renderDeleteBtn(task) {
        const label = escapeHtml(task?.project_day_plan ? '移出这一天' : t('schedule.delete', '删除'));
        return `<button type="button" class="flow-mini-btn flow-danger" data-act="delete" aria-label="${label}">${label}</button>`;
    }

    function renderSplitRow(task) {
        if (splitFor !== task.id) return '';
        return `
            <div class="flow-split-row" role="group" aria-label="拆成下一步">
                <input type="text" maxlength="500" placeholder="${escapeHtml(t('schedule.split.placeholder', '写下更具体的一步'))}" value="${escapeHtml(splitDrafts.get(`${currentDay()}:${task.id}`) || '')}" aria-label="更具体的一步" data-split-input>
                <button type="button" class="flow-ghost-btn" data-act="split-save">${escapeHtml(t('schedule.split.add', '加入'))}</button>
            </div>`;
    }

    function renderEditActions(showSplit, task) {
        return `
            <div class="flow-task-actions">
                ${showSplit ? `<button type="button" data-act="split">${escapeHtml(t('schedule.split', '拆开'))}</button>` : ''}
                ${renderDeleteBtn(task)}
            </div>`;
    }

    function renderQuickAttributes(task) {
        const difficulty = task.practice?.difficulty;
        return `
            <div class="flow-task-attributes">
                <div class="flow-attribute-group" role="group" aria-labelledby="taskFamiliarityLabel-${task.id}">
                    <span class="flow-attribute-label" id="taskFamiliarityLabel-${task.id}">${escapeHtml(t('schedule.familiarityLabel', '熟悉度'))}</span>
                    <div class="flow-attribute-options">
                        <button type="button" class="flow-chip${task.familiarity === 'familiar' ? ' active' : ''}" data-act="fam" data-value="familiar" aria-pressed="${task.familiarity === 'familiar'}">${escapeHtml(t('schedule.familiar', '熟悉'))}</button>
                        <button type="button" class="flow-chip${task.familiarity === 'unfamiliar' ? ' active' : ''}" data-act="fam" data-value="unfamiliar" aria-pressed="${task.familiarity === 'unfamiliar'}">${escapeHtml(t('schedule.unfamiliar', '陌生'))}</button>
                    </div>
                </div>
                <div class="flow-attribute-group" role="group" aria-labelledby="taskDifficultyLabel-${task.id}">
                    <span class="flow-attribute-label" id="taskDifficultyLabel-${task.id}">${escapeHtml(t('schedule.difficultyLabel', '难度'))}</span>
                    <div class="flow-attribute-options">
                        <button type="button" class="flow-chip${difficulty === 'simple' ? ' active' : ''}" data-act="difficulty" data-value="simple" aria-pressed="${difficulty === 'simple'}">${escapeHtml(t('schedule.difficulty.simple', '简单'))}</button>
                        <button type="button" class="flow-chip${difficulty === 'difficult' ? ' active' : ''}" data-act="difficulty" data-value="difficult" aria-pressed="${difficulty === 'difficult'}">${escapeHtml(t('schedule.difficulty.difficult', '困难'))}</button>
                    </div>
                </div>
                ${task.practice?.importance ? `<div class="flow-attribute-group flow-attribute-readonly" role="group" aria-labelledby="taskImportanceLabel-${task.id}"><span class="flow-attribute-label" id="taskImportanceLabel-${task.id}">${escapeHtml(t('schedule.importanceLabel', '重要性'))}</span><span class="flow-importance-value">${escapeHtml(t('schedule.importance.' + task.practice.importance, ({unimportant:'不重要',ordinary:'一般',important:'重要'})[task.practice.importance]))}</span></div>` : ''}
            </div>`;
    }

    function renderTimeFeedback(task) {
        if (task.children?.length) return '';
        const p = task.practice || {}, feedback = p.feedback;
        const actual = feedback?.actual_minutes;
        const difference = feedback?.difference;
        const future = currentDay() > todayISO();
        const draft = timeDrafts.get(`${currentDay()}:${task.id}`);
        let comparison = difference == null ? '' : difference === 0 ? '与最初预计一致' : `${difference > 0 ? '比最初预计多' : '比最初预计少'} ${Math.abs(difference)} 分钟`;
        if (p.original_estimate != null && p.original_estimate !== task.estimated_minutes) {
            comparison = `最初预计 ${p.original_estimate} 分${comparison ? ' · ' + comparison : ''}`;
        }
        return `<form class="flow-time-feedback" data-time-form>
            <label>预计 <input type="text" name="estimate" class="flow-minutes" maxlength="20" placeholder="如 30分钟" value="${escapeHtml(draft?.estimate ?? (task.estimated_minutes == null ? '' : task.estimated_minutes + '分钟'))}" aria-label="预计用时"></label>
            <label>实际 <input type="text" name="actual" class="flow-minutes" maxlength="24" placeholder="${future ? '当天再记' : '用后填写'}" value="${escapeHtml(draft?.actual ?? (actual == null ? '' : actual + '分钟'))}" aria-label="实际用时" ${future ? 'disabled' : ''}></label>
            <button type="submit" class="flow-mini-btn">保存用时</button>
            <span class="flow-time-comparison">${escapeHtml(comparison)}${p.recorded_minutes ? `${comparison ? ' · ' : ''}计时记录 ${p.recorded_minutes} 分` : ''}</span>
            <span class="flow-time-status" role="status"></span>
        </form>`;
    }

    function timeFeedbackBody(prior, actual, result, basis = 'self_report') {
        const body = {actual_minutes:actual, result, basis};
        ['reason','next_estimate','outcome','scope_changed','checklist_exception','feedback_date'].forEach(key => {
            if (prior?.[key] != null) body[key] = prior[key];
        });
        return body;
    }

    async function saveTimeFeedback(id, form) {
        const savedDay = currentDay();
        const task = flatten(data.tasks || [], []).find(item => item.id === id);
        const estimateText = form.elements.estimate.value.trim();
        const actualText = form.elements.actual.value.trim();
        const estimate = estimateText ? parseDuration(estimateText) : null;
        const actual = actualText ? parseDuration(actualText, 1000000) : null;
        if ((estimateText && (!Number.isInteger(estimate) || estimate < 0)) || (actualText && !Number.isFinite(actual))) {
            throw new Error('请填写分钟数，或如 1小时30分；预计用时请用整数分钟');
        }
        const path = `/api/projects/practice/tasks/daily/${id}`;
        const latest = await apiRequest(path);
        const prior = latest.feedback;
        if (actual == null && prior?.actual_minutes != null) {
            throw new Error('已有实际用时会保留；需要更正时请直接填写新的总用时');
        }
        if (estimate !== (task.estimated_minutes ?? null)) {
            // Do not replace the form during a save: both fields belong to this action.
            await api(`/tasks/${id}`, {method:'PATCH', body:JSON.stringify(estimate == null ? {clear_estimate:true} : {estimated_minutes:estimate})});
        }
        const result = latest.completed ? 'completed' : prior?.result === 'rework' ? 'rework' : 'partial';
        if (actual != null && (actual !== prior?.actual_minutes || prior?.basis === 'pending' || result !== prior?.result)) {
            await apiRequest(path + '/feedback', {method:'POST', body:JSON.stringify(timeFeedbackBody(prior, actual, result))});
        }
        timeDrafts.delete(`${savedDay}:${id}`);
        if (currentDay() !== savedDay) return;
        await load(savedDay);
        const status = document.querySelector(`[data-task-id="${id}"] .flow-time-status`);
        if (status) status.textContent = '已保存';
    }

    function renderTask(task, isChild) {
        const plan = task.project_day_plan;
        const source = plan ? `<div class="schedule-project-source">${escapeHtml(plan.project_title)} › ${escapeHtml(plan.stage_title)} › ${plan.source_missing ? `${escapeHtml(plan.task_title)} · 来源已移除，历史安排保留` : `<a href="/static/projects.html?task=${task.project_task_id}#taskDetail">${escapeHtml(plan.task_title)}</a> · ${plan.source_completed ? '项目任务已验收' : '修改或验收项目任务'}`}</div>` : '';
        const recorded = plan ? `<p class="schedule-project-time">今日已记录 ${task.actual_minutes} 分 · 项目累计已记录 ${plan.project_actual_minutes} 分${plan.source_estimated_minutes != null ? ' · 调入时整项预计 ' + plan.source_estimated_minutes + ' 分' : ''}（未记录不代表未投入）</p>` : '';
        return `
            <article class="flow-task${isChild ? ' is-child' : ''}${task.completed ? ' is-done' : ''}" data-task-id="${task.id}"${colorStyle(task)}>
                ${source}
                <div class="flow-task-summary">
                <div class="flow-task-main">
                    ${renderTitle(task)}
                </div>
                ${renderColorPicker(task.color)}
                </div>
                ${renderQuickAttributes(task)}
                ${renderTimeFeedback(task)}
                ${recorded}
                ${renderTaskLaunch(task)}
                ${renderSplitRow(task)}
                <div class="flow-task-detail" id="scheduleDetail-${task.id}" ${expandedTasks.has(task.id) ? '' : 'hidden'}>
                <div class="flow-detail-group"><h3>准备与回顾</h3><div class="flow-detail-actions"><button type="button" data-act="practice-attributes">目标重要性</button><button type="button" data-act="practice">估时与预演</button><button type="button" data-act="feedback">完整反馈与历史</button></div></div>
                ${renderTaskLinks(task)}
                ${renderMethod(task)}
                ${renderNote(task)}
                ${renderEditActions(false, task)}
                </div>
            </article>
            ${(task.children || []).map((child) => renderTask(child, true)).join('')}
        `;
    }

    function renderSortPlan(tasks) {
        return tasks.map((task, index) => {
            const prev = index > 0 ? tasks[index - 1] : null;
            const parallelOn = !!(prev && task.parallel_group && task.parallel_group === prev.parallel_group);
            const path = task.parent_path && task.parent_path.length
                ? `<div class="flow-parent-path">${escapeHtml(task.parent_path.join(' / '))}</div>`
                : '';
            return `
                <article class="flow-task flow-sortable${task.completed ? ' is-done' : ''}" data-task-id="${task.id}"${colorStyle(task)}>
                    <div class="flow-sort-row">
                        <button type="button" class="flow-sort-handle" data-sort-handle aria-label="${escapeHtml(t('schedule.dragToSort', '拖动调整顺序'))}" title="${escapeHtml(t('schedule.dragToSort', '拖动调整顺序'))}">⋮⋮</button>
                        <div class="flow-sort-index">${index + 1}</div>
                        <div class="flow-sort-copy">
                            <div class="flow-task-main"><div class="flow-task-text flow-task-text-static">${escapeHtml(task.text)}</div></div>
                            ${path}
                        </div>
                    </div>
                    <div class="flow-task-meta flow-sort-controls">
                        ${index > 0 ? `<button type="button" class="flow-mini-btn" data-act="up">${escapeHtml(t('schedule.moveUp', '上移'))}</button>` : ''}
                        ${index < tasks.length - 1 ? `<button type="button" class="flow-mini-btn" data-act="down">${escapeHtml(t('schedule.moveDown', '下移'))}</button>` : ''}
                        ${index > 0 ? `<button type="button" class="flow-chip${parallelOn ? ' active' : ''}" data-act="parallel">${escapeHtml(t('schedule.parallelPrevious', '与上一项并行'))}</button>` : ''}
                    </div>
                </article>`;
        }).join('');
    }

    function groupSiblings(tasks) {
        const groups = [];
        (tasks || []).forEach((task) => {
            const last = groups[groups.length - 1];
            if (
                last
                && last.parallel
                && task.parallel_group
                && last.group === task.parallel_group
            ) {
                last.items.push(task);
                return;
            }
            groups.push({
                parallel: !!task.parallel_group,
                group: task.parallel_group,
                items: [task],
            });
        });
        groups.forEach((group) => {
            if (group.items.length === 1) group.parallel = false;
        });
        return groups;
    }

    function renderFlowNode(task) {
        return renderTask(task, false);
    }

    function renderFlowGroups(tasks) {
        return groupSiblings(tasks).map((group, i) => {
            const inner = group.items.map(renderFlowNode).join('');
            if (group.parallel) {
                return `
                    <div class="flow-lane">
                        <div class="flow-step-label">${escapeHtml(t('schedule.flow.parallel', '并行'))}</div>
                        <div class="flow-parallel${group.items.length > 1 ? ' has-many' : ''}">${inner}</div>
                    </div>`;
            }
            return `
                <div class="flow-lane">
                    <div class="flow-step-label">${escapeHtml(withCount(t('schedule.flow.step', '第 {count} 步'), i + 1))}</div>
                    ${inner}
                </div>`;
        }).join('');
    }

    function focusEditor() {
        const list = document.getElementById('scheduleList');
        if (!list) return;
        const editInput = editingId
            ? list.querySelector(`[data-task-id="${editingId}"] [data-act="text"]`)
            : null;
        if (editInput) {
            editInput.focus();
            editInput.select();
            return;
        }
    }

    function render() {
        const list = document.getElementById('scheduleList');
        if (!list) return;
        const active = document.activeElement;
        const activeTask = active?.closest?.('[data-task-id]')?.dataset.taskId;
        const activeName = active?.closest?.('[data-time-form]') ? active.name : null;
        const selection = activeName ? [active.selectionStart, active.selectionEnd] : null;
        renderToolbar();
        let projectEntry = document.getElementById('scheduleProjectEntry');
        if (!projectEntry) {
            projectEntry = document.createElement('button'); projectEntry.type = 'button'; projectEntry.id = 'scheduleProjectEntry';
            projectEntry.className = 'schedule-project-entry'; projectEntry.textContent = '从项目安排';
            projectEntry.setAttribute('aria-expanded', 'false'); projectEntry.setAttribute('aria-controls', 'scheduleStagePanel');
            projectEntry.addEventListener('click', () => window.ShuranScheduleProjects?.toggle());
            document.querySelector('.schedule-date-actions').appendChild(projectEntry);
        }
        window.ShuranScheduleProjects?.sync(currentDay(), data.tasks, mode);
        setHint();
        if (!(data.tasks || []).length) {
            list.innerHTML = `<p class="flow-empty">${escapeHtml(t('schedule.emptyTasks', '还没有行动'))}</p>`;
            return;
        }
        if (mode === 'sort') {
            list.innerHTML = renderSortPlan(executionLeaves(data.tasks));
        } else if (mode === 'flow') {
            list.innerHTML = renderFlowGroups(executionLeaves(data.tasks));
        } else {
            list.innerHTML = data.tasks.map((task) => renderTask(task, false)).join('');
        }
        focusEditor();
        if (activeName && activeTask) {
            const input = list.querySelector(`[data-task-id="${activeTask}"] [name="${activeName}"]`);
            input?.focus({preventScroll:true});
            if (input && selection) input.setSelectionRange(...selection);
        }
    }

    async function load(nextDay) {
        const serial = ++loadSerial;
        const token = localStorage.getItem('authToken');
        if (!token) {
            data = { date: currentDay(), designed_at: null, tasks: [] };
            render();
            return;
        }
        day = nextDay || currentDay();
        window.ShuranScheduleProjects?.sync(day, data.tasks, mode);
        editingId = null;
        const result = await api(`?task_date=${encodeURIComponent(day)}`);
        if (serial !== loadSerial || token !== localStorage.getItem('authToken')) return;
        data = result;
        render();
    }

    async function addTask(text, parentId, openDesign, attributes) {
        const value = (text || '').trim();
        if (!value) return;
        const taskDay = currentDay();
        data = await api('/tasks', {
            method: 'POST',
            body: JSON.stringify({
                text: value,
                color: attributes?.color || null,
                task_date: taskDay,
                parent_id: parentId || null,
                familiarity: attributes?.familiarity || null,
                difficulty: attributes?.difficulty || null,
                importance: attributes?.importance || null,
                priority: Number.isInteger(attributes?.priority) ? attributes.priority : 0,
                estimated_minutes: Number.isInteger(attributes?.estimatedMinutes) ? attributes.estimatedMinutes : null,
            }),
        });
        if (parentId) splitDrafts.delete(`${taskDay}:${parentId}`);
        splitFor = null;
        if (openDesign) {
            const tasks = flatten(data.tasks || [], []);
            const newest = tasks.reduce((latest, task) => (!latest || task.id > latest.id ? task : latest), null);
            mode = 'list';
            editingId = newest ? newest.id : null;
        }
        render();
    }

    async function patchTask(id, body) {
        data = await api(`/tasks/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
        });
        render();
        if ('remind_time' in body || body.completed != null) window.reminderNotificationService?.syncNativeTodos();
        if (body.completed != null && typeof window.loadHabitFocus === 'function') {
            window.loadHabitFocus();
        }
    }

    async function saveText(id, value) {
        const task = flatten(data.tasks || [], []).find((item) => item.id === id);
        const next = (value || '').trim();
        const prev = task ? String(task.text || '').trim() : '';
        if (editingId === id) editingId = null;
        if (!task || !next || next === prev) {
            render();
            return;
        }
        await patchTask(id, { text: next });
    }

    async function beginEdit(id) {
        if (editingId === id) return;
        if (editingId) {
            const input = document.querySelector(`#scheduleList [data-task-id="${editingId}"] [data-act="text"]`);
            if (input) await saveText(editingId, input.value);
        }
        splitFor = null;
        editingId = id;
        render();
    }

    function openDesign(id) {
        mode = 'design';
        splitFor = null;
        editingId = id;
        render();
    }

    async function saveNote(id, value) {
        const task = flatten(data.tasks || [], []).find((item) => item.id === id);
        const next = (value || '').trim();
        const prev = (task && task.note ? String(task.note) : '').trim();
        if (next === prev) return;
        if (!next) {
            await patchTask(id, { clear_note: true });
            return;
        }
        await patchTask(id, { note: next });
    }

    function siblingsOf(taskId) {
        const walk = (nodes) => {
            for (let i = 0; i < nodes.length; i += 1) {
                if (nodes[i].id === taskId) return { list: nodes, index: i };
                const found = walk(nodes[i].children || []);
                if (found) return found;
            }
            return null;
        };
        return walk(data.tasks || []);
    }

    function nextParallelGroup() {
        const all = flatten(data.tasks || [], []);
        const used = all.map((t) => t.parallel_group).filter((v) => v != null);
        return (used.length ? Math.max.apply(null, used) : 0) + 1;
    }

    async function moveTask(taskId, dir) {
        if (mode === 'sort' || mode === 'design') {
            const leaves = executionLeaves(data.tasks || []);
            const index = leaves.findIndex((item) => item.id === taskId);
            const swap = index + dir;
            if (index < 0 || swap < 0 || swap >= leaves.length) return;
            const ordered = leaves.slice();
            [ordered[index], ordered[swap]] = [ordered[swap], ordered[index]];
            await reorderExecution(ordered);
            return;
        }
        const found = siblingsOf(taskId);
        if (!found) return;
        const swap = found.index + dir;
        if (swap < 0 || swap >= found.list.length) return;
        const a = found.list[found.index];
        const b = found.list[swap];
        await api('/reorder', {
            method: 'POST',
            body: JSON.stringify({
                task_date: currentDay(),
                items: [
                    { id: a.id, sort_order: b.sort_order, parallel_group: a.parallel_group, parent_id: a.parent_id },
                    { id: b.id, sort_order: a.sort_order, parallel_group: b.parallel_group, parent_id: b.parent_id },
                ],
            }),
        });
        await load(currentDay());
    }

    async function reorderExecution(tasks) {
        await api('/reorder', {
            method: 'POST',
            body: JSON.stringify({
                task_date: currentDay(),
                items: tasks.map((task, index) => ({
                    id: task.id,
                    sort_order: index,
                    flow_order: index,
                    parallel_group: task.parallel_group,
                    priority: task.priority ?? 0,
                })),
            }),
        });
        await load(currentDay());
    }

    async function toggleParallel(taskId) {
        const list = mode === 'sort' ? executionLeaves(data.tasks || []) : null;
        const found = list
            ? { list, index: list.findIndex((item) => item.id === taskId) }
            : siblingsOf(taskId);
        if (!found || found.index <= 0) return;
        const current = found.list[found.index];
        const prev = found.list[found.index - 1];
        const on = !!(current.parallel_group && prev.parallel_group && current.parallel_group === prev.parallel_group);
        if (on) {
            await patchTask(current.id, { clear_parallel: true });
            return;
        }
        const group = prev.parallel_group || nextParallelGroup();
        if (!prev.parallel_group) {
            await api(`/tasks/${prev.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ parallel_group: group }),
            });
        }
        await patchTask(current.id, { parallel_group: group });
    }

    async function moveToTop(taskId) {
        const leaves = executionLeaves(data.tasks || []);
        const selected = leaves.find((item) => item.id === taskId);
        if (!selected || leaves[0]?.id === taskId) return;
        await reorderExecution([selected].concat(leaves.filter((item) => item.id !== taskId)));
    }

    function clearDragPress() {
        if (dragPressTimer) {
            clearTimeout(dragPressTimer);
            dragPressTimer = null;
        }
    }

    function clearDragClasses() {
        document.querySelectorAll('#scheduleList .is-dragging, #scheduleList [data-sort-handle].is-drop-target')
            .forEach((item) => item.classList.remove('is-dragging', 'is-drop-target'));
    }

    function stopDragAutoScroll() {
        if (dragScrollTimer) {
            clearInterval(dragScrollTimer);
            dragScrollTimer = null;
        }
    }

    function updateDragAutoScroll(clientY) {
        const edge = 90;
        let delta = 0;
        if (clientY < edge) delta = -14;
        if (clientY > window.innerHeight - edge) delta = 14;
        if (!delta) {
            stopDragAutoScroll();
            return;
        }
        if (dragScrollTimer) return;
        dragScrollTimer = setInterval(() => window.scrollBy(0, delta), 30);
    }

    function dragTargetAt(x, y) {
        const element = document.elementFromPoint(x, y);
        return element?.closest('#scheduleList [data-task-id]') || null;
    }

    function markDragTarget(article) {
        document.querySelectorAll('#scheduleList [data-sort-handle].is-drop-target')
            .forEach((item) => item.classList.remove('is-drop-target'));
        if (article && parseInt(article.dataset.taskId, 10) !== dragTaskId) {
            article.querySelector('[data-sort-handle]')?.classList.add('is-drop-target');
        }
    }

    async function finishDrag(targetId) {
        const sourceId = dragTaskId;
        if (!dragActive || sourceId == null) return;
        dragActive = false;
        suppressClickUntil = Date.now() + 500;
        stopDragAutoScroll();
        clearDragClasses();
        dragTaskId = null;
        dragPointerId = null;
        if (targetId == null || sourceId === targetId) return;
        const leaves = executionLeaves(data.tasks || []);
        const from = leaves.findIndex((item) => item.id === sourceId);
        const to = leaves.findIndex((item) => item.id === targetId);
        if (from < 0 || to < 0) return;
        const ordered = leaves.slice();
        const [moved] = ordered.splice(from, 1);
        ordered.splice(to, 0, moved);
        await reorderExecution(ordered);
    }

    function bindDragSorting(list) {
        list?.addEventListener('pointerdown', (e) => {
            if (mode !== 'sort' && mode !== 'design') return;
            dragArmed = false;
            if (!e.target.closest('[data-sort-handle]')) return;
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
            dragArmed = true;
            clearDragPress();
            dragStartX = e.clientX;
            dragStartY = e.clientY;
            dragPointerId = e.pointerId;
            const id = parseInt(article.dataset.taskId, 10);
            if (e.pointerType !== 'mouse') {
                dragPressTimer = setTimeout(() => startPointerDrag(article, id, e.pointerId), 450);
            }
        });

        list?.addEventListener('pointermove', (e) => {
            if (!dragActive) {
                if (!dragArmed || dragPointerId !== e.pointerId) return;
                const moved = Math.hypot(e.clientX - dragStartX, e.clientY - dragStartY);
                if (dragPressTimer && moved > 8) clearDragPress();
                if (e.pointerType === 'mouse' && moved > 6) {
                    const article = e.target.closest('[data-task-id]');
                    if (article) startPointerDrag(article, parseInt(article.dataset.taskId, 10), e.pointerId);
                }
                return;
            }
            e.preventDefault();
            markDragTarget(dragTargetAt(e.clientX, e.clientY));
        });

        list?.addEventListener('pointerup', async (e) => {
            clearDragPress();
            dragArmed = false;
            if (!dragActive) return;
            try {
                const target = dragTargetAt(e.clientX, e.clientY);
                await finishDrag(target ? parseInt(target.dataset.taskId, 10) : null);
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
        });
        list?.addEventListener('pointercancel', () => {
            clearDragPress();
            dragArmed = false;
            dragActive = false;
            dragTaskId = null;
            dragPointerId = null;
            stopDragAutoScroll();
            clearDragClasses();
        });
    }

    function startPointerDrag(article, id, pointerId) {
        if (dragActive) return;
        clearDragPress();
        dragTaskId = id;
        dragPointerId = pointerId;
        dragActive = true;
        article.classList.add('is-dragging');
        try { article.setPointerCapture(pointerId); } catch (err) { /* ignore */ }
    }

    function actionFromEvent(e) {
        const actEl = e.target.closest('[data-act]');
        const article = e.target.closest('[data-task-id]');
        const act = actEl ? actEl.dataset.act : '';
        if (!article || !act) return null;
        return {
            article,
            act,
            actEl,
            id: parseInt(article.dataset.taskId, 10),
        };
    }

    window.loadDailySchedule = function loadDailySchedule() {
        return load(currentDay()).catch((e) => {
            const hint = document.getElementById('scheduleHint');
            if (hint) hint.textContent = e.message || t('schedule.loadFailed', '加载失败');
        });
    };
    window.getScheduleDay = currentDay;

    function onReady() {
        const root = document.getElementById('homeSchedule') || document.getElementById('schedule');
        if (!root || root.dataset.bound) return;
        root.dataset.bound = '1';
        root.addEventListener('click', async e => {
            const button = e.target.closest('[data-color-value], [data-color-clear]');
            if (!button || button.disabled) return;
            const picker = button.closest('.schedule-color');
            const clear = button.hasAttribute('data-color-clear');
            const color = clear ? null : safeColor(button.dataset.colorValue);
            const status = picker.querySelector('[role="status"]');
            if (!clear && !color) return;
            const article = button.closest('[data-task-id]');
            if (!article) { newTaskColor = color; updateAddComposer(); return; }
            picker.querySelectorAll('button').forEach(item => { item.disabled = true; });
            try {
                await patchTask(Number(article.dataset.taskId), {color});
            } catch (err) {
                status.textContent = err.message || '保存失败，请重试';
            } finally {
                picker.querySelectorAll('button').forEach(item => { item.disabled = false; });
            }
        });
        const requestedDay = new URLSearchParams(location.search).get('schedule_date');
        day = /^\d{4}-\d{2}-\d{2}$/.test(requestedDay || '') ? requestedDay : todayISO();
        const list = document.getElementById('scheduleList');
        bindDragSorting(list);
        document.getElementById('scheduleFlowBtn')?.addEventListener('click', () => {
            mode = mode === 'flow' ? 'list' : 'flow';
            editingId = null; splitFor = null; render();
        });
        document.getElementById('scheduleDateInput')?.addEventListener('change', e => {
            if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) load(e.target.value).catch(err => showMessage(err.message,'error'));
        });

        document.getElementById('schedulePrevDay')?.addEventListener('click', () => {
            load(shiftDay(currentDay(), -1));
        });
        document.getElementById('scheduleNextDay')?.addEventListener('click', () => {
            load(shiftDay(currentDay(), 1));
        });
        document.getElementById('scheduleAddBtn')?.addEventListener('click', async () => {
            if (addingTask) return;
            const input = document.getElementById('scheduleAddInput');
            const submittedText = input?.value || '';
            if (!submittedText.trim()) { input?.focus(); return; }
            const durationValue = newTaskDuration.trim();
            const estimatedMinutes = durationValue ? parseDuration(durationValue) : null;
            if (durationValue && !Number.isInteger(estimatedMinutes)) {
                if (typeof showMessage === 'function') showMessage(t('schedule.durationInvalid', '请输入例如 30分钟、1小时或1小时30分'), 'error');
                return;
            }
            addingTask = true;
            const addButton = document.getElementById('scheduleAddBtn');
            const focusFromAdd = document.activeElement === addButton;
            addButton.disabled = true;
            try {
                await addTask(submittedText, null, false, {
                    familiarity: newTaskFamiliarity,
                    difficulty: newTaskDifficulty,
                    importance: newTaskImportance,
                    priority: newTaskPriority,
                    estimatedMinutes,
                    color: newTaskColor,
                });
                if (input && input.value === submittedText) input.value = '';
                const durationInput = document.getElementById('scheduleAddDuration');
                if (durationInput) durationInput.value = '';
                newTaskFamiliarity = null;
                newTaskDifficulty = null;
                newTaskImportance = null;
                newTaskPriority = 0;
                newTaskDuration = '';
                newTaskColor = null;
                updateAddComposer();
            } catch (e) {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            } finally {
                addingTask = false;
                addButton.disabled = false;
                if (document.activeElement === addButton || (focusFromAdd && document.activeElement === document.body)) input?.focus();
            }
        });
        document.getElementById('scheduleAddRow')?.addEventListener('click', (e) => {
            const button = e.target.closest('[data-new-act]');
            if (!button) return;
            if (button.dataset.newAct === 'fam') {
                newTaskFamiliarity = newTaskFamiliarity === button.dataset.value ? null : button.dataset.value;
            } else if (button.dataset.newAct === 'difficulty') {
                newTaskDifficulty = newTaskDifficulty === button.dataset.value ? null : button.dataset.value;
            } else if (button.dataset.newAct === 'importance') {
                newTaskImportance = newTaskImportance === button.dataset.value ? null : button.dataset.value;
            } else if (button.dataset.newAct === 'priority') {
                newTaskPriority = parseInt(button.dataset.value, 10);
            }
            updateAddComposer();
        });
        document.getElementById('scheduleAddRow')?.addEventListener('keydown', (e) => {
            if (['scheduleAddInput', 'scheduleAddDuration'].includes(e.target.id) && e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
                e.preventDefault();
                document.getElementById('scheduleAddBtn')?.click();
            }
        });
        document.getElementById('scheduleAddDuration')?.addEventListener('input', (e) => {
            newTaskDuration = e.target.value;
        });
        window.addEventListener('shuran-language-change', () => render());
        window.addEventListener('shuran-practice-change', () => load(currentDay()));
        document.getElementById('schedulePractice')?.addEventListener('click', () => globalThis.ShuranPractice?.openDay(currentDay()));
        document.getElementById('scheduleSortBtn')?.addEventListener('click', () => {
            if (mode === 'sort') {
                mode = sortReturnMode;
            } else {
                sortReturnMode = mode;
                mode = 'sort';
            }
            editingId = null;
            render();
        });
        list?.addEventListener('mousedown', (e) => {
            const hit = actionFromEvent(e);
            if (!hit || !editingId) return;
            if (hit.act === 'delete' || hit.act === 'edit' || hit.act === 'split') {
                e.preventDefault();
            }
        });

        list?.addEventListener('click', async (e) => {
            if (Date.now() < suppressClickUntil) return;
            const hit = actionFromEvent(e);
            if (!hit) return;
            const { article, act, actEl, id } = hit;
            if (act === 'note' || act === 'text' || act === 'minutes') return;
            try {
                if (act === 'edit') {
                    await beginEdit(id);
                } else if (act === 'expand') {
                    if (expandedTasks.has(id)) expandedTasks.delete(id); else expandedTasks.add(id);
                    render();
                    document.querySelector(`#scheduleList [data-task-id="${id}"] [data-act="expand"]`)?.focus({preventScroll:true});
                } else if (act === 'toggle') {
                    const task = flatten(data.tasks || [], []).find((item) => item.id === id);
                    const prior = task.practice?.feedback;
                    if (!task.children?.length && prior?.actual_minutes != null) {
                        const result = task.completed ? 'partial' : 'completed';
                        await apiRequest(`/api/projects/practice/tasks/daily/${id}/feedback`, {method:'POST',body:JSON.stringify(timeFeedbackBody(prior,prior.actual_minutes,result,prior.basis))});
                        await load(currentDay());
                        window.reminderNotificationService?.syncNativeTodos();
                    } else {
                        await patchTask(id, { completed: !task.completed });
                    }
                } else if (act === 'difficulty') {
                    const task = flatten(data.tasks || [], []).find(item => item.id === id);
                    const difficulty = task.practice?.difficulty === actEl.dataset.value ? null : actEl.dataset.value;
                    await apiRequest(`/api/projects/practice/tasks/daily/${id}/attributes`, {method:'PATCH',body:JSON.stringify({difficulty})});
                    await load(currentDay());
                } else if (act === 'practice' || act === 'feedback' || act === 'practice-attributes') {
                    await globalThis.ShuranPractice?.openTask('daily',id,act==='feedback'?'feedback':act==='practice-attributes'?'attributes':'rehearsal');
                } else if (act === 'delete') {
                    editingId = null;
                    data = await api(`/tasks/${id}`, { method: 'DELETE' });
                                render();
                } else if (act === 'split') {
                    splitFor = splitFor === id ? null : id;
                    editingId = null;
                    render();
                    document.querySelector(`#scheduleList [data-task-id="${id}"] [data-split-input]`)?.focus();
                } else if (act === 'split-save') {
                    const input = article.querySelector('[data-split-input]');
                    await addTask(input?.value, id);
                } else if (act === 'fam') {
                    const value = actEl.dataset.value;
                    const task = flatten(data.tasks || [], []).find((t) => t.id === id);
                    if (task && task.familiarity === value) {
                        await patchTask(id, { clear_familiarity: true });
                    } else {
                        await patchTask(id, { familiarity: value });
                    }
                } else if (act === 'up') {
                    await moveTask(id, -1);
                } else if (act === 'down') {
                    await moveTask(id, 1);
                } else if (act === 'parallel') {
                    await toggleParallel(id);
                } else if (act === 'conditions') {
                    globalThis.ShuranConditions?.open('daily', id, load);
                } else if (act === 'reminder') {
                    const task = flatten(data.tasks || [], []).find(item => item.id === id);
                    const value = await window.TimePicker.pick({value:task.remind_time || '09:00', title:'提醒时间', optional:true});
                    if (value !== undefined) await patchTask(id, {remind_time:value || null});
                } else if (act === 'priority') {
                    await patchTask(id, { priority: parseInt(actEl.dataset.value, 10) });
                } else if (act === 'top') {
                    await moveToTop(id);
                }
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
        });

        list?.addEventListener('keydown', async (e) => {
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
            const id = parseInt(article.dataset.taskId, 10);
            if (e.target.dataset.act === 'text') {
                if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
                    e.preventDefault();
                    try {
                        await saveText(id, e.target.value);
                    } catch (err) {
                        if (typeof showMessage === 'function') showMessage(err.message, 'error');
                    }
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    editingId = null;
                    render();
                }
                return;
            }
            if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
            if (e.target.dataset.act === 'note') {
                e.preventDefault();
                e.target.blur();
                return;
            }
            const input = e.target.closest('[data-split-input]');
            if (!input) return;
            e.preventDefault();
            try {
                await addTask(input.value, id);
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
        });

        list?.addEventListener('focusout', (e) => {
            if (e.target.dataset.act !== 'text') return;
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
            const id = parseInt(article.dataset.taskId, 10);
            const value = e.target.value;
            setTimeout(() => {
                if (editingId !== id) return;
                saveText(id, value).catch((err) => {
                    if (typeof showMessage === 'function') showMessage(err.message, 'error');
                });
            }, 120);
        });

        list?.addEventListener('input', (e) => {
            if (e.target.matches('[data-split-input]')) {
                const id = e.target.closest('[data-task-id]').dataset.taskId;
                splitDrafts.set(`${currentDay()}:${id}`, e.target.value);
                return;
            }
            const form = e.target.closest('[data-time-form]');
            if (!form) return;
            const id = form.closest('[data-task-id]').dataset.taskId;
            timeDrafts.set(`${currentDay()}:${id}`, {estimate:form.elements.estimate.value,actual:form.elements.actual.value});
        });

        list?.addEventListener('submit', async (e) => {
            if (!e.target.matches('[data-time-form]')) return;
            e.preventDefault();
            const form = e.target;
            const id = Number(form.closest('[data-task-id]').dataset.taskId);
            const button = form.querySelector('[type="submit"]');
            if (button.disabled) return;
            button.disabled = true;
            try {
                await saveTimeFeedback(id, form);
            } catch (err) {
                form.querySelector('[role="status"]').textContent = err.message;
            } finally {
                button.disabled = false;
            }
        });

        list?.addEventListener('change', async (e) => {
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
            const id = parseInt(article.dataset.taskId, 10);
            try {
                if (e.target.dataset.act === 'method-check') {
                    const task = flatten(data.tasks || [], []).find(item => item.id === id);
                    const checks = task.checklist.map((item,index) => index === Number(e.target.dataset.checkIndex) ? e.target.checked : item.done);
                    await patchTask(id, {checklist_done:checks});
                    document.querySelector(`[data-task-id="${id}"] .flow-method`)?.setAttribute('open','');
                    return;
                }
                if (e.target.dataset.act === 'duration') {
                    const raw = e.target.value;
                    if (raw === '') {
                        await patchTask(id, { clear_estimate: true });
                    } else {
                        const minutes = parseDuration(raw);
                        if (!Number.isFinite(minutes)) {
                            throw new Error(t('schedule.durationInvalid', '请输入例如 30分钟、1小时或1小时30分'));
                        }
                        await patchTask(id, { estimated_minutes: minutes });
                    }
                    return;
                }
                if (e.target.dataset.act === 'note') {
                    await saveNote(id, e.target.value);
                }
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
