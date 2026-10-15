/** 今日待办与日历。 */
(function () {
    function escapeHtml(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    async function todayApi(path, options = {}) {
        if (typeof apiRequest !== 'function') throw new Error('请先登录');
        return apiRequest(`/api/today${path}`, options);
    }
    window.loadTodayDashboard = async function loadTodayDashboard() {
        if (!localStorage.getItem('authToken')) { renderDailyTodos([]); return; }
        try {
            renderDailyTodos(await todayApi('/todos'));
            window.reminderNotificationService?.syncNativeTodos();
            startTodayAutoRefresh();
        } catch (error) { console.error('加载今日待办失败', error); }
    };
    function renderDailyTodos(todos) {
        const list = document.getElementById('todayTodosList');
        if (!list) return;
        if (!todos.length) {
            list.innerHTML = '<p style="color:#999;font-size:0.85rem;">暂无待办，在下方添加</p>';
            return;
        }
        list.innerHTML = todos.map((t) => renderTodoItem(t)).join('');
    }

    function renderTodoItem(t) {
        const done = t.completed;
        const remind = t.remind_time ? String(t.remind_time).slice(0, 5) : '';
        return `
            <div class="todo-item ${done ? 'completed' : ''}" data-todo-id="${t.id}">
                <div class="todo-main">
                    <span class="todo-text" ondblclick="editDailyTodo(${t.id})">${escapeHtml(t.text)}</span>
                    ${remind ? `<span class="todo-remind-badge">${escapeHtml(remind)}</span>` : ''}
                </div>
                <div class="todo-actions">
                    <button type="button" class="todo-btn edit" onclick="setTodoRemindTime(${t.id})" title="提醒时间">时</button>
                    <button type="button" class="todo-btn edit" onclick="editDailyTodo(${t.id})" title="编辑">✎</button>
                    <button type="button" class="todo-check" onclick="toggleDailyTodo(${t.id}, ${!done})" title="${done ? '标为未完成' : '完成'}">${done ? '↩' : '✓'}</button>
                    <button type="button" class="todo-btn delete" onclick="deleteDailyTodo(${t.id})" title="删除">×</button>
                </div>
            </div>`;
    }

    function readRemindTime(inputId) {
        const el = document.getElementById(inputId);
        const value = el?.value?.trim();
        return value || null;
    }

    window.addDailyTodo = async function () {
        const input = document.getElementById('newTodoInput');
        const text = input?.value?.trim();
        if (!text) return;
        const payload = { text };
        const remindTime = readRemindTime('newTodoRemindTime');
        if (remindTime) payload.remind_time = remindTime;
        try {
            await todayApi('/todos', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            input.value = '';
            const timeInput = document.getElementById('newTodoRemindTime');
            if (timeInput) timeInput.value = '';
            await refreshTodosAfterChange();
        } catch (e) {
            const detail = typeof humanizeApiError === 'function' ? humanizeApiError(e) : (e && e.message ? e.message : '请稍后重试');
            showMessage('添加待办失败: ' + detail, 'error');
        }
    };

    window.setTodoRemindTime = async function (id) {
        const item = document.querySelector(`[data-todo-id="${id}"]`);
        const current = item?.querySelector('.todo-remind-badge')?.textContent?.replace(/[^\d:]/g, '') || '';
        let remindTime = '';
        if (window.TimePicker && typeof window.TimePicker.pick === 'function') {
            const picked = await window.TimePicker.pick({
                value: current || '20:00',
                title: '提醒时间',
                optional: true,
            });
            if (picked === undefined) return;
            remindTime = picked;
        } else {
            const next = window.prompt('设置提醒时间（HH:MM，留空则取消）', current);
            if (next === null) return;
            remindTime = next.trim();
            if (remindTime && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(remindTime)) {
                showMessage('时间格式应为 HH:MM', 'error');
                return;
            }
        }
        try {
            await todayApi(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify({ remind_time: remindTime }) });
            await refreshTodosAfterChange();
        } catch (e) {
            showMessage('设置提醒失败', 'error');
        }
    };

    window.toggleDailyTodo = async function (id, completed) {
        try {
            await todayApi(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify({ completed }) });
            await refreshTodosAfterChange();
        } catch (e) {
            showMessage('更新失败', 'error');
        }
    };

    window.editDailyTodo = async function (id) {
        const item = document.querySelector(`[data-todo-id="${id}"]`);
        if (!item || item.classList.contains('editing')) return;
        const textEl = item.querySelector('.todo-text');
        const current = textEl.textContent;
        item.classList.add('editing');
        const input = document.createElement('input');
        input.className = 'todo-edit-input';
        input.value = current;
        textEl.after(input);
        input.focus();
        input.select();

        const save = async () => {
            const val = input.value.trim();
            if (!val) {
                showMessage('内容不能为空', 'error');
                return;
            }
            try {
                await todayApi(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify({ text: val }) });
                await refreshTodosAfterChange();
            } catch (e) {
                showMessage('保存失败', 'error');
            }
        };
        input.addEventListener('blur', save, { once: true });
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') input.blur();
            if (ev.key === 'Escape') {
                if (window.selectedCalendarDate) loadCalendarDayTodos();
                else loadTodayDashboard();
            }
        });
    };

    window.deleteDailyTodo = async function (id) {
        if (!confirm('确定删除？')) return;
        try {
            await todayApi(`/todos/${id}`, { method: 'DELETE' });
            await refreshTodosAfterChange();
        } catch (e) {
            const detail = typeof humanizeApiError === 'function' ? humanizeApiError(e) : (e && e.message ? e.message : '请稍后重试');
            showMessage('删除失败: ' + detail, 'error');
        }
    };

    function beijingTodayKey() {
        if (typeof getBeijingParts === 'function') {
            const p = getBeijingParts();
            return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
        }
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }

    function compareDateKey(a, b) {
        if (a === b) return 0;
        return a < b ? -1 : 1;
    }

    function formatDateKeyLabel(dateKey) {
        const [y, m, d] = dateKey.split('-').map(Number);
        const date = new Date(y, m - 1, d);
        const weekday = ['日', '一', '二', '三', '四', '五', '六'][date.getDay()];
        const today = beijingTodayKey();
        let tag = '';
        if (dateKey === today) tag = ' · 今天';
        else if (compareDateKey(dateKey, today) < 0) tag = ' · 已过';
        else tag = ' · 未来';
        return `${y}年${m}月${d}日 周${weekday}${tag}`;
    }

    async function refreshTodosAfterChange() {
        await loadTodayDashboard();
        if (window.selectedCalendarDate) {
            await loadCalendarDayTodos();
        }
        await refreshOpenMonthMarkers();
        if (window.reminderNotificationService) {
            window.reminderNotificationService.syncNativeTodos();
        }
    }

    async function refreshOpenMonthMarkers() {
        const first = document.querySelector('.calendar-day[data-date]');
        if (!first || typeof window.refreshCalendarTodoMarkers !== 'function') return;
        const [y, m] = first.dataset.date.split('-');
        await window.refreshCalendarTodoMarkers(Number(y), Number(m));
    }

    window.refreshCalendarTodoMarkers = async function (year, month) {
        const grid = document.getElementById('calendarGrid');
        if (!grid) return;
        try {
            const data = await todayApi(`/todos/month?year=${year}&month=${month}`);
            const map = {};
            (data.days || []).forEach((d) => {
                const key = typeof d.date === 'string' ? d.date : String(d.date);
                map[key] = d;
            });
            grid.querySelectorAll('.calendar-day[data-date]').forEach((el) => {
                const info = map[el.dataset.date];
                el.classList.toggle('has-todos', Boolean(info && info.total > 0));
                el.classList.remove('has-events');
                let indicator = el.querySelector('.event-indicator');
                if (info && info.total > 0) {
                    if (!indicator) {
                        indicator = document.createElement('div');
                        indicator.className = 'event-indicator';
                        el.appendChild(indicator);
                    }
                    indicator.classList.toggle('today', el.classList.contains('today'));
                } else if (indicator) {
                    indicator.remove();
                }
            });
        } catch (e) {
            console.warn('加载日历待办标记失败', e);
        }
    };

    async function loadCalendarDayTodos() {
        const dateKey = window.selectedCalendarDate;
        const list = document.getElementById('dayTodoList');
        if (!dateKey || !list) return;
        try {
            const todos = await todayApi(`/todos?todo_date=${dateKey}`);
            if (!todos.length) {
                list.innerHTML = '<p style="color:#999;font-size:0.85rem;">这一天还没有待办</p>';
                return;
            }
            const today = beijingTodayKey();
            const isPast = compareDateKey(dateKey, today) < 0;
            list.innerHTML = todos.map((t) => {
                const html = renderTodoItem(t);
                return isPast ? html.replace('class="todo-item', 'class="todo-item past-readonly') : html;
            }).join('');
        } catch (e) {
            list.innerHTML = '<p style="color:#c53030;font-size:0.85rem;">加载该日待办失败</p>';
        }
    }

    window.openCalendarDayTodos = async function (dateKey) {
        window.selectedCalendarDate = dateKey;
        const panel = document.getElementById('dayTodoPanel');
        const title = document.getElementById('dayTodoPanelTitle');
        const addRow = document.getElementById('dayTodoAddRow');
        const hint = document.getElementById('dayTodoHint');
        if (!panel) return;

        document.querySelectorAll('.calendar-day[data-date]').forEach((el) => {
            el.classList.toggle('selected', el.dataset.date === dateKey);
        });

        const today = beijingTodayKey();
        const cmp = compareDateKey(dateKey, today);
        if (title) title.textContent = formatDateKeyLabel(dateKey);
        panel.hidden = false;

        if (addRow) addRow.hidden = cmp < 0;
        if (hint) {
            if (cmp < 0) hint.textContent = '过去的日期仅可查看当时待办状态。';
            else if (cmp === 0) hint.textContent = '这是今天。上方列表只看这一天；下方「今日待办」始终显示今天。';
            else hint.textContent = '可以为这一天提前添加待办，不会混入今日待办。';
        }

        await loadCalendarDayTodos();
    };

    window.closeCalendarDayTodos = function () {
        window.selectedCalendarDate = null;
        const panel = document.getElementById('dayTodoPanel');
        if (panel) panel.hidden = true;
        document.querySelectorAll('.calendar-day.selected').forEach((el) => el.classList.remove('selected'));
    };

    window.addCalendarDayTodo = async function () {
        const dateKey = window.selectedCalendarDate;
        const input = document.getElementById('dayTodoInput');
        const text = input?.value?.trim();
        if (!dateKey || !text) return;
        const today = beijingTodayKey();
        if (compareDateKey(dateKey, today) < 0) {
            showMessage('过去的日期不能再添加待办', 'error');
            return;
        }
        try {
            const payload = { text, todo_date: dateKey };
            const remindTime = readRemindTime('dayTodoRemindTime');
            if (remindTime) payload.remind_time = remindTime;
            await todayApi('/todos', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            input.value = '';
            const timeInput = document.getElementById('dayTodoRemindTime');
            if (timeInput) timeInput.value = '';
            await refreshTodosAfterChange();
        } catch (e) {
            const detail = typeof humanizeApiError === 'function' ? humanizeApiError(e) : (e && e.message ? e.message : '请稍后重试');
            showMessage('添加待办失败: ' + detail, 'error');
        }
    };

    window.initializeTodayStats = function () {
        loadTodayDashboard();
    };
    window.initializeTodos = function () {
        const input = document.getElementById('newTodoInput');
        if (input && !input.dataset.bound) {
            input.dataset.bound = '1';
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') addDailyTodo();
            });
        }
        const dayInput = document.getElementById('dayTodoInput');
        if (dayInput && !dayInput.dataset.bound) {
            dayInput.dataset.bound = '1';
            dayInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') addCalendarDayTodo();
            });
        }
        const addBtn = document.getElementById('dayTodoAddBtn');
        if (addBtn && !addBtn.dataset.bound) {
            addBtn.dataset.bound = '1';
            addBtn.addEventListener('click', () => addCalendarDayTodo());
        }
        const closeBtn = document.getElementById('dayTodoPanelClose');
        if (closeBtn && !closeBtn.dataset.bound) {
            closeBtn.dataset.bound = '1';
            closeBtn.addEventListener('click', () => closeCalendarDayTodos());
        }
    };

    const TODAY_REFRESH_MS = 2 * 60 * 1000; // 每 2 分钟自动刷新今日概况

    function startTodayAutoRefresh() {
        if (window._todayDashboardRefreshTimer) {
            clearInterval(window._todayDashboardRefreshTimer);
        }
        window._todayDashboardRefreshTimer = setInterval(() => {
            if (!localStorage.getItem('authToken')) return;
            loadTodayDashboard();
        }, TODAY_REFRESH_MS);
    }

    window.addEventListener('selftalk-playback-logged', () => {
        loadTodayDashboard();
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && localStorage.getItem('authToken')) {
            loadTodayDashboard();
        }
    });

    function tryLoadTodayDashboard() {
        if (!localStorage.getItem('authToken')) return;
        loadTodayDashboard();
    }

    document.addEventListener('DOMContentLoaded', () => {
        initializeTodos();
        if (window.authCheckSettled) {
            tryLoadTodayDashboard();
        } else {
            window.addEventListener('auth-check-settled', tryLoadTodayDashboard, { once: true });
        }
    });
})();
