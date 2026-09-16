/**
 * 日程安排：先写下具体行动，再可选进入流程设计。
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

    function familiarityLabel(value) {
        if (value === 'familiar') return '熟悉';
        if (value === 'unfamiliar') return '陌生';
        return '';
    }

    function minutesLabel(mins) {
        if (mins == null) return '';
        const m = parseInt(mins, 10);
        if (!m) return '未估时';
        if (m < 60) return `${m} 分钟`;
        const h = Math.floor(m / 60);
        const r = m % 60;
        return r ? `${h} 小时 ${r} 分` : `${h} 小时`;
    }

    async function api(path, options) {
        if (typeof apiRequest !== 'function') throw new Error('请先登录');
        return apiRequest(`/api/schedule${path}`, options || {});
    }

    function currentDay() {
        return day || todayISO();
    }

    function dayLabel(iso) {
        const today = todayISO();
        if (iso === today) return '今天';
        const parts = String(iso).split('-');
        if (parts.length < 3) return iso;
        return `${Number(parts[1])}月${Number(parts[2])}日`;
    }

    function setHint() {
        const hint = document.getElementById('scheduleHint');
        if (!hint) return;
        if (mode === 'design') {
            hint.textContent = '未填项可留空。点文字可改，也可拆开或删除';
            return;
        }
        if (mode === 'flow' && data.designed_at) {
            hint.textContent = allDone() ? '今日已完成' : '勾选完成，也可记下执行情况。写错了点文字可改，右侧可删除';
            return;
        }
        hint.textContent = allDone() ? '今日已完成' : '写下今天要做的事。写错了点文字可改，右侧可删除';
    }

    function allDone() {
        const tasks = flatten(data.tasks || [], []);
        return tasks.length > 0 && tasks.every((task) => task.completed);
    }

    function renderDoneBtn(task) {
        if (task.completed) {
            return '<button type="button" class="flow-done-btn is-on" data-act="toggle" aria-pressed="true">完成</button>';
        }
        return '<button type="button" class="flow-done-btn" data-act="toggle" aria-pressed="false" aria-label="完成"></button>';
    }

    function renderNote(task) {
        if (!task.completed && !(task.note || '').trim()) return '';
        return `<input type="text" class="flow-note" maxlength="500" placeholder="执行情况" value="${escapeHtml(task.note || '')}" data-act="note" aria-label="执行情况">`;
    }

    function renderToolbar() {
        const label = document.getElementById('scheduleDateLabel');
        if (label) label.textContent = dayLabel(currentDay());
        const designBtn = document.getElementById('scheduleDesignBtn');
        const doneBtn = document.getElementById('scheduleDoneBtn');
        const backBtn = document.getElementById('scheduleBackBtn');
        const addRow = document.getElementById('scheduleAddRow');
        if (designBtn) designBtn.hidden = mode !== 'list' || !(data.tasks || []).length;
        if (doneBtn) doneBtn.hidden = mode !== 'design';
        if (backBtn) {
            backBtn.hidden = mode === 'list';
            backBtn.textContent = '回到清单';
        }
        if (addRow) addRow.hidden = mode !== 'list';
        const later = document.getElementById('scheduleLater');
        if (later) later.hidden = mode !== 'list';
    }

    function renderTitle(task) {
        if (editingId === task.id) {
            return `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(task.text)}" data-act="text" aria-label="修改这一步">`;
        }
        return `<div class="flow-task-text" data-act="edit" title="点此修改">${escapeHtml(task.text)}</div>`;
    }

    function renderDeleteBtn() {
        return '<button type="button" class="flow-mini-btn flow-danger" data-act="delete">删除</button>';
    }

    function renderSplitRow(task) {
        if (splitFor !== task.id) return '';
        return `
            <div class="flow-split-row">
                <input type="text" maxlength="500" placeholder="写下更具体的一步" data-split-input>
                <button type="button" class="flow-ghost-btn" data-act="split-save">加入</button>
            </div>`;
    }

    function renderEditActions(showSplit) {
        return `
            <div class="flow-task-actions">
                <button type="button" data-act="edit">修改</button>
                ${showSplit ? '<button type="button" data-act="split">拆开</button>' : ''}
            </div>`;
    }

    function renderTask(task, isChild) {
        const meta = [];
        const fam = familiarityLabel(task.familiarity);
        if (fam) meta.push(`<span class="flow-mark">${escapeHtml(fam)}</span>`);
        if (task.estimated_minutes != null) {
            meta.push(`<span class="flow-mark">${escapeHtml(minutesLabel(task.estimated_minutes))}</span>`);
        }
        return `
            <article class="flow-task${isChild ? ' is-child' : ''}${task.completed ? ' is-done' : ''}" data-task-id="${task.id}">
                <div class="flow-task-main">
                    ${renderDoneBtn(task)}
                    ${renderTitle(task)}
                    ${renderDeleteBtn()}
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
                    ${renderDeleteBtn()}
                </div>
                <div class="flow-task-meta">
                    <button type="button" class="flow-chip${task.familiarity === 'familiar' ? ' active' : ''}" data-act="fam" data-value="familiar">熟悉</button>
                    <button type="button" class="flow-chip${task.familiarity === 'unfamiliar' ? ' active' : ''}" data-act="fam" data-value="unfamiliar">陌生</button>
                    <input type="number" class="flow-minutes" min="0" max="1440" placeholder="分钟" value="${task.estimated_minutes ?? ''}" data-act="minutes" aria-label="预估分钟">
                    <button type="button" class="flow-mini-btn" data-act="up">上移</button>
                    <button type="button" class="flow-mini-btn" data-act="down">下移</button>
                    ${index > 0 ? `<button type="button" class="flow-chip${parallelOn ? ' active' : ''}" data-act="parallel">与上一项并行</button>` : ''}
                </div>
                ${renderEditActions(true)}
                ${renderSplitRow(task)}
            </article>
            ${(task.children || []).map((child, i, arr) => renderDesignTask(child, arr, i, true)).join('')}
        `;
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
        return `
            <article class="flow-task${task.completed ? ' is-done' : ''}" data-task-id="${task.id}">
                <div class="flow-task-main">
                    ${renderDoneBtn(task)}
                    ${renderTitle(task)}
                    ${renderDeleteBtn()}
                </div>
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
                        <div class="flow-step-label">并行</div>
                        <div class="flow-parallel${group.items.length > 1 ? ' has-many' : ''}">${inner}</div>
                    </div>`;
            }
            return `
                <div class="flow-lane">
                    <div class="flow-step-label">第 ${i + 1} 步</div>
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
            return;
        }
        const visible = nudgeOpen ? suggestions : suggestions.slice(0, 3);
        const rest = suggestions.length - visible.length;
        box.innerHTML = `
            <div class="schedule-nudge-kicker">排进今天</div>
            ${visible.map((item) => `
                <div class="schedule-nudge-item" data-action-id="${item.action_id}">
                    <div class="schedule-nudge-copy">
                        <div class="schedule-nudge-text">${escapeHtml(item.text)}</div>
                        <div class="schedule-nudge-why">${escapeHtml(item.reason || '')}</div>
                    </div>
                    <button type="button" data-nudge-add="${item.action_id}">加入</button>
                </div>
            `).join('')}
            ${rest > 0 ? `<button type="button" class="schedule-nudge-more" data-nudge-more>还有 ${rest} 个</button>` : ''}
        `;
    }

    function laterIntoLabel() {
        return currentDay() === todayISO() ? '写进今天' : '写进这一天';
    }

    function renderLater() {
        const box = document.getElementById('scheduleLaterList');
        if (!box) return;
        if (!laterItems.length) {
            box.innerHTML = '<p class="schedule-later-empty">先记下来，准备好了再写进这一天</p>';
            return;
        }
        box.innerHTML = laterItems.map((item) => {
            const title = editingLaterId === item.id
                ? `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(item.text)}" data-later-act="text" aria-label="修改以后想做">`
                : `<div class="flow-task-text" data-later-act="edit" title="点此修改">${escapeHtml(item.text)}</div>`;
            return `
                <article class="schedule-later-item" data-later-id="${item.id}">
                    <div class="flow-task-main">
                        ${title}
                        <button type="button" class="flow-mini-btn flow-danger" data-later-act="delete">删除</button>
                    </div>
                    <div class="flow-task-actions">
                        <button type="button" data-later-act="edit">修改</button>
                        <button type="button" data-later-act="into">${laterIntoLabel()}</button>
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
            list.innerHTML = '<p class="flow-empty">还没有行动</p>';
            return;
        }
        if (mode === 'design') {
            list.innerHTML = data.tasks.map((task, i, arr) => renderDesignTask(task, arr, i, false)).join('');
        } else if (mode === 'flow') {
            list.innerHTML = renderFlowGroups(data.tasks);
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

    async function addTask(text, parentId, actionId) {
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

    async function toggleParallel(taskId) {
        const found = siblingsOf(taskId);
        if (!found || found.index === 0) return;
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
            if (hint) hint.textContent = e.message || '加载失败';
        });
    };

    function onReady() {
        const root = document.getElementById('homeSchedule') || document.getElementById('schedule');
        if (!root || root.dataset.bound) return;
        root.dataset.bound = '1';
        day = todayISO();
        const list = document.getElementById('scheduleList');
        const nudge = document.getElementById('scheduleNudge');

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
            addTask(input?.value).then(() => {
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
        document.getElementById('scheduleDesignBtn')?.addEventListener('click', () => {
            mode = 'design';
            editingId = null;
            editingLaterId = null;
            render();
        });
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
                nudgeOpen = true;
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
            const hit = actionFromEvent(e);
            if (!hit) return;
            const { article, act, actEl, id } = hit;
            if (act === 'note' || act === 'text' || act === 'minutes') return;
            try {
                if (act === 'edit') {
                    await beginEdit(id);
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
                if (e.target.dataset.act === 'minutes') {
                    const raw = e.target.value;
                    if (raw === '') {
                        await patchTask(id, { clear_estimate: true });
                    } else {
                        await patchTask(id, { estimated_minutes: parseInt(raw, 10) });
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
