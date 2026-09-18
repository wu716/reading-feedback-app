/**
 * 时间日志：点击节点记下此刻，再写上一段做了什么。
 */
(function () {
    let day = null;
    let data = { date: null, total_seconds: 0, nodes: [] };
    let tasks = [];
    let pendingNode = null;
    let captureContext = null;
    let captureKind = 'moment';
    let captureTodoWhen = 'today';
    let compact = document.body.classList.contains('tl-compact-page');
    let composerViewportHandler = null;

    function todayISO() {
        try {
            return new Intl.DateTimeFormat('en-CA', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
            }).format(new Date());
        } catch (e) {
            const now = new Date();
            const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
            return local.toISOString().slice(0, 10);
        }
    }

    function shiftDay(iso, delta) {
        const parts = String(iso || '').split('-').map((n) => parseInt(n, 10));
        if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) {
            return todayISO();
        }
        const shifted = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + delta));
        return shifted.toISOString().slice(0, 10);
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
            const viewingToday = currentDay() === todayISO();
            total.textContent = data.nodes?.length
                ? `已记录 ${formatDuration(data.total_seconds)}`
                : (viewingToday ? '今天还没有写下任何一段' : `${currentDay()} 还没有写下任何一段`);
        }
        const hint = document.getElementById('timeLogRecentHint');
        if (hint && (data.nodes || []).length) {
            hint.hidden = true;
            hint.textContent = '';
        }
        if (!list) return;
        if (!(data.nodes || []).length) {
            list.innerHTML = '<p class="flow-empty">写下后才会出现在日志里。</p>';
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
                    <div class="tl-node-actions">
                        <button type="button" class="flow-mini-btn" data-act="edit">改</button>
                        <button type="button" class="flow-mini-btn" data-act="delete">删</button>
                    </div>
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
        if (!(data.nodes || []).length) {
            loadRecentHint();
        }
    }

    async function loadRecentHint() {
        const hint = document.getElementById('timeLogRecentHint');
        if (!hint) return;
        try {
            const summary = await logApi('/recent-days?days=30');
            const days = (summary.days || []).filter((item) => item.date && item.date !== currentDay() && item.count);
            if (!days.length) {
                hint.hidden = true;
                hint.textContent = '';
                return;
            }
            const shown = days.slice(0, 5).map((item) => `${item.date} ${item.count} 条`).join('，');
            hint.textContent = `这台服务器上还有记录：${shown}。可用「前一天 / 后一天」查看。`;
            hint.hidden = false;
        } catch (e) {
            hint.hidden = true;
        }
    }

    function isUnwritten(node) {
        return !!(node && !(node.label || '').trim() && !node.task_id);
    }

    function closeSheet() {
        unbindComposerViewport();
        document.getElementById('timeLogSheet')?.remove();
        document.getElementById('timeLogSheetBackdrop')?.remove();
        document.body.classList.remove('tl-composing');
        pendingNode = null;
        captureContext = null;
    }

    async function removeNode(nodeId) {
        const id = parseInt(nodeId, 10);
        if (!id) return false;
        if (!window.confirm('确定删除？')) {
            return false;
        }
        try {
            data = await logApi(`/nodes/${id}`, { method: 'DELETE' });
            renderList();
            return true;
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
            return false;
        }
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

    function unbindComposerViewport() {
        if (!composerViewportHandler) return;
        window.visualViewport?.removeEventListener('resize', composerViewportHandler);
        window.visualViewport?.removeEventListener('scroll', composerViewportHandler);
        window.removeEventListener('resize', composerViewportHandler);
        composerViewportHandler = null;
    }

    function bindComposerViewport(sheet) {
        unbindComposerViewport();
        const input = sheet.querySelector('#timeLogSheetInput');
        const apply = () => {
            if (isDesktopShell() && !compact) {
                sheet.style.bottom = '';
                sheet.style.maxHeight = '';
                return;
            }
            const vv = window.visualViewport;
            const occluded = vv
                ? Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop))
                : 0;
            sheet.style.bottom = `${occluded}px`;
            sheet.style.maxHeight = `${Math.max(220, Math.round((vv ? vv.height : window.innerHeight) - 8))}px`;
            if (input && document.activeElement === input) {
                input.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }
        };
        composerViewportHandler = apply;
        window.visualViewport?.addEventListener('resize', apply);
        window.visualViewport?.addEventListener('scroll', apply);
        window.addEventListener('resize', apply);
        input?.addEventListener('focus', () => {
            setTimeout(apply, 50);
            setTimeout(() => input.scrollIntoView({ block: 'center', inline: 'nearest' }), 80);
        });
        apply();
    }

    function openSheet(node, isStart) {
        closeSheet();
        pendingNode = node;
        document.body.classList.add('tl-composing');
        const backdrop = document.createElement('div');
        backdrop.id = 'timeLogSheetBackdrop';
        backdrop.className = 'tl-sheet-backdrop';
        const sheet = document.createElement('div');
        sheet.id = 'timeLogSheet';
        sheet.className = 'tl-sheet';
        sheet.innerHTML = `
            <h3>${isStart ? '记下开始' : '这段在做什么'}</h3>
            <p>${isStart ? '写下才会记入。' : `距上一段 ${formatDuration(node.duration_seconds)}`}</p>
            <textarea id="timeLogSheetInput" maxlength="500" placeholder="这段在做什么" enterkeyhint="done">${escapeHtml(node.label || '')}</textarea>
            <div class="tl-sheet-actions">
                ${node.id && !isUnwritten(node) ? '<button type="button" class="flow-ghost-btn" id="timeLogSheetDelete">删除</button>' : '<span></span>'}
                <div class="tl-sheet-actions-end">
                    <button type="button" class="flow-ghost-btn" id="timeLogSheetCancel">稍后</button>
                    <button type="button" class="flow-solid-btn" id="timeLogSheetSave">写下</button>
                </div>
            </div>
        `;
        document.body.appendChild(backdrop);
        document.body.appendChild(sheet);
        placeDesktopSheet(sheet);
        bindComposerViewport(sheet);
        backdrop.addEventListener('click', () => discardSheet());
        sheet.querySelector('#timeLogSheetCancel').addEventListener('click', () => discardSheet());
        sheet.querySelector('#timeLogSheetDelete')?.addEventListener('click', async () => {
            if (!node.id) return;
            const removed = await removeNode(node.id);
            if (removed) closeSheet();
        });
        sheet.querySelector('#timeLogSheetSave').addEventListener('click', async () => {
            const input = sheet.querySelector('#timeLogSheetInput');
            const label = (input?.value || '').trim();
            if (!label && !node.task_id) {
                await discardSheet();
                return;
            }
            try {
                if (node.id) {
                    await logApi(`/nodes/${node.id}`, {
                        method: 'PATCH',
                        body: JSON.stringify({ label }),
                    });
                } else {
                    await logApi('/nodes', {
                        method: 'POST',
                        body: JSON.stringify({
                            log_date: node.log_date || currentDay(),
                            logged_at: node.logged_at,
                            label,
                        }),
                    });
                }
                closeSheet();
                await load(currentDay());
            } catch (e) {
                if (typeof showMessage === 'function') showMessage(e.message, 'error');
            }
        });
        const input = sheet.querySelector('#timeLogSheetInput');
        if (input) {
            input.focus();
            const len = input.value.length;
            input.setSelectionRange(len, len);
        }
    }

    const CAPTURE_KINDS = ['moment', 'idea', 'todo'];
    const CAPTURE_KIND_KEY = 'shuran.captureKind';

    function readCachedKind() {
        try {
            const raw = localStorage.getItem(CAPTURE_KIND_KEY);
            if (CAPTURE_KINDS.includes(raw)) return raw;
        } catch (e) {
            /* ignore */
        }
        return 'moment';
    }

    function writeCachedKind(kind) {
        const next = CAPTURE_KINDS.includes(kind) ? kind : 'moment';
        captureKind = next;
        try {
            localStorage.setItem(CAPTURE_KIND_KEY, next);
        } catch (e) {
            /* ignore */
        }
        return next;
    }

    async function loadCapturePreference() {
        captureKind = readCachedKind();
        try {
            const pref = await apiRequest('/api/capture/preference');
            if (pref && CAPTURE_KINDS.includes(pref.kind)) {
                writeCachedKind(pref.kind);
            }
        } catch (e) {
            /* 离线时用本地默认时刻 */
        }
        return captureKind;
    }

    async function saveCapturePreference(kind) {
        const next = writeCachedKind(kind);
        try {
            await apiRequest('/api/capture/preference', {
                method: 'PATCH',
                body: JSON.stringify({ kind: next }),
            });
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
        syncCaptureKindRow();
        return next;
    }

    function kindCopy(kind, ctx) {
        if (kind === 'idea') {
            return {
                title: 'idea',
                hint: '先写下来，之后在 idea 里能看到。',
                placeholder: '一闪而过的念头',
            };
        }
        if (kind === 'todo') {
            return {
                title: 'todo',
                hint: '先写下来，再选今天或以后。',
                placeholder: '突然想起要做的事',
            };
        }
        if (ctx && ctx.isStart) {
            return {
                title: '时刻',
                hint: '写下才会记入 moment。',
                placeholder: '这段在做什么',
            };
        }
        return {
            title: '时刻',
            hint: ctx && ctx.duration
                ? `距上一段 ${formatDuration(ctx.duration)}`
                : '写下才会记入 moment。',
            placeholder: '这段在做什么',
        };
    }

    function paintCaptureSheet(sheet) {
        const ctx = captureContext || {};
        const copy = kindCopy(captureKind, ctx);
        const title = sheet.querySelector('#timeLogSheetTitle');
        const hint = sheet.querySelector('#timeLogSheetHint');
        const input = sheet.querySelector('#timeLogSheetInput');
        const whenRow = sheet.querySelector('#timeLogWhenPicks');
        if (title) title.textContent = copy.title;
        if (hint) hint.textContent = copy.hint;
        if (input) input.placeholder = copy.placeholder;
        sheet.querySelectorAll('[data-kind]').forEach((btn) => {
            btn.classList.toggle('is-on', btn.dataset.kind === captureKind);
        });
        sheet.querySelectorAll('[data-when]').forEach((btn) => {
            btn.classList.toggle('is-on', btn.dataset.when === captureTodoWhen);
        });
        if (whenRow) whenRow.hidden = captureKind !== 'todo';
    }

    async function saveCaptureSheet(sheet) {
        const input = sheet.querySelector('#timeLogSheetInput');
        const label = (input?.value || '').trim();
        if (!label) {
            await discardSheet();
            return;
        }
        const ctx = captureContext || {};
        const payload = { kind: captureKind, text: label };
        if (captureKind === 'todo') payload.todo_when = captureTodoWhen;
        if (captureKind === 'moment' && ctx.loggedAt) payload.logged_at = ctx.loggedAt;
        try {
            await apiRequest('/api/capture/save', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            closeSheet();
            if (captureKind === 'moment') {
                await load(ctx.logDate || currentDay());
            }
            if (captureKind === 'idea' && typeof window.loadIdeas === 'function') {
                window.loadIdeas();
            }
            if (captureKind === 'todo' && captureTodoWhen === 'today' && typeof window.loadTodayDashboard === 'function') {
                window.loadTodayDashboard();
            }
            if (captureKind === 'todo' && captureTodoWhen === 'later' && typeof window.loadDailySchedule === 'function') {
                window.loadDailySchedule();
            }
            if (typeof showMessage === 'function') {
                const done = captureKind === 'idea'
                    ? '已记入 idea'
                    : (captureKind === 'todo'
                        ? (captureTodoWhen === 'later' ? '已记入 later' : '已记入 today')
                        : '已记入 moment');
                showMessage(done, 'success');
            }
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
    }

    function openCaptureSheet(ctx) {
        closeSheet();
        captureContext = ctx || {};
        captureTodoWhen = 'today';
        document.body.classList.add('tl-composing');
        const backdrop = document.createElement('div');
        backdrop.id = 'timeLogSheetBackdrop';
        backdrop.className = 'tl-sheet-backdrop';
        const sheet = document.createElement('div');
        sheet.id = 'timeLogSheet';
        sheet.className = 'tl-sheet';
        sheet.innerHTML = `
            <h3 id="timeLogSheetTitle"></h3>
            <p id="timeLogSheetHint"></p>
            <div class="tl-kind-picks" role="tablist" aria-label="记下到哪里">
                <button type="button" data-kind="moment">moment</button>
                <button type="button" data-kind="idea">idea</button>
                <button type="button" data-kind="todo">todo</button>
            </div>
            <div class="tl-when-picks" id="timeLogWhenPicks" hidden>
                <button type="button" data-when="today">today</button>
                <button type="button" data-when="later">later</button>
            </div>
            <textarea id="timeLogSheetInput" maxlength="500" enterkeyhint="done"></textarea>
            <div class="tl-sheet-actions">
                <span></span>
                <div class="tl-sheet-actions-end">
                    <button type="button" class="flow-ghost-btn" id="timeLogSheetCancel">稍后</button>
                    <button type="button" class="flow-solid-btn" id="timeLogSheetSave">写下</button>
                </div>
            </div>
        `;
        document.body.appendChild(backdrop);
        document.body.appendChild(sheet);
        paintCaptureSheet(sheet);
        placeDesktopSheet(sheet);
        bindComposerViewport(sheet);
        backdrop.addEventListener('click', () => discardSheet());
        sheet.querySelector('#timeLogSheetCancel').addEventListener('click', () => discardSheet());
        sheet.querySelectorAll('[data-kind]').forEach((btn) => {
            btn.addEventListener('click', () => {
                captureKind = btn.dataset.kind;
                paintCaptureSheet(sheet);
                placeDesktopSheet(sheet);
            });
        });
        sheet.querySelectorAll('[data-when]').forEach((btn) => {
            btn.addEventListener('click', () => {
                captureTodoWhen = btn.dataset.when;
                paintCaptureSheet(sheet);
            });
        });
        sheet.querySelector('#timeLogSheetSave').addEventListener('click', () => saveCaptureSheet(sheet));
        const input = sheet.querySelector('#timeLogSheetInput');
        if (input) {
            input.focus();
        }
    }

    function syncCaptureKindRow() {
        captureKind = readCachedKind();
        document.querySelectorAll('input[name="captureKindDefault"]').forEach((input) => {
            input.checked = input.value === captureKind;
        });
        const label = document.getElementById('captureKindDefaultDesc');
        if (label) {
            const names = { moment: 'moment', idea: 'idea', todo: 'todo' };
            label.textContent = `三击或点「记」时先落到 ${names[captureKind] || 'moment'}，仍可当场改。`;
        }
    }

    window.syncCaptureKindRow = syncCaptureKindRow;
    window.loadCapturePreference = loadCapturePreference;

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

    async function punch(forSelectedDay, kindOverride) {
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
        } catch (e) {
            /* 时刻需要日志；灵感/待办仍可先写 */
        }
        try {
            await loadCapturePreference();
            if (CAPTURE_KINDS.includes(kindOverride)) captureKind = kindOverride;
            const duration = durationSinceLast(clickedAt);
            openCaptureSheet({
                logDate: punchDay,
                loggedAt: new Date(clickedAt).toISOString(),
                duration,
                isStart: duration <= 0 && !(data.nodes || []).length,
            });
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
            btn.title = '记下。默认为 moment，可当场改成 idea 或 todo。';
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

    function isPhoneApp() {
        if (typeof shuranIsPhoneApp === 'function') return !!shuranIsPhoneApp();
        return !!(native() || /ShuranApp/i.test(navigator.userAgent || ''));
    }

    function hasVolumeApi(n) {
        return !!(n && typeof n.setVolumeTripleEnabled === 'function' && typeof n.isVolumeTripleEnabled === 'function');
    }

    function shellNeedsVolumeUpdate() {
        return !hasVolumeApi(native());
    }

    function readVolumeOn() {
        const n = native();
        try {
            return !!(hasVolumeApi(n) && n.isVolumeTripleEnabled());
        } catch (e) {
            return false;
        }
    }

    function bindOnce(el, event, handler) {
        if (!el || el.dataset.bound === '1') return;
        el.dataset.bound = '1';
        el.addEventListener(event, handler);
    }

    function applyVolumeWant(want, switchEl) {
        const n = native();
        if (!hasVolumeApi(n) || shellNeedsVolumeUpdate()) {
            if (switchEl) switchEl.checked = false;
            if (typeof showMessage === 'function') {
                showMessage('当前手机安装包没有这项。请换安装包，覆盖即可，不用卸载。', 'info');
            }
            if (typeof shuranStartAppUpdate === 'function') shuranStartAppUpdate();
            setTimeout(syncAssistRow, 300);
            return;
        }
        try {
            n.setVolumeTripleEnabled(want);
        } catch (err) {
            if (typeof showMessage === 'function') showMessage('无法打开系统无障碍设置', 'error');
            if (switchEl) switchEl.checked = !want;
        }
        setTimeout(syncAssistRow, 400);
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
        syncCaptureKindRow();
        loadCapturePreference().then(syncCaptureKindRow);
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
        const n = native();
        const phone = isPhoneApp();
        const outdated = phone && shellNeedsVolumeUpdate();
        const volumeOn = readVolumeOn();

        const meGroup = document.getElementById('meVolumeTripleGroup');
        if (meGroup) meGroup.hidden = false;
        const volumeRow = document.getElementById('timeLogVolumeRow');
        if (volumeRow) volumeRow.hidden = !phone;
        const meVolumeRow = document.getElementById('timeLogVolumeMeRow');
        if (meVolumeRow) meVolumeRow.hidden = !phone;

        const meSwitch = document.getElementById('timeLogVolumeMeSwitch');
        const volumeSwitch = document.getElementById('timeLogVolumeSwitch');
        [meSwitch, volumeSwitch].forEach((sw) => {
            if (!sw) return;
            sw.checked = volumeOn;
            sw.disabled = outdated;
        });

        let desc = '书然开着时，约 1.5 秒内连按三下音量减就会打开「记」，不必开本开关。锁屏或其他应用再用，请打开右侧开关。';
        let extra = '';
        if (outdated) {
            desc = '当前安装包没有音量键功能。点「换安装包」覆盖即可，不用卸载。';
            extra = '安装包需更新。更新后打开书然，约 1.5 秒内连按三下音量减就会出现「记」。锁屏或其他 App 再用，再打开右侧开关。';
        } else if (volumeOn) {
            desc = '锁屏或其他应用上，约 1.5 秒内连按三下音量减会弹出「记」。书然在前台时不必开本开关。单击仍调音量。';
        }

        const meDesc = document.getElementById('timeLogVolumeMeDesc');
        const volumeHint = document.getElementById('timeLogVolumeHint');
        const meHint = document.getElementById('timeLogVolumeMeHint');
        if (meDesc) meDesc.textContent = desc;
        if (volumeHint) volumeHint.textContent = desc;
        if (meHint) {
            meHint.textContent = extra;
            meHint.hidden = !extra;
        }
        const updateWrap = document.getElementById('timeLogVolumeUpdateWrap');
        if (updateWrap) updateWrap.hidden = !outdated;

        const row = document.getElementById('timeLogAssistRow');
        const showAssist = !!(n && typeof n.pinTimeLogShortcut === 'function');
        if (row) row.hidden = !showAssist;
        const status = document.getElementById('timeLogAssistStatus');
        if (!status || !n) return;
        let held = false;
        try {
            held = typeof n.isAssistantRoleHeld === 'function' && !!n.isAssistantRoleHeld();
        } catch (e) {
            held = false;
        }
        status.textContent = held
            ? '书然已是默认数字助理。请再到荣耀/华为系统设置把电源键长按指定为书然。'
            : '先把书然设为默认数字助理，再到荣耀「辅助功能 / 快捷启动与手势」或华为「智慧助手 / 按键与手势」里，把电源键长按指过来。';
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
        document.getElementById('timeLogPunchBtn')?.addEventListener('click', () => punch(true, 'moment'));
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
        bindOnce(document.getElementById('timeLogVolumeSwitch'), 'change', (e) => {
            applyVolumeWant(!!e.target.checked, e.target);
        });
        bindOnce(document.getElementById('timeLogVolumeMeSwitch'), 'change', (e) => {
            applyVolumeWant(!!e.target.checked, e.target);
        });
        document.querySelectorAll('input[name="captureKindDefault"]').forEach((input) => {
            bindOnce(input, 'change', () => {
                if (input.checked) saveCapturePreference(input.value);
            });
        });
        bindOnce(document.getElementById('timeLogVolumeUpdateBtn'), 'click', () => {
            if (typeof shuranStartAppUpdate === 'function') shuranStartAppUpdate();
        });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') syncAssistRow();
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
            const act = e.target.dataset.act;
            const article = e.target.closest('[data-node-id]');
            if (!article || !act) return;
            const id = parseInt(article.dataset.nodeId, 10);
            if (act === 'delete') {
                removeNode(id);
                return;
            }
            if (act !== 'edit') return;
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
        const previousResume = window.onNativeAppResume;
        window.onNativeAppResume = function (info) {
            if (typeof previousResume === 'function') previousResume(info);
            syncAssistRow();
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
