/**
 * 今日待办 & 今日概览（登录后从 API 加载）
 */
(function () {
    let todayOverviewData = null;
    let expandedPanel = null;
    let readingAdjustEntryId = null;
    let pendingReadingMinutes = null;
    let readingSaveTimer = null;
    let readingSaving = false;
    let readingWheelBound = false;

    function formatMinutes(mins) {
        const m = Math.max(0, parseInt(mins, 10) || 0);
        if (m < 60) return `${m}分钟`;
        const h = Math.floor(m / 60);
        const r = m % 60;
        return r ? `${h}小时${r}分` : `${h}小时`;
    }

    function formatDurationSeconds(sec) {
        const s = Math.max(0, parseInt(sec, 10) || 0);
        if (s < 60) return `${s}秒`;
        const m = Math.floor(s / 60);
        const r = s % 60;
        if (m < 60) return r ? `${m}分${r}秒` : `${m}分钟`;
        const h = Math.floor(m / 60);
        const rm = m % 60;
        return rm ? `${h}小时${rm}分` : `${h}小时`;
    }

    function loopModeLabel(mode) {
        if (mode === 'count') return '按次数';
        if (mode === 'time') return '按时长';
        return '单次';
    }

    function escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function todayApi(path, options = {}) {
        if (typeof apiRequest !== 'function') {
            throw new Error('请先登录');
        }
        return apiRequest(`/api/today${path}`, options);
    }

    window.loadTodayDashboard = async function loadTodayDashboard() {
        const token = localStorage.getItem('authToken');
        if (!token) {
            const hint = document.getElementById('todayOverviewHint');
            if (hint) hint.textContent = '登录后查看今日数据';
            renderDailyTodos([]);
            return;
        }
        try {
            todayOverviewData = await todayApi('/overview');
            renderTodayOverview(todayOverviewData);
            renderDailyTodos(todayOverviewData.todos || []);
            await loadReadingReminderSettings();
            if (window.reminderNotificationService) {
                window.reminderNotificationService.syncNativeTodos();
            }
            const hint = document.getElementById('todayOverviewHint');
            if (hint) hint.textContent = `数据已更新 · ${todayOverviewData.date}`;
            startTodayAutoRefresh();
        } catch (e) {
            console.error('加载今日概览失败', e);
            const hint = document.getElementById('todayOverviewHint');
            if (hint) hint.textContent = '加载失败，请刷新页面';
        }
    };

    function currentReadingMinutes() {
        if (pendingReadingMinutes != null) return pendingReadingMinutes;
        return todayOverviewData?.reading_total_minutes || 0;
    }

    function paintReadingMinutes(total) {
        const rt = document.getElementById('todayReadingTime');
        const rpb = document.getElementById('readingProgressBar');
        const goal = todayOverviewData?.reading_goal_minutes || 120;
        if (rt) rt.textContent = formatMinutes(total);
        if (rpb) rpb.style.width = `${Math.min(100, Math.round((total / Math.max(goal, 1)) * 100))}%`;
    }

    function renderTodayOverview(data) {
        const ca = document.getElementById('completedActions');
        const pc = document.getElementById('practiceCount');
        const apb = document.getElementById('actionsProgressBar');
        const ppb = document.getElementById('practiceProgressBar');
        const stSummary = document.getElementById('selfTalkPlaySummary');
        const stpb = document.getElementById('selfTalkProgressBar');
        const stCount = data.self_talk_play_count || 0;
        const stSeconds = data.self_talk_play_seconds || 0;

        paintReadingMinutes(currentReadingMinutes());
        if (ca) ca.textContent = `${data.actions_completed}/${data.actions_total}`;
        if (pc) pc.textContent = `${data.practice_count}次`;
        if (stSummary) {
            stSummary.textContent = stCount
                ? `${stCount}次 · ${formatDurationSeconds(stSeconds)}`
                : '0次';
        }
        if (apb) {
            const pct = data.actions_total ? (data.actions_completed / data.actions_total) * 100 : 0;
            apb.style.width = `${Math.min(100, Math.round(pct))}%`;
        }
        if (ppb) ppb.style.width = `${Math.min(100, data.practice_count * 10)}%`;
        if (stpb) stpb.style.width = `${Math.min(100, Math.round(stSeconds / 60))}%`;

        if (pendingReadingMinutes == null) {
            readingAdjustEntryId = data.reading_entries?.[0]?.id || null;
        }
        renderOverviewPanels(data);
        setupReadingAdjustControls();
    }

    function renderOverviewPanels(data) {
        const rp = document.getElementById('readingPanel');
        const ap = document.getElementById('actionsPanel');
        const pp = document.getElementById('practicePanel');
        const stp = document.getElementById('selfTalkPanel');

        if (rp) {
            const entries = data.reading_entries || [];
            rp.innerHTML = entries.length
                ? entries.map((e) => `
                    <div class="overview-panel-item">
                        <h5>${escapeHtml(e.book_title || '阅读记录')} · ${formatMinutes(e.duration_minutes)}</h5>
                        <p><strong>内容：</strong>${escapeHtml(e.content)}</p>
                        ${e.reflection ? `<p><strong>笔记/感悟：</strong>${escapeHtml(e.reflection)}</p>` : ''}
                        <button type="button" class="todo-btn" onclick="openReadingNoteForm(${e.id})">编辑</button>
                    </div>`).join('')
                : '<p style="color:#999;font-size:0.85rem;">暂无阅读记录，可在「上传笔记」中添加，或滚轮调整时长后自动创建。</p>';
            rp.innerHTML += `<p style="margin-top:8px;"><button type="button" class="todo-add-btn" onclick="openReadingNoteForm()">＋ 添加阅读内容与笔记</button></p>`;
        }

        if (ap) {
            const items = (data.action_items || []).filter((a) => a.status !== 'done');
            ap.innerHTML = items.length
                ? items.map((a) => `
                    <div class="overview-panel-item">
                        <h5>${escapeHtml(a.book_title)} · ${a.practiced_today ? '今日已记录' : '待实践'}</h5>
                        <p><strong>行动：</strong>${escapeHtml(a.action_text)}</p>
                        ${a.practiced_today
                            ? ''
                            : `<p style="margin-top:8px;"><button type="button" class="todo-btn" onclick="showPracticeModal(${a.id})">记录实践</button></p>`}
                    </div>`).join('')
                : '<p style="color:#999;font-size:0.85rem;">暂无行动项，可先添加一条。</p>';
            ap.innerHTML += `<p style="margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;">
                <button type="button" class="todo-add-btn" onclick="recordTodayPractice()">记录今日实践</button>
                <button type="button" class="todo-btn" onclick="addAction()">＋ 添加行动项</button>
                <button type="button" class="todo-btn" onclick="navigateTo('actions')">查看全部</button>
            </p>`;
        }

        if (pp) {
            const items = data.practice_items || [];
            pp.innerHTML = items.length
                ? items.map((p) => `
                    <div class="overview-panel-item">
                        <h5>${escapeHtml(p.book_title)} · ${escapeHtml(p.result)}</h5>
                        <p><strong>行动：</strong>${escapeHtml(p.action_text)}</p>
                        ${p.notes ? `<p><strong>反馈：</strong>${escapeHtml(p.notes)}</p>` : ''}
                    </div>`).join('')
                : '<p style="color:#999;font-size:0.85rem;">今日暂无实践记录。</p>';
        }

        if (stp) {
            const items = data.self_talk_play_items || [];
            stp.innerHTML = items.length
                ? items.map((item) => `
                    <div class="overview-panel-item">
                        <h5>Self-talk #${item.self_talk_id} · ${loopModeLabel(item.loop_mode)}</h5>
                        <p><strong>收听：</strong>${formatDurationSeconds(item.duration_seconds)} · ${item.loops_completed} 遍</p>
                        ${item.transcript_preview ? `<p><strong>内容：</strong>${escapeHtml(item.transcript_preview)}</p>` : ''}
                    </div>`).join('')
                : '<p style="color:#999;font-size:0.85rem;">今日暂无 Self-talk 播放记录，在 Self-talk 页面播放后会自动统计。</p>';
            stp.innerHTML += `<p style="margin-top:8px;"><button type="button" class="todo-btn" onclick="recordSelfTalk()">前往 Self-talk</button></p>`;
        }
    }

    window.toggleOverviewPanel = function (name) {
        if (name === 'selftalk' && localStorage.getItem('authToken')) {
            loadTodayDashboard();
        }
        const map = {
            reading: 'readingPanel',
            actions: 'actionsPanel',
            practice: 'practicePanel',
            selftalk: 'selfTalkPanel',
        };
        const statMap = {
            reading: 'readingStatItem',
            actions: 'actionsStatItem',
            practice: 'practiceStatItem',
            selftalk: 'selfTalkStatItem',
        };
        const id = map[name];
        if (!id) return;
        const panel = document.getElementById(id);
        const stat = document.getElementById(statMap[name]);
        if (!panel) return;

        if (expandedPanel === name) {
            panel.classList.add('hidden');
            stat?.classList.remove('expanded');
            expandedPanel = null;
            return;
        }
        ['readingPanel', 'actionsPanel', 'practicePanel', 'selfTalkPanel'].forEach((pid) => {
            document.getElementById(pid)?.classList.add('hidden');
        });
        ['readingStatItem', 'actionsStatItem', 'practiceStatItem', 'selfTalkStatItem'].forEach((sid) => {
            document.getElementById(sid)?.classList.remove('expanded');
        });
        panel.classList.remove('hidden');
        stat?.classList.add('expanded');
        expandedPanel = name;
    };

    function setupReadingAdjustControls() {
        const el = document.getElementById('readingStatItem');
        if (el && !el.dataset.keyBound) {
            el.dataset.keyBound = '1';
            el.setAttribute('tabindex', '0');
            el.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
                    e.preventDefault();
                    applyReadingDelta(5);
                } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
                    e.preventDefault();
                    applyReadingDelta(-5);
                }
            });
            el.querySelectorAll('.duration-step').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    applyReadingDelta(parseInt(btn.dataset.delta, 10) || 0);
                });
            });
        }

        if (readingWheelBound) return;
        readingWheelBound = true;
        document.addEventListener('wheel', onReadingWheel, { passive: false, capture: true });
    }

    function onReadingWheel(e) {
        if (e.ctrlKey || e.deltaY === 0) return;
        const el = document.getElementById('readingStatItem');
        if (!el || !el.contains(e.target)) return;
        e.preventDefault();
        e.stopPropagation();
        const delta = e.deltaY < 0 ? 5 : -5;
        applyReadingDelta(delta);
    }

    function applyReadingDelta(delta) {
        if (!delta) return;
        if (!localStorage.getItem('authToken')) {
            if (typeof showMessage === 'function') showMessage('请先登录后再调整时长', 'error');
            return;
        }
        const current = currentReadingMinutes();
        const next = Math.max(0, Math.min(24 * 60, current + delta));
        if (next === current) return;
        pendingReadingMinutes = next;
        paintReadingMinutes(next);
        scheduleSaveReadingMinutes();
    }

    function scheduleSaveReadingMinutes() {
        clearTimeout(readingSaveTimer);
        readingSaveTimer = setTimeout(() => {
            persistReadingMinutes();
        }, 280);
    }

    async function persistReadingMinutes() {
        if (readingSaving) {
            scheduleSaveReadingMinutes();
            return;
        }
        if (pendingReadingMinutes == null) return;
        if (!localStorage.getItem('authToken')) return;

        readingSaving = true;
        const target = pendingReadingMinutes;
        try {
            if (!todayOverviewData) {
                todayOverviewData = await todayApi('/overview');
            }
            const entries = todayOverviewData.reading_entries || [];
            const entry = entries.find((e) => e.id === readingAdjustEntryId) || entries[0];
            const currentTotal = todayOverviewData.reading_total_minutes || 0;

            if (entry) {
                const othersSum = Math.max(0, currentTotal - (entry.duration_minutes || 0));
                const newDur = Math.max(0, target - othersSum);
                await todayApi(`/reading-entries/${entry.id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ duration_minutes: newDur }),
                });
                entry.duration_minutes = newDur;
                readingAdjustEntryId = entry.id;
                todayOverviewData.reading_total_minutes = othersSum + newDur;
            } else {
                const created = await todayApi('/reading-entries', {
                    method: 'POST',
                    body: JSON.stringify({
                        book_title: '今日阅读',
                        content: '（点击展开可填写阅读内容）',
                        duration_minutes: target,
                    }),
                });
                readingAdjustEntryId = created.id;
                todayOverviewData.reading_entries = [created, ...entries];
                todayOverviewData.reading_total_minutes = target;
            }

            if (pendingReadingMinutes === target) {
                pendingReadingMinutes = null;
                await loadTodayDashboard();
            }
        } catch (err) {
            console.error(err);
            pendingReadingMinutes = null;
            if (typeof showMessage === 'function') showMessage('更新阅读时长失败', 'error');
            if (todayOverviewData) paintReadingMinutes(todayOverviewData.reading_total_minutes || 0);
        } finally {
            readingSaving = false;
            if (pendingReadingMinutes != null && pendingReadingMinutes !== target) {
                scheduleSaveReadingMinutes();
            }
        }
    }

    window.openReadingNoteForm = function (entryId) {
        if (typeof navigateTo === 'function') navigateTo('upload');
        if (typeof switchUploadTab === 'function') switchUploadTab('reading');
        if (entryId && todayOverviewData?.reading_entries) {
            const e = todayOverviewData.reading_entries.find((x) => x.id === entryId);
            if (e) fillReadingForm(e);
        }
    };

    function fillReadingForm(e) {
        const book = document.getElementById('readingBookTitle');
        const content = document.getElementById('readingContent');
        const reflection = document.getElementById('readingReflection');
        const duration = document.getElementById('readingDuration');
        const hid = document.getElementById('readingEntryId');
        if (book) book.value = e.book_title || '';
        if (content) content.value = e.content || '';
        if (reflection) reflection.value = e.reflection || '';
        if (duration) duration.value = e.duration_minutes || 0;
        if (hid) hid.value = e.id;
    }

    window.saveReadingEntry = async function () {
        const id = document.getElementById('readingEntryId')?.value;
        const body = {
            book_title: document.getElementById('readingBookTitle')?.value?.trim() || null,
            content: document.getElementById('readingContent')?.value?.trim(),
            reflection: document.getElementById('readingReflection')?.value?.trim() || null,
            duration_minutes: parseInt(document.getElementById('readingDuration')?.value, 10) || 0,
        };
        if (!body.content) {
            showMessage('请填写阅读内容', 'error');
            return;
        }
        try {
            if (id) {
                await todayApi(`/reading-entries/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
            } else {
                await todayApi('/reading-entries', { method: 'POST', body: JSON.stringify(body) });
            }
            showMessage('阅读记录已保存', 'success');
            document.getElementById('readingEntryId').value = '';
            await loadTodayDashboard();
        } catch (e) {
            showMessage('保存失败', 'error');
        }
    };

    window.createManualAction = async function () {
        const book = document.getElementById('manualBookTitle')?.value?.trim();
        const action = document.getElementById('manualActionText')?.value?.trim();
        const excerpt = document.getElementById('manualSourceExcerpt')?.value?.trim() || action;
        if (!book || !action) {
            showMessage('请填写书名和行动内容', 'error');
            return;
        }
        try {
            await apiRequest('/api/actions/', {
                method: 'POST',
                body: JSON.stringify({
                    book_title: book,
                    action_text: action,
                    source_excerpt: excerpt,
                    tags: [],
                }),
            });
            showMessage('行动项已添加', 'success');
            document.getElementById('manualBookTitle').value = '';
            document.getElementById('manualActionText').value = '';
            document.getElementById('manualSourceExcerpt').value = '';
            if (typeof loadActions === 'function') loadActions();
            await loadTodayDashboard();
        } catch (e) {
            showMessage('添加失败: ' + (e.message || ''), 'error');
        }
    };

    window.switchUploadTab = function (tab) {
        document.querySelectorAll('.upload-tab').forEach((t) => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });
        document.querySelectorAll('.upload-panel').forEach((p) => {
            p.classList.toggle('hidden', p.dataset.panel !== tab);
        });
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
        try {
            await todayApi('/todos', {
                method: 'POST',
                body: JSON.stringify({ text, remind_time: readRemindTime('newTodoRemindTime') }),
            });
            input.value = '';
            const timeInput = document.getElementById('newTodoRemindTime');
            if (timeInput) timeInput.value = '';
            await refreshTodosAfterChange();
        } catch (e) {
            showMessage('添加待办失败', 'error');
        }
    };

    window.setTodoRemindTime = async function (id) {
        const item = document.querySelector(`[data-todo-id="${id}"]`);
        const current = item?.querySelector('.todo-remind-badge')?.textContent?.replace(/[^\d:]/g, '') || '';
        const next = window.prompt('设置提醒时间（HH:MM，留空则取消）', current);
        if (next === null) return;
        const remindTime = next.trim();
        if (remindTime && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(remindTime)) {
            showMessage('时间格式应为 HH:MM', 'error');
            return;
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
        if (!confirm('确定删除这条待办？')) return;
        try {
            await todayApi(`/todos/${id}`, { method: 'DELETE' });
            await refreshTodosAfterChange();
        } catch (e) {
            showMessage('删除失败', 'error');
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

    async function loadReadingReminderSettings() {
        const enabledEl = document.getElementById('readingReminderSwitch');
        const timeEl = document.getElementById('readingReminderTime');
        if (!enabledEl || !timeEl || typeof apiRequest !== 'function') return;
        try {
            const settings = await apiRequest('/api/self_talk_reminders/settings');
            enabledEl.checked = !!settings.reading_reminder_enabled;
            if (settings.reading_reminder_time) {
                timeEl.value = String(settings.reading_reminder_time).slice(0, 5);
            } else if (!timeEl.value) {
                timeEl.value = '21:00';
            }
            timeEl.disabled = !enabledEl.checked;
        } catch (e) {
            console.warn('加载阅读提醒失败', e);
        }
    }

    async function saveReadingReminderSettings() {
        const enabledEl = document.getElementById('readingReminderSwitch');
        const timeEl = document.getElementById('readingReminderTime');
        if (!enabledEl || !timeEl || typeof apiRequest !== 'function') return;
        const enabled = enabledEl.checked;
        const time = (timeEl.value || '21:00').slice(0, 5);
        timeEl.disabled = !enabled;
        try {
            await apiRequest('/api/self_talk_reminders/settings', {
                method: 'PATCH',
                body: JSON.stringify({
                    reading_reminder_enabled: enabled,
                    reading_reminder_time: time,
                }),
            });
            if (window.reminderNotificationService) {
                window.reminderNotificationService.syncNativeSchedule();
            }
        } catch (e) {
            showMessage('保存阅读提醒失败', 'error');
        }
    }

    window.saveReadingReminderSettings = saveReadingReminderSettings;

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
            await todayApi('/todos', {
                method: 'POST',
                body: JSON.stringify({
                    text,
                    todo_date: dateKey,
                    remind_time: readRemindTime('dayTodoRemindTime'),
                }),
            });
            input.value = '';
            const timeInput = document.getElementById('dayTodoRemindTime');
            if (timeInput) timeInput.value = '';
            await refreshTodosAfterChange();
        } catch (e) {
            showMessage('添加待办失败', 'error');
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
        const readingSwitch = document.getElementById('readingReminderSwitch');
        const readingTime = document.getElementById('readingReminderTime');
        if (readingSwitch && !readingSwitch.dataset.bound) {
            readingSwitch.dataset.bound = '1';
            readingSwitch.addEventListener('change', () => saveReadingReminderSettings());
        }
        if (readingTime && !readingTime.dataset.bound) {
            readingTime.dataset.bound = '1';
            readingTime.addEventListener('change', () => saveReadingReminderSettings());
        }
    };

    const TODAY_REFRESH_MS = 2 * 60 * 1000; // 每 2 分钟自动刷新今日概况

    function startTodayAutoRefresh() {
        if (window._todayDashboardRefreshTimer) {
            clearInterval(window._todayDashboardRefreshTimer);
        }
        window._todayDashboardRefreshTimer = setInterval(() => {
            if (!localStorage.getItem('authToken')) return;
            if (pendingReadingMinutes != null || readingSaving) return;
            loadTodayDashboard();
        }, TODAY_REFRESH_MS);
    }

    window.addEventListener('selftalk-playback-logged', () => {
        loadTodayDashboard();
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && localStorage.getItem('authToken')) {
            if (pendingReadingMinutes != null || readingSaving) return;
            loadTodayDashboard();
        }
    });

    function tryLoadTodayDashboard() {
        if (!localStorage.getItem('authToken')) return;
        loadTodayDashboard();
    }

    document.addEventListener('DOMContentLoaded', () => {
        initializeTodos();
        setupReadingAdjustControls();
        if (window.authCheckSettled) {
            tryLoadTodayDashboard();
        } else {
            window.addEventListener('auth-check-settled', tryLoadTodayDashboard, { once: true });
        }
    });
    setupReadingAdjustControls();
})();
