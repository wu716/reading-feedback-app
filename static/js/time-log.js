/**
 * 时间日志：点击节点记下此刻，再写上一段做了什么。
 */
(function () {
    let day = null;
    let data = { date: null, total_seconds: 0, nodes: [] };
    let tasks = [];
    let pendingNode = null;
    let compact = document.body.classList.contains('tl-compact-page');

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
                : '今天还没有写下任何一段';
        }
        if (!list) return;
        if (!(data.nodes || []).length) {
            list.innerHTML = '<p class="flow-empty">点「记」会先抓住此刻。写下这段在做什么之后，才会出现在日志里。</p>';
            return;
        }
        list.innerHTML = data.nodes.map((node, index) => {
            const title = node.label || taskText(node.task_id) || '这段';
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

    function isUnwritten(node) {
        return !!(node && !(node.label || '').trim() && !node.task_id);
    }

    function closeSheet() {
        document.getElementById('timeLogSheet')?.remove();
        document.getElementById('timeLogSheetBackdrop')?.remove();
        pendingNode = null;
    }

    async function discardSheet() {
        const node = pendingNode;
        closeSheet();
        if (node && node.id && isUnwritten(node)) {
            try {
                await logApi(`/nodes/${node.id}`, { method: 'DELETE' });
            } catch (e) {
                /* 草稿未写入日志时删掉即可 */
            }
            try {
                await load(currentDay());
            } catch (e) {
                /* ignore */
            }
        }
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
            <p>${isStart ? '写下此刻在做什么，才会记入今天的日志。' : `距上一段 ${formatDuration(node.duration_seconds)}。写下之后才会记入日志。`}</p>
            <textarea id="timeLogSheetInput" maxlength="500" placeholder="分类昆虫学：鉴定袋蛾">${escapeHtml(node.label || '')}</textarea>
            ${picks ? `<div class="tl-task-picks">${picks}</div>` : ''}
            <div class="tl-sheet-actions">
                <button type="button" class="flow-ghost-btn" id="timeLogSheetCancel">稍后</button>
                <button type="button" class="flow-solid-btn" id="timeLogSheetSave">写下</button>
            </div>
        `;
        document.body.appendChild(backdrop);
        document.body.appendChild(sheet);
        placeDesktopSheet(sheet);
        backdrop.addEventListener('click', () => discardSheet());
        sheet.querySelector('#timeLogSheetCancel').addEventListener('click', () => discardSheet());
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
            const label = (input?.value || '').trim();
            const taskId = picked ? parseInt(picked.dataset.taskId, 10) : undefined;
            if (!label && !taskId) {
                await discardSheet();
                return;
            }
            try {
                if (node.id) {
                    await logApi(`/nodes/${node.id}`, {
                        method: 'PATCH',
                        body: JSON.stringify({
                            label,
                            task_id: taskId,
                            clear_task: !taskId,
                        }),
                    });
                } else {
                    await logApi('/nodes', {
                        method: 'POST',
                        body: JSON.stringify({
                            log_date: node.log_date || currentDay(),
                            logged_at: node.logged_at,
                            label,
                            task_id: taskId,
                        }),
                    });
                }
                closeSheet();
                await load(currentDay());
            } catch (e) {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            }
        });
        sheet.querySelector('#timeLogSheetInput')?.focus();
    }

    function isDesktopShell() {
        return window.matchMedia('(min-width: 769px)').matches;
    }

    function placeDesktopSheet(sheet) {
        if (!isDesktopShell() || compact) return;
        sheet.classList.add('tl-sheet-desktop');
        const width = Math.min(380, window.innerWidth - 24);
        requestAnimationFrame(() => {
            const height = Math.min(sheet.offsetHeight || 320, window.innerHeight - 24);
            const fab = document.getElementById('timeLogFab');
            const rect = fab && !fab.hidden ? fab.getBoundingClientRect() : null;
            let left = Math.max(12, (window.innerWidth - width) / 2);
            let top = Math.max(12, (window.innerHeight - height) / 2);
            if (rect) {
                const onLeft = rect.left < window.innerWidth / 2;
                left = onLeft
                    ? Math.min(window.innerWidth - width - 12, rect.right + 12)
                    : rect.left - width - 12;
                left = Math.max(12, left);
                top = Math.min(window.innerHeight - height - 12, Math.max(12, rect.top - 24));
            }
            sheet.style.width = `${width}px`;
            sheet.style.left = `${left}px`;
            sheet.style.top = `${top}px`;
            sheet.style.right = 'auto';
            sheet.style.bottom = 'auto';
            sheet.style.transform = 'none';
        });
    }

    const FAB_POS_KEY = 'shuran.fabDock';
    const BALL_SIZE = { width: 132, height: 148 };
    const COMPACT_SIZE = { width: 380, height: 560 };

    function readFabPos() {
        try {
            const raw = JSON.parse(localStorage.getItem(FAB_POS_KEY) || 'null');
            if (!raw || (raw.side !== 'left' && raw.side !== 'right')) {
                return { side: 'right', y: 0.62 };
            }
            const y = Number(raw.y);
            return { side: raw.side, y: Number.isFinite(y) ? Math.min(0.9, Math.max(0.12, y)) : 0.62 };
        } catch (e) {
            return { side: 'right', y: 0.62 };
        }
    }

    function saveFabPos(pos) {
        localStorage.setItem(FAB_POS_KEY, JSON.stringify(pos));
    }

    function applyFabDock(btn) {
        if (!btn) return;
        if (!isDesktopShell()) {
            btn.classList.remove('is-dock-left', 'is-dock-right', 'is-dragging');
            btn.style.left = '';
            btn.style.right = '';
            btn.style.top = '';
            btn.style.bottom = '';
            return;
        }
        const pos = readFabPos();
        const size = btn.offsetHeight || 48;
        const top = Math.round(window.innerHeight * pos.y - size / 2);
        btn.classList.toggle('is-dock-left', pos.side === 'left');
        btn.classList.toggle('is-dock-right', pos.side !== 'left');
        btn.style.top = `${Math.min(window.innerHeight - size - 16, Math.max(64, top))}px`;
        btn.style.bottom = 'auto';
        btn.style.left = pos.side === 'left' ? '8px' : 'auto';
        btn.style.right = pos.side === 'left' ? 'auto' : '8px';
    }

    function bindFabDock(btn) {
        if (!btn || btn.dataset.dockBound === '1') {
            applyFabDock(btn);
            return;
        }
        btn.dataset.dockBound = '1';
        let dragging = false;
        let moved = false;
        let startX = 0;
        let startY = 0;
        let origLeft = 0;
        let origTop = 0;

        btn.addEventListener('pointerdown', (e) => {
            if (!isDesktopShell() || e.button) return;
            dragging = true;
            moved = false;
            const rect = btn.getBoundingClientRect();
            startX = e.clientX;
            startY = e.clientY;
            origLeft = rect.left;
            origTop = rect.top;
            btn.classList.add('is-dragging');
            btn.setPointerCapture(e.pointerId);
        });
        btn.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (Math.abs(dx) > 5 || Math.abs(dy) > 5) moved = true;
            if (!moved) return;
            btn.classList.remove('is-dock-left', 'is-dock-right');
            btn.style.left = `${origLeft + dx}px`;
            btn.style.top = `${origTop + dy}px`;
            btn.style.right = 'auto';
            btn.style.bottom = 'auto';
        });
        const endDrag = () => {
            if (!dragging) return;
            dragging = false;
            btn.classList.remove('is-dragging');
            if (!moved) return;
            btn.dataset.dragged = '1';
            const rect = btn.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            saveFabPos({
                side: cx < window.innerWidth / 2 ? 'left' : 'right',
                y: (rect.top + rect.height / 2) / window.innerHeight,
            });
            applyFabDock(btn);
        };
        btn.addEventListener('pointerup', endDrag);
        btn.addEventListener('pointercancel', endDrag);
        window.addEventListener('resize', () => applyFabDock(btn));
        applyFabDock(btn);
    }

    window.syncTimeLogFabDock = function syncTimeLogFabDock() {
        applyFabDock(document.getElementById('timeLogFab'));
    };

    function setCompactCollapsed(collapsed) {
        if (!compact) return;
        document.body.classList.toggle('tl-collapsed', collapsed);
        const size = collapsed ? BALL_SIZE : COMPACT_SIZE;
        [window, window.parent, window.top].forEach((host) => {
            try {
                host.resizeTo(size.width, size.height);
            } catch (e) {
                /* 标签页或跨域窗口无法改尺寸 */
            }
        });
    }

    function durationSinceLast(clickedAt) {
        const nodes = data.nodes || [];
        if (!nodes.length) return 0;
        const prev = new Date(nodes[nodes.length - 1].logged_at).getTime();
        if (Number.isNaN(prev)) return 0;
        return Math.max(0, Math.round((clickedAt - prev) / 1000));
    }

    async function punch(forSelectedDay) {
        if (compact) setCompactCollapsed(false);
        const token = localStorage.getItem('authToken');
        if (!token) {
            if (typeof showMessage === 'function') showMessage('请先登录', 'error');
            return;
        }
        const punchDay = forSelectedDay ? currentDay() : todayISO();
        const clickedAt = Date.now();
        try {
            day = punchDay;
            if (!data.nodes || data.date !== punchDay) {
                await load(punchDay);
            } else {
                await loadTasks();
            }
            const duration = durationSinceLast(clickedAt);
            const node = {
                id: null,
                log_date: punchDay,
                logged_at: new Date(clickedAt).toISOString(),
                label: '',
                duration_seconds: duration,
                task_id: null,
            };
            openSheet(node, duration <= 0 && !(data.nodes || []).length);
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
    }

    function ensureFab() {
        if (compact) return;
        let btn = document.getElementById('timeLogFab');
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'timeLogFab';
            btn.className = 'tl-fab';
            btn.type = 'button';
            btn.textContent = '记';
            btn.title = '记下此刻。写下内容才会记入日志。电脑上可拖到左右边缘停靠。';
            btn.addEventListener('click', (e) => {
                if (btn.dataset.dragged === '1') {
                    e.preventDefault();
                    btn.dataset.dragged = '0';
                    return;
                }
                punch(false);
            });
            document.body.appendChild(btn);
        }
        bindFabDock(btn);
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
                ? '打开后，离开书然也能点悬浮按钮。写下内容才会记入日志。'
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
        const url = '/static/time-log-compact.html?ball=1';
        const w = window.open(
            url,
            'shuran-timelog',
            `popup=yes,width=${BALL_SIZE.width},height=${BALL_SIZE.height},resizable=yes,scrollbars=no,menubar=no,toolbar=no,location=no,status=no`
        );
        if (!w && typeof showMessage === 'function') {
            showMessage('浏览器拦截了悬浮窗，请允许弹出式窗口', 'error');
        }
    }

    window.syncTimeLogChrome = function syncTimeLogChrome() {
        ensureFab();
        const fab = document.getElementById('timeLogFab');
        if (fab) fab.hidden = !localStorage.getItem('authToken');
        syncOverlaySwitch();
        syncAssistRow();
    };

    window.loadTimeLog = function loadTimeLog() {
        return load(currentDay()).catch((e) => {
            const total = document.getElementById('timeLogTotal');
            if (total) total.textContent = e.message || '加载失败';
        });
    };

    window.punchTimeLog = punch;

    window.closeTimeLogSheet = discardSheet;

    function syncAssistRow() {
        const row = document.getElementById('timeLogAssistRow');
        const n = native();
        if (!row) return;
        const show = !!(n && (typeof n.requestAssistantRole === 'function' || typeof n.pinTimeLogShortcut === 'function'));
        row.hidden = !show;
        const status = document.getElementById('timeLogAssistStatus');
        if (!status || !n) return;
        let held = false;
        try {
            held = typeof n.isAssistantRoleHeld === 'function' && !!n.isAssistantRoleHeld();
        } catch (e) {
            held = false;
        }
        status.textContent = held
            ? '书然已是默认数字助理。荣耀/华为可在系统设置把电源键长按指定为书然。'
            : '第三方应用不能真正抢走电源键。能做的是：设为默认数字助理后，部分荣耀/华为机会把电源键长按打开书然「记」。所有机型都可用快捷设置磁贴或桌面快捷方式。';
    }

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
        document.getElementById('timeLogDockBall')?.addEventListener('click', () => punch(false));
        document.getElementById('timeLogMinimizeBtn')?.addEventListener('click', () => {
            discardSheet();
            setCompactCollapsed(true);
        });
        if (compact && new URLSearchParams(location.search).get('ball') === '1') {
            setCompactCollapsed(true);
        }
        document.getElementById('timeLogOverlaySwitch')?.addEventListener('change', (e) => {
            applyOverlay(e.target.checked);
        });
        document.getElementById('timeLogAssistBtn')?.addEventListener('click', () => {
            const n = native();
            try {
                if (n && typeof n.requestAssistantRole === 'function') n.requestAssistantRole();
            } catch (e) {
                if (typeof showMessage === 'function') showMessage('无法打开系统助理设置', 'error');
            }
        });
        document.getElementById('timeLogShortcutBtn')?.addEventListener('click', () => {
            const n = native();
            try {
                if (n && typeof n.pinTimeLogShortcut === 'function') n.pinTimeLogShortcut();
            } catch (e) {
                if (typeof showMessage === 'function') showMessage('无法添加桌面快捷方式', 'error');
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('timeLogSheet')) {
                e.preventDefault();
                discardSheet();
            }
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
                    discardSheet();
                    return 'consumed';
                }
                return originalHandle();
            };
        }

        if (document.getElementById('time-log') || compact) {
            load(currentDay()).catch(() => {});
        }
        syncOverlaySwitch();
        syncAssistRow();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
