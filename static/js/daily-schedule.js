/**
 * 日程安排：添加行动后在同一页完成可选的流程设计。
 */
(function () {
    let day = null;
    let data = { date: null, designed_at: null, tasks: [] };
    let mode = 'list';
    let splitFor = null;
    let editingId = null;
    let suggestions = [];
    let nudgeOpen = false;
    let laterItems = [];
    let editingLaterId = null;
    let dragTaskId = null;
    let dragPressTimer = null;
    let dragActive = false;
    let suppressClickUntil = 0;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragPointerId = null;
    let dragScrollTimer = null;
    const laterOpenKey = 'shuran.scheduleLaterOpen';
    let laterOpen = readLaterOpen();

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

    function readLaterOpen() {
        try {
            return localStorage.getItem(laterOpenKey) === '1';
        } catch (err) {
            return false;
        }
    }

    function rememberLaterOpen() {
        try {
            localStorage.setItem(laterOpenKey, laterOpen ? '1' : '0');
        } catch (err) {
            /* 忽略无痕模式或存储不可用的情况。 */
        }
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

    function parseDuration(value) {
        const raw = String(value || '').trim().toLowerCase();
        if (!raw) return null;
        if (/^\d+$/.test(raw)) return Math.min(1440, parseInt(raw, 10));
        const hours = raw.match(/(\d+(?:\.\d+)?)\s*(?:小时|小時|h|hr|hrs)/);
        const minutes = raw.match(/(\d+)\s*(?:分钟|分鐘|分|min|mins|m)/);
        const h = hours ? Number(hours[1]) * 60 : 0;
        const m = minutes ? Number(minutes[1]) : 0;
        if (!hours && !minutes) return NaN;
        return Math.min(1440, Math.round(h + m));
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
        if (mode === 'design') {
            hint.textContent = t('schedule.hint.design', '未填项可留空。点文字可改，也可拆开或删除');
            return;
        }
        if (mode === 'flow' && data.designed_at) {
            hint.textContent = allDone()
                ? t('schedule.hint.done', '今日已完成')
                : t('schedule.hint.flow', '勾选完成，也可记下执行情况。点任务内容即可修改，也可删除');
            return;
        }
        hint.textContent = allDone()
            ? t('schedule.hint.done', '今日已完成')
            : t('schedule.hint.list', '添加一件事，即可安排熟悉程度和预计用时');
    }

    function allDone() {
        const tasks = executionLeaves(data.tasks || []);
        return tasks.length > 0 && tasks.every((task) => task.completed);
    }

    function renderDoneBtn(task) {
        const label = escapeHtml(t('schedule.done', '完成'));
        if (task.completed) {
            return `<button type="button" class="flow-done-btn is-on" data-act="toggle" aria-pressed="true">${label}</button>`;
        }
        return `<button type="button" class="flow-done-btn" data-act="toggle" aria-pressed="false" aria-label="${label}"></button>`;
    }

    function renderNote(task) {
        if (!task.completed && !(task.note || '').trim()) return '';
        const label = escapeHtml(t('schedule.note', '执行情况'));
        return `<input type="text" class="flow-note" maxlength="500" placeholder="${label}" value="${escapeHtml(task.note || '')}" data-act="note" aria-label="${label}">`;
    }

    function renderToolbar() {
        const label = document.getElementById('scheduleDateLabel');
        if (label) label.textContent = dayLabel(currentDay());
        const doneBtn = document.getElementById('scheduleDoneBtn');
        const backBtn = document.getElementById('scheduleBackBtn');
        const addRow = document.getElementById('scheduleAddRow');
        if (doneBtn) doneBtn.hidden = mode !== 'design';
        if (backBtn) {
            backBtn.hidden = mode === 'list';
            backBtn.textContent = t('schedule.backToList', '回到清单');
        }
        if (addRow) addRow.hidden = mode === 'flow';
        const later = document.getElementById('scheduleLater');
        if (later) later.hidden = mode !== 'list';
    }

    function renderTitle(task) {
        if (editingId === task.id) {
            return `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(task.text)}" data-act="text" aria-label="${escapeHtml(t('schedule.editStepAria', '修改这一步'))}">`;
        }
        return `<div class="flow-task-text" data-act="edit" title="${escapeHtml(t('schedule.editTitle', '点此修改'))}">${escapeHtml(task.text)}</div>`;
    }

    function renderDeleteBtn() {
        return `<button type="button" class="flow-mini-btn flow-danger" data-act="delete">${escapeHtml(t('schedule.delete', '删除'))}</button>`;
    }

    function renderSplitRow(task) {
        if (splitFor !== task.id) return '';
        return `
            <div class="flow-split-row">
                <input type="text" maxlength="500" placeholder="${escapeHtml(t('schedule.split.placeholder', '写下更具体的一步'))}" data-split-input>
                <button type="button" class="flow-ghost-btn" data-act="split-save">${escapeHtml(t('schedule.split.add', '加入'))}</button>
            </div>`;
    }

    function renderEditActions(showSplit) {
        return `
            <div class="flow-task-actions">
                ${showSplit ? `<button type="button" data-act="split">${escapeHtml(t('schedule.split', '拆开'))}</button>` : ''}
                ${renderDeleteBtn()}
            </div>`;
    }

    function renderTask(task, isChild) {
        const meta = [];
        const fam = familiarityLabel(task.familiarity);
        if (fam) meta.push(`<span class="flow-mark">${escapeHtml(fam)}</span>`);
        if (task.priority) meta.push(`<span class="flow-mark priority-${task.priority}">${escapeHtml(priorityLabel(task.priority))}</span>`);
        if (task.estimated_minutes != null) {
            meta.push(`<span class="flow-mark">${escapeHtml(minutesLabel(task.estimated_minutes))}</span>`);
        }
        return `
            <article class="flow-task${isChild ? ' is-child' : ''}${task.completed ? ' is-done' : ''}" data-task-id="${task.id}">
                <div class="flow-task-main">
                    ${renderDoneBtn(task)}
                    ${renderTitle(task)}
                </div>
                ${meta.length ? `<div class="flow-task-meta">${meta.join('')}</div>` : ''}
                ${renderNote(task)}
                ${renderEditActions(true)}
                ${renderSplitRow(task)}
            </article>
            ${(task.children || []).map((child) => renderTask(child, true)).join('')}
        `;
    }

    function renderDesignTask(task, siblings, index, isChild) {
        const prev = index > 0 ? siblings[index - 1] : null;
        const parallelOn = !!(prev && task.parallel_group && task.parallel_group === prev.parallel_group);
        return `
            <article class="flow-task${isChild ? ' is-child' : ''}" data-task-id="${task.id}">
                <div class="flow-task-main">
                    ${renderTitle(task)}
                </div>
                <div class="flow-task-meta">
                    <button type="button" class="flow-chip${task.familiarity === 'familiar' ? ' active' : ''}" data-act="fam" data-value="familiar">${escapeHtml(t('schedule.familiar', '熟悉'))}</button>
                    <button type="button" class="flow-chip${task.familiarity === 'unfamiliar' ? ' active' : ''}" data-act="fam" data-value="unfamiliar">${escapeHtml(t('schedule.unfamiliar', '陌生'))}</button>
                    <input type="number" class="flow-minutes" min="0" max="1440" placeholder="${escapeHtml(t('schedule.minutesPlaceholder', '分钟'))}" value="${task.estimated_minutes ?? ''}" data-act="minutes" aria-label="${escapeHtml(t('schedule.estimatedMinutes', '预估分钟'))}">
                    <button type="button" class="flow-mini-btn" data-act="up">${escapeHtml(t('schedule.moveUp', '上移'))}</button>
                    <button type="button" class="flow-mini-btn" data-act="down">${escapeHtml(t('schedule.moveDown', '下移'))}</button>
                    ${index > 0 ? `<button type="button" class="flow-chip${parallelOn ? ' active' : ''}" data-act="parallel">${escapeHtml(t('schedule.parallelPrevious', '与上一项并行'))}</button>` : ''}
                </div>
                ${renderEditActions(true)}
                ${renderSplitRow(task)}
            </article>
            ${(task.children || []).map((child, i, arr) => renderDesignTask(child, arr, i, true)).join('')}
        `;
    }

    function renderDesignPlan(tasks) {
        return tasks.map((task, index) => {
            const prev = index > 0 ? tasks[index - 1] : null;
            const parallelOn = !!(prev && task.parallel_group && task.parallel_group === prev.parallel_group);
            const path = task.parent_path && task.parent_path.length
                ? `<div class="flow-parent-path">${escapeHtml(task.parent_path.join(' / '))}</div>`
                : '';
            return `
                <article class="flow-task flow-sortable${task.completed ? ' is-done' : ''}" data-task-id="${task.id}">
                    <div class="flow-task-main">${renderTitle(task)}</div>
                    ${path}
                    <div class="flow-task-meta">
                        <button type="button" class="flow-chip${task.familiarity === 'familiar' ? ' active' : ''}" data-act="fam" data-value="familiar">${escapeHtml(t('schedule.familiar', '熟悉'))}</button>
                        <button type="button" class="flow-chip${task.familiarity === 'unfamiliar' ? ' active' : ''}" data-act="fam" data-value="unfamiliar">${escapeHtml(t('schedule.unfamiliar', '陌生'))}</button>
                        <button type="button" class="flow-chip${task.priority === 2 ? ' active' : ''}" data-act="priority" data-value="2">${escapeHtml(t('schedule.priority.high', '最高'))}</button>
                        <button type="button" class="flow-chip${task.priority === 1 ? ' active' : ''}" data-act="priority" data-value="1">${escapeHtml(t('schedule.priority.important', '重要'))}</button>
                        <button type="button" class="flow-chip${!task.priority ? ' active' : ''}" data-act="priority" data-value="0">${escapeHtml(t('schedule.priority.normal', '普通'))}</button>
                        <input type="text" class="flow-minutes" maxlength="20" placeholder="${escapeHtml(t('schedule.durationPlaceholder', '如 1小时30分'))}" value="${escapeHtml(durationInputValue(task.estimated_minutes))}" data-act="duration" aria-label="${escapeHtml(t('schedule.estimatedDuration', '预计用时'))}">
                        ${index > 0 ? `<button type="button" class="flow-chip${parallelOn ? ' active' : ''}" data-act="parallel">${escapeHtml(t('schedule.parallelPrevious', '与上一项并行'))}</button>` : ''}
                        ${index > 0 ? `<button type="button" class="flow-mini-btn" data-act="up">${escapeHtml(t('schedule.moveUp', '上移'))}</button>` : ''}
                        ${index < tasks.length - 1 ? `<button type="button" class="flow-mini-btn" data-act="down">${escapeHtml(t('schedule.moveDown', '下移'))}</button>` : ''}
                        ${index > 0 ? `<button type="button" class="flow-mini-btn" data-act="top">${escapeHtml(t('schedule.moveTop', '移到第一项'))}</button>` : ''}
                    </div>
                    ${renderEditActions(false)}
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
        const fam = familiarityLabel(task.familiarity);
        const extra = [];
        if (fam) extra.push(fam);
        if (task.estimated_minutes != null) extra.push(minutesLabel(task.estimated_minutes));
        if (task.priority) extra.push(priorityLabel(task.priority));
        const path = task.parent_path && task.parent_path.length
            ? `<div class="flow-parent-path">${escapeHtml(task.parent_path.join(' / '))}</div>`
            : '';
        return `
            <article class="flow-task${task.completed ? ' is-done' : ''}" data-task-id="${task.id}">
                <div class="flow-task-main">
                    ${renderDoneBtn(task)}
                    ${renderTitle(task)}
                </div>
                ${path}
                ${extra.length ? `<div class="flow-task-meta">${extra.map((x) => `<span class="flow-mark">${escapeHtml(x)}</span>`).join('')}</div>` : ''}
                ${renderNote(task)}
                ${renderEditActions(false)}
                ${task.children && task.children.length ? renderFlowGroups(task.children) : ''}
            </article>
        `;
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
        if (mode === 'list' || mode === 'design') list.querySelector('[data-split-input]')?.focus();
    }

    function renderNudge() {
        const box = document.getElementById('scheduleNudge');
        if (!box) return;
        const show = mode === 'list' && suggestions.length > 0;
        box.hidden = !show;
        if (!show) {
            box.innerHTML = '';
            box.classList.remove('is-collapsed');
            return;
        }
        const rest = Math.max(0, suggestions.length - 1);
        const collapsed = !nudgeOpen && rest > 0;
        const visible = nudgeOpen ? suggestions : suggestions.slice(0, 1);
        box.classList.toggle('is-collapsed', collapsed);
        box.innerHTML = `
            <div class="schedule-nudge-kicker">${escapeHtml(t('schedule.nudge.kicker', '行动项 · 还没排进今天'))}</div>
            ${visible.map((item, idx) => `
                <div class="schedule-nudge-item" data-action-id="${item.action_id}">
                    <div class="schedule-nudge-copy">
                        <div class="schedule-nudge-text">${escapeHtml(item.text)}</div>
                        ${collapsed ? '' : `<div class="schedule-nudge-why">${escapeHtml(item.reason || '')}</div>`}
                    </div>
                    <div class="schedule-nudge-actions">
                        <button type="button" data-nudge-add="${item.action_id}">${escapeHtml(t('schedule.nudge.add', '加入'))}</button>
                        ${collapsed && idx === 0
                            ? `<button type="button" class="schedule-nudge-more" data-nudge-more>${escapeHtml(withCount(t('schedule.nudge.more', '还有 {count} 个'), rest))}</button>`
                            : ''}
                    </div>
                </div>
            `).join('')}
            ${nudgeOpen && rest > 0
                ? `<button type="button" class="schedule-nudge-more is-footer" data-nudge-more>${escapeHtml(t('schedule.collapse', '收起'))}</button>`
                : ''}
        `;
    }

    function laterIntoLabel() {
        return currentDay() === todayISO()
            ? t('schedule.later.intoToday', '写进今天')
            : t('schedule.later.intoDay', '写进这一天');
    }

    function renderLaterShell() {
        const root = document.getElementById('scheduleLater');
        const toggle = document.getElementById('scheduleLaterToggle');
        const body = document.getElementById('scheduleLaterBody');
        const summary = document.getElementById('scheduleLaterSummary');
        const count = laterItems.length;
        if (root) root.classList.toggle('is-collapsed', !laterOpen);
        if (toggle) toggle.setAttribute('aria-expanded', laterOpen ? 'true' : 'false');
        if (body) body.hidden = false;
        if (summary) {
            const countLabel = count
                ? withCount(t('schedule.later.count', '{count} 个'), count)
                : t('schedule.later.emptySummary', '空');
            summary.textContent = laterOpen
                ? `${countLabel} · ${t('schedule.later.collapseList', '收起列表')}`
                : `${countLabel} · ${t('schedule.later.expandList', '展开列表')}`;
        }
    }

    function renderLater() {
        renderLaterShell();
        const box = document.getElementById('scheduleLaterList');
        if (!box) return;
        if (!laterOpen) {
            box.innerHTML = '';
            return;
        }
        if (!laterItems.length) {
            box.innerHTML = `<p class="schedule-later-empty">${escapeHtml(t('schedule.later.empty', '先记下来，准备好了再写进这一天'))}</p>`;
            return;
        }
        box.innerHTML = laterItems.map((item) => {
            const title = editingLaterId === item.id
                ? `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(item.text)}" data-later-act="text" aria-label="${escapeHtml(t('schedule.later.editAria', '修改以后想做'))}">`
                : `<div class="flow-task-text" data-later-act="edit" title="${escapeHtml(t('schedule.editTitle', '点此修改'))}">${escapeHtml(item.text)}</div>`;
            return `
                <article class="schedule-later-item" data-later-id="${item.id}">
                    <div class="flow-task-main">
                        ${title}
                    </div>
                    <div class="flow-task-actions">
                        <button type="button" data-later-act="into">${laterIntoLabel()}</button>
                        <button type="button" class="flow-mini-btn flow-danger" data-later-act="delete">${escapeHtml(t('schedule.delete', '删除'))}</button>
                    </div>
                </article>`;
        }).join('');
        if (editingLaterId) {
            const input = box.querySelector(`[data-later-id="${editingLaterId}"] [data-later-act="text"]`);
            if (input) {
                input.focus();
                input.select();
            }
        }
    }

    function render() {
        const list = document.getElementById('scheduleList');
        if (!list) return;
        renderToolbar();
        setHint();
        renderNudge();
        renderLater();
        if (!(data.tasks || []).length) {
            list.innerHTML = `<p class="flow-empty">${escapeHtml(t('schedule.emptyTasks', '还没有行动'))}</p>`;
            return;
        }
        if (mode === 'design') {
            list.innerHTML = renderDesignPlan(executionLeaves(data.tasks));
        } else if (mode === 'flow') {
            list.innerHTML = renderFlowGroups(executionLeaves(data.tasks));
        } else {
            list.innerHTML = data.tasks.map((task) => renderTask(task, false)).join('');
        }
        focusEditor();
    }

    async function loadSuggestions() {
        const token = localStorage.getItem('authToken');
        const box = document.getElementById('scheduleNudge');
        if (!token) {
            suggestions = [];
            return;
        }
        try {
            const result = await api(`/suggestions?task_date=${encodeURIComponent(currentDay())}`);
            suggestions = result.items || [];
        } catch (err) {
            suggestions = [];
            if (box) box.hidden = true;
        }
    }

    async function loadLater() {
        const token = localStorage.getItem('authToken');
        if (!token) {
            laterItems = [];
            return;
        }
        try {
            const result = await api('/future');
            laterItems = result.items || [];
        } catch (err) {
            laterItems = [];
        }
    }

    async function load(nextDay) {
        const token = localStorage.getItem('authToken');
        if (!token) {
            data = { date: currentDay(), designed_at: null, tasks: [] };
            suggestions = [];
            laterItems = [];
            render();
            return;
        }
        day = nextDay || currentDay();
        editingId = null;
        editingLaterId = null;
        data = await api(`?task_date=${encodeURIComponent(day)}`);
        if (mode === 'flow' && !data.designed_at) mode = 'list';
        await Promise.all([loadSuggestions(), loadLater()]);
        render();
    }

    async function addTask(text, parentId, actionId, openDesign) {
        const value = (text || '').trim();
        if (!value) return;
        data = await api('/tasks', {
            method: 'POST',
            body: JSON.stringify({
                text: value,
                task_date: currentDay(),
                parent_id: parentId || null,
                action_id: actionId || null,
            }),
        });
        splitFor = null;
        if (openDesign) {
            const tasks = flatten(data.tasks || [], []);
            const newest = tasks.reduce((latest, task) => (!latest || task.id > latest.id ? task : latest), null);
            mode = 'design';
            editingId = newest ? newest.id : null;
        }
        await loadSuggestions();
        render();
    }

    async function addLater(text) {
        const value = (text || '').trim();
        if (!value) return;
        const result = await api('/future', {
            method: 'POST',
            body: JSON.stringify({ text: value }),
        });
        laterItems = result.items || [];
        editingLaterId = null;
        renderLater();
    }

    async function saveLaterText(id, value) {
        const item = laterItems.find((row) => row.id === id);
        const next = (value || '').trim();
        const prev = item ? String(item.text || '').trim() : '';
        if (editingLaterId === id) editingLaterId = null;
        if (!item || !next || next === prev) {
            renderLater();
            return;
        }
        const result = await api(`/future/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ text: next }),
        });
        laterItems = result.items || [];
        renderLater();
    }

    async function beginLaterEdit(id) {
        if (editingLaterId === id) return;
        if (editingLaterId) {
            const input = document.querySelector(`#scheduleLaterList [data-later-id="${editingLaterId}"] [data-later-act="text"]`);
            if (input) await saveLaterText(editingLaterId, input.value);
        }
        editingLaterId = id;
        renderLater();
    }

    async function deleteLater(id) {
        const result = await api(`/future/${id}`, { method: 'DELETE' });
        laterItems = result.items || [];
        if (editingLaterId === id) editingLaterId = null;
        renderLater();
    }

    async function scheduleLater(id) {
        data = await api(`/future/${id}/schedule`, {
            method: 'POST',
            body: JSON.stringify({ task_date: currentDay() }),
        });
        laterItems = laterItems.filter((row) => row.id !== id);
        if (editingLaterId === id) editingLaterId = null;
        await Promise.all([loadSuggestions(), loadLater()]);
        render();
    }

    async function patchTask(id, body) {
        data = await api(`/tasks/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
        });
        render();
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
        if (mode === 'design') {
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
                    sort_order: task.sort_order,
                    flow_order: index,
                    parallel_group: task.parallel_group,
                    priority: task.priority ?? 0,
                })),
            }),
        });
        await load(currentDay());
    }

    async function toggleParallel(taskId) {
        const list = mode === 'design' ? executionLeaves(data.tasks || []) : null;
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
        document.querySelectorAll('#scheduleList .is-dragging, #scheduleList .is-drop-target')
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
        document.querySelectorAll('#scheduleList .is-drop-target')
            .forEach((item) => item.classList.remove('is-drop-target'));
        if (article && parseInt(article.dataset.taskId, 10) !== dragTaskId) {
            article.classList.add('is-drop-target');
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
            if (mode !== 'design') return;
            if (e.target.closest('button, input, textarea, select')) return;
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
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
                const moved = Math.hypot(e.clientX - dragStartX, e.clientY - dragStartY);
                if (dragPressTimer && moved > 8) clearDragPress();
                if (e.pointerType === 'mouse' && moved > 6) {
                    const article = e.target.closest('[data-task-id]');
                    if (article) startPointerDrag(article, parseInt(article.dataset.taskId, 10), e.pointerId);
                }
                return;
            }
            e.preventDefault();
            updateDragAutoScroll(e.clientY);
            markDragTarget(dragTargetAt(e.clientX, e.clientY));
        });

        list?.addEventListener('pointerup', async (e) => {
            clearDragPress();
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
        day = todayISO();
        const list = document.getElementById('scheduleList');
        const nudge = document.getElementById('scheduleNudge');
        bindDragSorting(list);

        document.getElementById('schedulePrevDay')?.addEventListener('click', () => {
            nudgeOpen = false;
            load(shiftDay(currentDay(), -1));
        });
        document.getElementById('scheduleNextDay')?.addEventListener('click', () => {
            nudgeOpen = false;
            load(shiftDay(currentDay(), 1));
        });
        document.getElementById('scheduleAddBtn')?.addEventListener('click', () => {
            const input = document.getElementById('scheduleAddInput');
            addTask(input?.value, null, null, true).then(() => {
                if (input) input.value = '';
            }).catch((e) => {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            });
        });
        document.getElementById('scheduleAddInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('scheduleAddBtn')?.click();
            }
        });
        document.getElementById('scheduleLaterAddBtn')?.addEventListener('click', () => {
            const input = document.getElementById('scheduleLaterInput');
            addLater(input?.value).then(() => {
                if (input) input.value = '';
            }).catch((e) => {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            });
        });
        document.getElementById('scheduleLaterInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('scheduleLaterAddBtn')?.click();
            }
        });
        document.getElementById('scheduleLaterToggle')?.addEventListener('click', () => {
            laterOpen = !laterOpen;
            if (!laterOpen) editingLaterId = null;
            rememberLaterOpen();
            renderLater();
        });
        window.addEventListener('shuran-language-change', () => render());
        document.getElementById('scheduleDoneBtn')?.addEventListener('click', async () => {
            try {
                data = await api('/design', {
                    method: 'POST',
                    body: JSON.stringify({ task_date: currentDay() }),
                });
                mode = 'flow';
                editingId = null;
                render();
            } catch (e) {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            }
        });
        document.getElementById('scheduleBackBtn')?.addEventListener('click', () => {
            mode = 'list';
            editingId = null;
            editingLaterId = null;
            render();
        });

        const laterList = document.getElementById('scheduleLaterList');

        laterList?.addEventListener('mousedown', (e) => {
            const actEl = e.target.closest('[data-later-act]');
            if (!actEl || !editingLaterId) return;
            const act = actEl.dataset.laterAct;
            if (act === 'delete' || act === 'edit' || act === 'into') {
                e.preventDefault();
            }
        });

        laterList?.addEventListener('click', async (e) => {
            const actEl = e.target.closest('[data-later-act]');
            const article = e.target.closest('[data-later-id]');
            if (!actEl || !article) return;
            const act = actEl.dataset.laterAct;
            if (act === 'text') return;
            const id = parseInt(article.dataset.laterId, 10);
            try {
                if (act === 'edit') {
                    await beginLaterEdit(id);
                } else if (act === 'delete') {
                    await deleteLater(id);
                } else if (act === 'into') {
                    await scheduleLater(id);
                }
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
        });

        laterList?.addEventListener('keydown', async (e) => {
            const article = e.target.closest('[data-later-id]');
            if (!article || e.target.dataset.laterAct !== 'text') return;
            const id = parseInt(article.dataset.laterId, 10);
            if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
                e.preventDefault();
                try {
                    await saveLaterText(id, e.target.value);
                } catch (err) {
                    if (typeof showMessage === 'function') showMessage(err.message, 'error');
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                editingLaterId = null;
                renderLater();
            }
        });

        laterList?.addEventListener('focusout', (e) => {
            if (e.target.dataset.laterAct !== 'text') return;
            const article = e.target.closest('[data-later-id]');
            if (!article) return;
            const id = parseInt(article.dataset.laterId, 10);
            const value = e.target.value;
            setTimeout(() => {
                if (editingLaterId !== id) return;
                saveLaterText(id, value).catch((err) => {
                    if (typeof showMessage === 'function') showMessage(err.message, 'error');
                });
            }, 120);
        });

        nudge?.addEventListener('click', async (e) => {
            const more = e.target.closest('[data-nudge-more]');
            if (more) {
                nudgeOpen = !nudgeOpen;
                renderNudge();
                return;
            }
            const addBtn = e.target.closest('[data-nudge-add]');
            if (!addBtn) return;
            const actionId = parseInt(addBtn.getAttribute('data-nudge-add'), 10);
            const item = suggestions.find((row) => row.action_id === actionId);
            if (!item) return;
            try {
                await addTask(item.text, null, actionId);
            } catch (err) {
                if (typeof showMessage === 'function') showMessage(err.message, 'error');
            }
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
                    if (mode === 'list') {
                        openDesign(id);
                    } else {
                        await beginEdit(id);
                    }
                } else if (act === 'toggle') {
                    const task = flatten(data.tasks || [], []).find((item) => item.id === id);
                    await patchTask(id, { completed: !(task && task.completed) });
                } else if (act === 'delete') {
                    editingId = null;
                    data = await api(`/tasks/${id}`, { method: 'DELETE' });
                    await loadSuggestions();
                    render();
                } else if (act === 'split') {
                    splitFor = splitFor === id ? null : id;
                    editingId = null;
                    render();
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

        list?.addEventListener('change', async (e) => {
            const article = e.target.closest('[data-task-id]');
            if (!article) return;
            const id = parseInt(article.dataset.taskId, 10);
            try {
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
