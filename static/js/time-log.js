/**
 * 时间日志：点击节点记下此刻，再写上一段做了什么。
 */
(function () {
    let day = null;
    let data = { date: null, total_seconds: 0, nodes: [] };
    let tasks = [];
    let pendingNode = null;
    let compact = false;

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

    function formatClock(iso) {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return '--:--';
        return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    }

    function formatDuration(sec) {
        const s = Math.max(0, parseInt(sec, 10) || 0);
        if (s < 60) return `${s} 秒`;
        const m = Math.floor(s / 60);
        const r = s % 60;
        if (m < 60) return r ? `${m} 分 ${r} 秒` : `${m} 分钟`;
        const h = Math.floor(m / 60);
        const rm = m % 60;
        return rm ? `${h} 小时 ${rm} 分` : `${h} 小时`;
    }

    function flattenTasks(nodes, acc) {
        (nodes || []).forEach((task) => {
            acc.push(task);
            flattenTasks(task.children || [], acc);
        });
        return acc;
    }

    async function logApi(path, options) {
        if (typeof apiRequest !== 'function') throw new Error('请先登录');
        return apiRequest(`/api/time-log${path}`, options || {});
    }

    function currentDay() {
        return day || todayISO();
    }

    function taskText(taskId) {
        const task = tasks.find((t) => t.id === taskId);
        return task ? task.text : '';
    }

    function renderList() {
        const list = document.getElementById('timeLogList');
        const total = document.getElementById('timeLogTotal');
        const label = document.getElementById('timeLogDateLabel');
        if (label) label.textContent = currentDay();
        if (total) {
            total.textContent = data.nodes?.length
                ? `已记录 ${formatDuration(data.total_seconds)}`
                : '今天还没有时间节点';
        }
        if (!list) return;
        if (!(data.nodes || []).length) {
            list.innerHTML = '<p class="flow-empty">点右下角「记」，先落下一个时间点。</p>';
            return;
        }
        list.innerHTML = data.nodes.map((node, index) => {
            const title = index === 0 && !node.label
                ? '开始'
                : (node.label || '未写下这段在做什么');
            const related = node.task_id ? taskText(node.task_id) : '';
            return `
                <article class="tl-node" data-node-id="${node.id}">
                    <div>
                        <div class="tl-time">${escapeHtml(formatClock(node.logged_at))}</div>
                        <div class="tl-duration">${index === 0 ? '起点' : escapeHtml(formatDuration(node.duration_seconds))}</div>
                    </div>
                    <div class="tl-label">
                        <div>${escapeHtml(title)}</div>
                        ${related ? `<div class="tl-duration">${escapeHtml(related)}</div>` : ''}
                    </div>
                    <button type="button" class="flow-mini-btn" data-act="edit">改</button>
                </article>
            `;
        }).join('');
    }

    async function loadTasks() {
        if (typeof apiRequest !== 'function') {
            tasks = [];
            return;
        }
        try {
            const schedule = await apiRequest(`/api/schedule?task_date=${encodeURIComponent(currentDay())}`);
            tasks = flattenTasks(schedule.tasks || [], []);
        } catch (e) {
            tasks = [];
        }
    }

    async function load(nextDay) {
        const token = localStorage.getItem('authToken');
        day = nextDay || currentDay();
        if (!token) {
            data = { date: day, total_seconds: 0, nodes: [] };
            renderList();
            return;
        }
        data = await logApi(`?log_date=${encodeURIComponent(day)}`);
        await loadTasks();
        renderList();
        syncOverlaySwitch();
    }

    function closeSheet() {
        document.getElementById('timeLogSheet')?.remove();
        document.getElementById('timeLogSheetBackdrop')?.remove();
        pendingNode = null;
    }

    function openSheet(node, isStart) {
        closeSheet();
        pendingNode = node;
        const backdrop = document.createElement('div');
        backdrop.id = 'timeLogSheetBackdrop';
        backdrop.className = 'tl-sheet-backdrop';
        const sheet = document.createElement('div');
        sheet.id = 'timeLogSheet';
        sheet.className = 'tl-sheet';
        const picks = tasks.map((task) => (
            `<button type="button" class="flow-chip${node.task_id === task.id ? ' active' : ''}" data-task-id="${task.id}">${escapeHtml(task.text)}</button>`
        )).join('');
        sheet.innerHTML = `
            <h3>${isStart ? '记下开始' : '这段在做什么'}</h3>
            <p>${isStart ? '今天的第一个节点。也可以写一句此刻在做什么。' : `距上一个节点 ${formatDuration(node.duration_seconds)}`}</p>
            <textarea id="timeLogSheetInput" maxlength="500" placeholder="分类昆虫学：鉴定袋蛾">${escapeHtml(node.label || '')}</textarea>
            ${picks ? `<div class="tl-task-picks">${picks}</div>` : ''}
            <div class="tl-sheet-actions">
                <button type="button" class="flow-ghost-btn" id="timeLogSheetCancel">稍后</button>
                <button type="button" class="flow-solid-btn" id="timeLogSheetSave">写下</button>
            </div>
        `;
        document.body.appendChild(backdrop);
        document.body.appendChild(sheet);
        backdrop.addEventListener('click', closeSheet);
        sheet.querySelector('#timeLogSheetCancel').addEventListener('click', closeSheet);
        sheet.querySelectorAll('[data-task-id]').forEach((btn) => {
            btn.addEventListener('click', () => {
                sheet.querySelectorAll('[data-task-id]').forEach((el) => el.classList.remove('active'));
                btn.classList.toggle('active');
                const input = sheet.querySelector('#timeLogSheetInput');
                if (input && !input.value.trim()) input.value = btn.textContent || '';
            });
        });
        sheet.querySelector('#timeLogSheetSave').addEventListener('click', async () => {
            const input = sheet.querySelector('#timeLogSheetInput');
            const picked = sheet.querySelector('[data-task-id].active');
            try {
                await logApi(`/nodes/${node.id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({
                        label: input?.value || '',
                        task_id: picked ? parseInt(picked.dataset.taskId, 10) : undefined,
                        clear_task: !picked,
                    }),
                });
                closeSheet();
                await load(currentDay());
            } catch (e) {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            }
        });
        sheet.querySelector('#timeLogSheetInput')?.focus();
    }

    async function punch(forSelectedDay) {
        const token = localStorage.getItem('authToken');
        if (!token) {
            if (typeof showMessage === 'function') showMessage('请先登录', 'error');
            return;
        }
        const punchDay = forSelectedDay ? currentDay() : todayISO();
        try {
            const node = await logApi('/nodes', {
                method: 'POST',
                body: JSON.stringify({ log_date: punchDay }),
            });
            day = punchDay;
            await load(punchDay);
            openSheet(node, !node.duration_seconds && (data.nodes || []).length <= 1);
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
    }

    function ensureFab() {
        if (compact) return;
        if (document.getElementById('timeLogFab')) return;
        const btn = document.createElement('button');
        btn.id = 'timeLogFab';
        btn.className = 'tl-fab';
        btn.type = 'button';
        btn.textContent = '记';
        btn.title = '记下时间节点';
        btn.addEventListener('click', () => punch(false));
        document.body.appendChild(btn);
    }

    function native() {
        return window.ShuranNative || null;
    }

    function syncOverlaySwitch() {
        const row = document.getElementById('timeLogOverlayRow');
        const sw = document.getElementById('timeLogOverlaySwitch');
        const hint = document.getElementById('timeLogOverlayHint');
        const n = native();
        if (!row) return;
        const show = !!(n && typeof n.hasOverlayPermission === 'function');
        row.hidden = !show;
        if (!show || !sw) return;
        try {
            sw.checked = !!n.isTimeLogOverlayEnabled();
        } catch (e) {
            sw.checked = false;
        }
        if (hint) {
            let allowed = true;
            try {
                allowed = !!n.hasOverlayPermission();
            } catch (e) {
                allowed = true;
            }
            hint.textContent = allowed
                ? '打开后，离开书然也能点悬浮按钮记下时间。'
                : '需要先允许「显示在其他应用上层」。';
        }
    }

    async function applyOverlay(enabled) {
        const n = native();
        if (!n) return;
        try {
            if (enabled && n.hasOverlayPermission && !n.hasOverlayPermission()) {
                n.requestOverlayPermission();
            }
            if (typeof n.setTimeLogOverlayEnabled === 'function') {
                n.setTimeLogOverlayEnabled(!!enabled);
            }
        } catch (e) {
            if (typeof showMessage === 'function') showMessage('无法打开悬浮窗', 'error');
        }
        setTimeout(syncOverlaySwitch, 400);
    }

    function openCompactWindow() {
        const url = '/static/time-log-compact.html';
        window.open(url, 'shuran-timelog', 'width=400,height=620,resizable=yes,scrollbars=yes');
    }

    window.syncTimeLogChrome = function syncTimeLogChrome() {
        ensureFab();
        const fab = document.getElementById('timeLogFab');
        if (fab) fab.hidden = !localStorage.getItem('authToken');
        syncOverlaySwitch();
    };

    window.loadTimeLog = function loadTimeLog() {
        return load(currentDay()).catch((e) => {
            const total = document.getElementById('timeLogTotal');
            if (total) total.textContent = e.message || '加载失败';
        });
    };

    window.punchTimeLog = punch;

    window.closeTimeLogSheet = closeSheet;

    function onReady() {
        compact = document.body.classList.contains('tl-compact-page');
        window.syncTimeLogChrome();

        document.getElementById('timeLogPrevDay')?.addEventListener('click', () => {
            load(shiftDay(currentDay(), -1));
        });
        document.getElementById('timeLogNextDay')?.addEventListener('click', () => {
            load(shiftDay(currentDay(), 1));
        });
        document.getElementById('timeLogPunchBtn')?.addEventListener('click', () => punch(true));
        document.getElementById('timeLogCompactBtn')?.addEventListener('click', openCompactWindow);
        document.getElementById('timeLogOverlaySwitch')?.addEventListener('change', (e) => {
            applyOverlay(e.target.checked);
        });
        document.getElementById('timeLogList')?.addEventListener('click', (e) => {
            if (e.target.dataset.act !== 'edit') return;
            const article = e.target.closest('[data-node-id]');
            if (!article) return;
            const id = parseInt(article.dataset.nodeId, 10);
            const node = (data.nodes || []).find((n) => n.id === id);
            if (node) openSheet(node, !node.duration_seconds && data.nodes[0]?.id === id);
        });

        const originalHandle = window.handleAppBack;
        if (typeof originalHandle === 'function') {
            window.handleAppBack = function () {
                if (document.getElementById('timeLogSheet')) {
                    closeSheet();
                    return 'consumed';
                }
                return originalHandle();
            };
        }

        if (document.getElementById('time-log') || compact) {
            load(currentDay()).catch(() => {});
        }
        syncOverlaySwitch();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
