/**
 * 今日待办 & 今日概览（登录后从 API 加载）
 */
(function () {
    let todayOverviewData = null;
    let expandedPanel = null;
    let readingAdjustEntryId = null;

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
            const hint = document.getElementById('todayOverviewHint');
            if (hint) hint.textContent = `数据已更新 · ${todayOverviewData.date}`;
            startTodayAutoRefresh();
        } catch (e) {
            console.error('加载今日概览失败', e);
            const hint = document.getElementById('todayOverviewHint');
            if (hint) hint.textContent = '加载失败，请刷新页面';
        }
    };

    function renderTodayOverview(data) {
        const goal = data.reading_goal_minutes || 120;
        const total = data.reading_total_minutes || 0;
        const rt = document.getElementById('todayReadingTime');
        const ca = document.getElementById('completedActions');
        const pc = document.getElementById('practiceCount');
        const rpb = document.getElementById('readingProgressBar');
        const apb = document.getElementById('actionsProgressBar');
        const ppb = document.getElementById('practiceProgressBar');
        const stSummary = document.getElementById('selfTalkPlaySummary');
        const stpb = document.getElementById('selfTalkProgressBar');
        const stCount = data.self_talk_play_count || 0;
        const stSeconds = data.self_talk_play_seconds || 0;

        if (rt) rt.textContent = formatMinutes(total);
        if (ca) ca.textContent = `${data.actions_completed}/${data.actions_total}`;
        if (pc) pc.textContent = `${data.practice_count}次`;
        if (stSummary) {
            stSummary.textContent = stCount
                ? `${stCount}次 · ${formatDurationSeconds(stSeconds)}`
                : '0次';
        }
        if (rpb) rpb.style.width = `${Math.min(100, Math.round((total / goal) * 100))}%`;
        if (apb) {
            const pct = data.actions_total ? (data.actions_completed / data.actions_total) * 100 : 0;
            apb.style.width = `${Math.min(100, Math.round(pct))}%`;
        }
        if (ppb) ppb.style.width = `${Math.min(100, data.practice_count * 10)}%`;
        if (stpb) stpb.style.width = `${Math.min(100, Math.round(stSeconds / 60))}%`;

        readingAdjustEntryId = data.reading_entries?.[0]?.id || null;
        renderOverviewPanels(data);
        setupReadingWheel();
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
            const items = (data.action_items || []).filter((a) => a.practiced_today);
            ap.innerHTML = items.length
                ? items.map((a) => `
                    <div class="overview-panel-item">
                        <h5>${escapeHtml(a.book_title)} · ${a.status}</h5>
                        <p><strong>行动：</strong>${escapeHtml(a.action_text)}</p>
                        <p><strong>摘录：</strong>${escapeHtml(a.source_excerpt)}</p>
                    </div>`).join('')
                : '<p style="color:#999;font-size:0.85rem;">今日暂无实践记录的行动项。</p>';
            ap.innerHTML += `<p style="margin-top:8px;"><button type="button" class="todo-btn" onclick="navigateTo('actions')">查看全部行动项</button></p>`;
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

    function setupReadingWheel() {
        const el = document.getElementById('readingStatItem');
        if (!el || el.dataset.wheelBound) return;
        el.dataset.wheelBound = '1';
        el.addEventListener('wheel', async (e) => {
            e.preventDefault();
            const delta = e.deltaY < 0 ? 5 : -5;
            await adjustReadingMinutes(delta);
        }, { passive: false });
    }

    async function adjustReadingMinutes(delta) {
        if (!todayOverviewData) return;
        const entryId = readingAdjustEntryId;
        const entry = todayOverviewData.reading_entries?.find((e) => e.id === entryId);

        try {
            if (entry) {
                const newDur = Math.max(0, (entry.duration_minutes || 0) + delta);
                await todayApi(`/reading-entries/${entryId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ duration_minutes: newDur }),
                });
            } else {
                await todayApi('/reading-entries', {
                    method: 'POST',
                    body: JSON.stringify({
                        book_title: '今日阅读',
                        content: '（点击展开可填写阅读内容）',
                        duration_minutes: Math.max(0, delta),
                    }),
                });
            }
            await loadTodayDashboard();
        } catch (err) {
            console.error(err);
            if (typeof showMessage === 'function') showMessage('更新阅读时长失败', 'error');
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
        return `
            <div class="todo-item ${done ? 'completed' : ''}" data-todo-id="${t.id}">
                <span class="todo-text" ondblclick="editDailyTodo(${t.id})">${escapeHtml(t.text)}</span>
                <div class="todo-actions">
                    <button type="button" class="todo-btn edit" onclick="editDailyTodo(${t.id})" title="编辑">✎</button>
                    <button type="button" class="todo-check" onclick="toggleDailyTodo(${t.id}, ${!done})" title="${done ? '标为未完成' : '完成'}">${done ? '↩' : '✓'}</button>
                    <button type="button" class="todo-btn delete" onclick="deleteDailyTodo(${t.id})" title="删除">×</button>
                </div>
            </div>`;
    }

    window.addDailyTodo = async function () {
        const input = document.getElementById('newTodoInput');
        const text = input?.value?.trim();
        if (!text) return;
        try {
            await todayApi('/todos', { method: 'POST', body: JSON.stringify({ text }) });
            input.value = '';
            await loadTodayDashboard();
        } catch (e) {
            showMessage('添加待办失败', 'error');
        }
    };

    window.toggleDailyTodo = async function (id, completed) {
        try {
            await todayApi(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify({ completed }) });
            await loadTodayDashboard();
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
                await loadTodayDashboard();
            } catch (e) {
                showMessage('保存失败', 'error');
            }
        };
        input.addEventListener('blur', save, { once: true });
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') input.blur();
            if (ev.key === 'Escape') loadTodayDashboard();
        });
    };

    window.deleteDailyTodo = async function (id) {
        if (!confirm('确定删除这条待办？')) return;
        try {
            await todayApi(`/todos/${id}`, { method: 'DELETE' });
            await loadTodayDashboard();
        } catch (e) {
            showMessage('删除失败', 'error');
        }
    };

    // 替换旧的静态初始化
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
    };

    const TODAY_REFRESH_MS = 2 * 60 * 1000; // 每 2 分钟自动刷新今日概况

    function startTodayAutoRefresh() {
        if (window._todayDashboardRefreshTimer) {
            clearInterval(window._todayDashboardRefreshTimer);
        }
        window._todayDashboardRefreshTimer = setInterval(() => {
            if (localStorage.getItem('authToken')) loadTodayDashboard();
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
