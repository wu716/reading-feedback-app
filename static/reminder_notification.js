/**
 * 自我提醒：轮询 pending 接口。
 * Android App（WebView + ShuranNative）走系统通知（状态栏/锁屏/通知栏），后台由 AlarmManager 触发；
 * 普通浏览器保留页面内铃铛/通知条，并在允许时使用 Notification API。
 */

class ReminderNotificationService {
    constructor() {
        this.pollInterval = 60 * 1000;
        this.timer = null;
        this.isPolling = false;
        this.apiBase = '/api';
        this.pending = [];
        this.shownOsIds = new Set();
        this.shownToastIds = new Set();
        this.dropdownOpen = false;
        this.uiReady = false;
    }

    start() {
        this.ensureUi();
        if (this.isPolling) {
            this.syncNativeSchedule();
            this.checkPendingReminders();
            return;
        }
        this.requestNotificationPermission();
        this.syncNativeSchedule();
        this.checkPendingReminders();
        this.timer = setInterval(() => this.checkPendingReminders(), this.pollInterval);
        this.isPolling = true;

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') this.checkPendingReminders();
        });
        window.addEventListener('focus', () => this.checkPendingReminders());
    }

    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.isPolling = false;
        this.pending = [];
        const wrap = document.getElementById('reminderBellWrap');
        if (wrap) wrap.hidden = true;
        const bar = document.getElementById('inAppReminderBar');
        if (bar) {
            bar.hidden = true;
            bar.classList.remove('show');
            bar.innerHTML = '';
        }
        this.closeDropdown();
        this.clearNativeSession();
    }

    nativeBridge() {
        try {
            return window.ShuranNative || null;
        } catch (e) {
            return null;
        }
    }

    hasNativeMethod(name) {
        const native = this.nativeBridge();
        if (!native) return false;
        try {
            return typeof native[name] === 'function';
        } catch (e) {
            return false;
        }
    }

    isNativeApp() {
        try {
            const native = this.nativeBridge();
            if (!native) return false;
            if (this.hasNativeMethod('isNative')) {
                try {
                    return !!native.isNative();
                } catch (e) {
                    return true;
                }
            }
            return this.hasNativeMethod('showTestNotification')
                || this.hasNativeMethod('showReminder')
                || this.hasNativeMethod('hasPermission');
        } catch (e) {
            return false;
        }
    }

    showFeedback(message, type) {
        this.ensureUi();
        let host = document.getElementById('shuranFeedbackToast');
        if (!host) {
            host = document.createElement('div');
            host.id = 'shuranFeedbackToast';
            host.setAttribute('role', 'status');
            host.style.cssText = [
                'position:fixed',
                'left:50%',
                'top:calc(76px + env(safe-area-inset-top, 0px))',
                'transform:translateX(-50%)',
                'z-index:2147483646',
                'max-width:min(520px, calc(100vw - 24px))',
                'padding:12px 16px',
                'border-radius:12px',
                'box-shadow:0 8px 24px rgba(0,0,0,.22)',
                'font-size:15px',
                'line-height:1.5',
                'color:#fff',
                'pointer-events:none',
                'display:none'
            ].join(';');
            document.body.appendChild(host);
        }
        const colors = {
            success: '#2f9e44',
            error: '#e03131',
            info: '#4263eb',
        };
        host.style.background = colors[type] || colors.info;
        host.textContent = message;
        host.style.display = 'block';
        clearTimeout(this._feedbackTimer);
        this._feedbackTimer = setTimeout(() => {
            host.style.display = 'none';
        }, 5000);
    }

    async testNow() {
        this.ensureUi();
        this.showFeedback('正在发送测试通知…', 'info');

        const native = this.nativeBridge();
        if (native && this.hasNativeMethod('requestPermission')) {
            try { native.requestPermission(); } catch (e) {}
        }

        if (native && this.hasNativeMethod('showTestNotification')) {
            let result = '';
            try {
                result = String(native.showTestNotification() || '');
            } catch (e) {
                console.error('showTestNotification failed', e);
                this.showFeedback('调用系统通知失败，请检查通知权限后重试。', 'error');
                return { ok: false, native: true };
            }
            if (result === 'ok') {
                this.showFeedback('已弹出系统通知。请下拉状态栏或看锁屏，同时页面也会提示。', 'success');
                return { ok: true, native: true };
            }
            if (result === 'no_permission') {
                this.showFeedback('尚未获得通知权限。请在系统弹窗中点「允许」，然后再次点击测试。', 'error');
                return { ok: false, native: true };
            }
            this.showFeedback('系统通知发送失败。请到系统设置里确认已允许「书然」通知。', 'error');
            return { ok: false, native: true };
        }

        if (native && this.hasNativeMethod('showReminder')) {
            try {
                native.showReminder(JSON.stringify({
                    log_id: Date.now() % 100000000,
                    title: '书然测试通知',
                    message: '看到这条就说明系统通知已打通。若状态栏没有出现，请检查更新到最新 App。',
                    reminder_type: 'test',
                    force: true,
                    action_url: '/static/index.html#user-center',
                    triggered_at: new Date().toISOString(),
                }));
                this.showFeedback('已请求系统通知。若状态栏没有出现，请到「我的」检查更新并安装 1.2.1。', 'success');
                return { ok: true, native: true };
            } catch (e) {
                console.error('showReminder test failed', e);
                this.showFeedback('当前 App 版本过旧，无法弹出系统通知。请检查更新或重新安装书然 App。', 'error');
                return { ok: false, native: true };
            }
        }

        if (native) {
            this.showFeedback('当前 App 版本过旧，无法弹出系统通知。请检查更新或重新安装书然 App。', 'error');
            return { ok: false, native: true };
        }

        this.showInPageToast({
            log_id: 'test-' + Date.now(),
            title: '书然测试通知',
            message: '这是页面内预览。手机状态栏通知只能在书然 App 里测试。',
            action_label: '知道了',
            reminder_type: 'test',
        });
        this.showFeedback('浏览器无法弹出手机状态栏通知。请在书然 App 中打开本页再点「测试通知」。', 'info');
        return { ok: true, native: false };
    }

    authToken() {
        return localStorage.getItem('authToken') || localStorage.getItem('token');
    }

    escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    stripHtml(s) {
        return String(s ?? '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    }

    async requestNotificationPermission() {
        if (this.isNativeApp()) {
            try {
                window.ShuranNative.requestPermission();
                return !!window.ShuranNative.hasPermission();
            } catch (e) {
                return false;
            }
        }
        if (!('Notification' in window)) return false;
        if (Notification.permission === 'granted') return true;
        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        }
        return false;
    }

    syncNativeSession() {
        if (!this.isNativeApp()) return;
        try {
            window.ShuranNative.syncSession(JSON.stringify({
                token: this.authToken() || '',
                origin: window.location.origin,
            }));
        } catch (e) {
            console.error('同步原生会话失败:', e);
        }
    }

    clearNativeSession() {
        if (!this.isNativeApp()) return;
        try {
            window.ShuranNative.clearSession();
        } catch (e) {
            console.error('清除原生提醒会话失败:', e);
        }
    }

    async syncNativeSchedule() {
        if (!this.isNativeApp()) return;
        const token = this.authToken();
        this.syncNativeSession();
        if (!token) {
            this.clearNativeSession();
            return;
        }
        try {
            const response = await fetch(`${this.apiBase}/self_talk_reminders/settings`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) return;
            const settings = await response.json();
            window.ShuranNative.scheduleReminders(JSON.stringify({
                enabled: !!settings.is_enabled,
                dailyEnabled: !!settings.daily_reminder_enabled,
                dailyTime: settings.daily_reminder_time || '20:00',
                reminderDays: settings.reminder_days || [0, 1, 2, 3, 4, 5, 6],
                systemNotification: settings.browser_notification !== false,
            }));
            window.ShuranNative.requestPermission();
            window.ShuranNative.pollNow();
        } catch (e) {
            console.error('同步原生提醒失败:', e);
        }
    }

    ensureUi() {
        if (this.uiReady) return;
        this.injectStyles();

        if (!document.getElementById('reminderBellWrap')) {
            this.injectBell();
        }
        if (!document.getElementById('inAppReminderBar')) {
            this.injectHomepageBar();
        }
        if (!document.getElementById('inAppReminderToastHost')) {
            const host = document.createElement('div');
            host.id = 'inAppReminderToastHost';
            host.className = 'in-app-toast-host';
            document.body.appendChild(host);
        }

        const bellBtn = document.getElementById('reminderBellBtn');
        const dropdown = document.getElementById('reminderDropdown');
        if (bellBtn && dropdown) {
            bellBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleDropdown();
            });
        }
        const settingsLink = document.getElementById('reminderSettingsLink');
        if (settingsLink) {
            settingsLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.openSettings();
            });
        }
        const closeBtn = document.getElementById('reminderDropdownClose');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeDropdown();
            });
        }
        document.addEventListener('click', (e) => {
            const wrap = document.getElementById('reminderBellWrap');
            if (wrap && !wrap.contains(e.target)) this.closeDropdown();
        });
        window.addEventListener('resize', () => this.positionDropdown());
        window.addEventListener('orientationchange', () => this.positionDropdown());

        this.uiReady = true;
    }

    injectStyles() {
        if (document.getElementById('inAppReminderStyles')) return;
        const style = document.createElement('style');
        style.id = 'inAppReminderStyles';
        style.textContent = `
            .header-actions { display: flex; align-items: center; gap: 12px; }
            .reminder-bell-wrap { position: relative; flex-shrink: 0; }
            .reminder-bell-btn { position: relative; width: 40px; height: 40px; border: none; border-radius: 12px; background: rgba(255,255,255,0.2); color: white; font-size: 1.2rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
            .reminder-bell-badge { position: absolute; top: -4px; right: -4px; min-width: 18px; height: 18px; padding: 0 5px; background: #ff4757; color: #fff; border-radius: 9px; font-size: 11px; line-height: 18px; font-weight: 700; }
            .reminder-dropdown { position: absolute; top: calc(100% + 8px); right: 0; left: auto; width: 360px; max-width: calc(100vw - 24px); box-sizing: border-box; background: #fff; color: #333; border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,0.18); z-index: 1200; overflow: hidden; display: flex; flex-direction: column; }
            .reminder-dropdown[hidden] { display: none !important; }
            .reminder-dropdown-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #eee; font-size: 0.95rem; flex-shrink: 0; }
            .reminder-dropdown-head-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
            .reminder-dropdown-head a { color: #667eea; text-decoration: none; font-size: 0.85rem; }
            .reminder-dropdown-close { width: 32px; height: 32px; border: none; border-radius: 8px; background: #f0f0f0; color: #555; font-size: 1.25rem; line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
            .reminder-dropdown-list { max-height: 360px; overflow-y: auto; min-height: 0; overscroll-behavior: contain; }
            .reminder-empty { padding: 20px; color: #999; font-size: 0.9rem; text-align: center; }
            .reminder-item { padding: 12px 14px; border-bottom: 1px solid #f3f3f3; }
            .reminder-item:last-child { border-bottom: none; }
            .reminder-item h5 { margin: 0 0 6px; color: #667eea; font-size: 0.95rem; }
            .reminder-item p { margin: 0 0 10px; color: #555; font-size: 0.85rem; line-height: 1.45; }
            .reminder-item-time { color: #999; font-size: 0.75rem; margin-bottom: 8px; }
            .reminder-item-actions { display: flex; gap: 8px; }
            .reminder-item-actions button { flex: 1; border: none; border-radius: 6px; padding: 7px 10px; cursor: pointer; font-size: 0.8rem; }
            .reminder-item-actions .primary { background: #667eea; color: #fff; }
            .reminder-item-actions .ghost { background: #f0f0f0; color: #666; }
            .in-app-reminder-bar { display: none; margin: 0 0 16px; padding: 12px 16px; background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 12px; color: #3730a3; align-items: flex-start; gap: 12px; }
            .in-app-reminder-bar.show { display: flex; }
            .in-app-reminder-bar .bar-body { flex: 1; min-width: 0; }
            .in-app-reminder-bar strong { display: block; margin-bottom: 4px; }
            .in-app-reminder-bar p { margin: 0; font-size: 0.9rem; line-height: 1.45; }
            .in-app-reminder-bar .bar-actions { display: flex; gap: 8px; flex-shrink: 0; }
            .in-app-reminder-bar button { border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 0.85rem; }
            .in-app-reminder-bar .primary { background: #667eea; color: #fff; }
            .in-app-reminder-bar .ghost { background: #fff; color: #555; }
            .in-app-toast-host { position: fixed; top: 84px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; pointer-events: none; }
            .in-page-notification { pointer-events: auto; background: #fff; padding: 16px 18px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.16); max-width: 360px; border-left: 4px solid #667eea; animation: inAppSlideIn 0.25s ease; }
            .reminder-bell-wrap.floating { display: none; }
            @keyframes inAppSlideIn { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
            @media (max-width: 768px) {
                .in-app-toast-host { top: 76px; left: 12px; right: 12px; }
                .in-page-notification { max-width: none; }
                .in-app-reminder-bar { flex-direction: column; }
                .reminder-dropdown { position: fixed; top: var(--reminder-sheet-top, 64px); left: max(12px, env(safe-area-inset-left, 0px)); right: max(12px, env(safe-area-inset-right, 0px)); width: auto; max-width: none; max-height: calc(100dvh - var(--reminder-sheet-top, 64px) - 12px); transform: none; z-index: 1300; }
                .reminder-dropdown-list { max-height: none; flex: 1 1 auto; }
                .reminder-item-actions { flex-wrap: wrap; }
                .reminder-item-actions button { min-width: 0; }
            }
        `;
        document.head.appendChild(style);
    }

    injectBell() {
        const wrap = document.createElement('div');
        wrap.className = 'reminder-bell-wrap';
        wrap.id = 'reminderBellWrap';
        wrap.innerHTML = `
            <button type="button" class="header-icon-btn reminder-bell-btn" id="reminderBellBtn" aria-label="应用内提醒" title="应用内提醒">🔔<span class="reminder-bell-badge" id="reminderBellBadge" hidden>0</span></button>
            <div class="reminder-dropdown" id="reminderDropdown" hidden>
                <div class="reminder-dropdown-head">
                    <strong>提醒</strong>
                    <div class="reminder-dropdown-head-actions">
                        <a href="#" id="reminderSettingsLink">提醒设置</a>
                        <button type="button" class="reminder-dropdown-close" id="reminderDropdownClose" aria-label="关闭">×</button>
                    </div>
                </div>
                <div class="reminder-dropdown-list" id="reminderDropdownList"></div>
            </div>
        `;
        const header = document.querySelector('.app-header');
        if (header) {
            let actions = header.querySelector('.header-actions');
            if (!actions) {
                actions = document.createElement('div');
                actions.className = 'header-actions';
                const userInfo = header.querySelector('#userInfo');
                if (userInfo) {
                    userInfo.parentNode.insertBefore(actions, userInfo);
                    actions.appendChild(wrap);
                    actions.appendChild(userInfo);
                } else {
                    header.appendChild(actions);
                    actions.appendChild(wrap);
                }
            } else {
                actions.insertBefore(wrap, actions.firstChild);
            }
        } else {
            // Self-talk / 个人中心已有顶栏「提醒设置」，不再挂悬浮铃铛（会挡住历史记录）
            return;
        }
    }

    injectHomepageBar() {
        const bar = document.createElement('div');
        bar.className = 'in-app-reminder-bar';
        bar.id = 'inAppReminderBar';
        bar.hidden = true;
        const dash = document.querySelector('.homepage-dashboard');
        if (dash && dash.parentNode) {
            dash.parentNode.insertBefore(bar, dash);
        }
    }

    toggleDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (!dropdown) return;
        this.dropdownOpen = dropdown.hidden;
        dropdown.hidden = !this.dropdownOpen;
        if (this.dropdownOpen) this.positionDropdown();
    }

    closeDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (dropdown) dropdown.hidden = true;
        this.dropdownOpen = false;
    }

    isNarrowViewport() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    positionDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (!dropdown || dropdown.hidden) return;

        dropdown.style.transform = '';
        dropdown.style.removeProperty('--reminder-sheet-top');

        if (this.isNarrowViewport()) {
            const header = document.querySelector('.app-header');
            const headerBottom = header ? header.getBoundingClientRect().bottom : 56;
            const top = Math.max(8, Math.round(headerBottom + 8));
            dropdown.style.setProperty('--reminder-sheet-top', `${top}px`);
            return;
        }

        const rect = dropdown.getBoundingClientRect();
        const pad = 12;
        if (rect.left < pad) {
            dropdown.style.transform = `translateX(${pad - rect.left}px)`;
        } else if (rect.right > window.innerWidth - pad) {
            dropdown.style.transform = `translateX(${window.innerWidth - pad - rect.right}px)`;
        }
    }

    openSettings() {
        this.closeDropdown();
        if (typeof navigateTo === 'function') {
            navigateTo('user-center');
            return;
        }
        if (window.location.pathname.includes('index.html') || window.location.pathname === '/' || window.location.pathname === '') {
            window.location.hash = 'user-center';
            return;
        }
        window.location.href = '/static/user_center.html';
    }

    async checkPendingReminders() {
        const token = this.authToken();
        if (!token) return;
        this.ensureUi();

        try {
            const response = await fetch(`${this.apiBase}/self_talk_reminders/pending`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.ok) {
                const data = await response.json();
                const list = data.notifications || [];
                const prevIds = new Set(this.pending.map((n) => n.log_id));
                const firstLoad = !this._loadedOnce;
                this._loadedOnce = true;
                this.pending = list;
                this.renderAll();
                if (firstLoad) {
                    if (!this.isNativeApp() && list[0]) this.announceNew(list[0]);
                } else {
                    list.filter((n) => !prevIds.has(n.log_id)).forEach((n) => this.announceNew(n));
                }
            } else if (response.status === 401) {
                this.stop();
            }
        } catch (error) {
            console.error('检查待处理提醒失败:', error);
        }
    }

    announceNew(notification) {
        if (this.isNativeApp()) {
            this.showNativeNotification(notification);
            return;
        }
        this.showInPageToast(notification);
        this.maybeShowOsNotification(notification);
    }

    showNativeNotification(reminderData) {
        try {
            window.ShuranNative.showReminder(JSON.stringify({
                log_id: reminderData.log_id,
                title: reminderData.title,
                message: this.stripHtml(reminderData.message),
                reminder_type: reminderData.reminder_type,
                action_url: reminderData.action_url || '/static/self_talk/index.html',
                triggered_at: reminderData.triggered_at || '',
            }));
        } catch (error) {
            console.error('显示系统通知失败:', error);
            this.showInPageToast(reminderData);
        }
    }

    maybeShowOsNotification(reminderData) {
        if (this.isNativeApp()) return;
        if (!('Notification' in window) || Notification.permission !== 'granted') return;
        if (this.shownOsIds.has(reminderData.log_id)) return;
        this.shownOsIds.add(reminderData.log_id);
        try {
            const notification = new Notification(reminderData.title, {
                body: this.stripHtml(reminderData.message),
                tag: `reminder-${reminderData.log_id}`,
                requireInteraction: false,
                silent: false,
            });
            notification.onclick = () => {
                window.focus();
                this.goToAction(reminderData, true);
                notification.close();
            };
        } catch (error) {
            console.error('显示浏览器通知失败:', error);
        }
    }

    showInPageToast(reminderData) {
        if (this.shownToastIds.has(reminderData.log_id)) return;
        this.shownToastIds.add(reminderData.log_id);
        const host = document.getElementById('inAppReminderToastHost');
        if (!host) return;
        const el = document.createElement('div');
        el.className = 'in-page-notification';
        el.dataset.logId = String(reminderData.log_id);
        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                <h4 style="margin:0;color:#667eea;font-size:1rem;">${this.escapeHtml(reminderData.title)}</h4>
                <button type="button" data-close style="background:none;border:none;font-size:1.2rem;cursor:pointer;color:#999;">×</button>
            </div>
            <p style="margin:0 0 12px;color:#555;line-height:1.45;font-size:0.9rem;">${this.escapeHtml(this.stripHtml(reminderData.message))}</p>
            <div style="display:flex;gap:8px;">
                <button type="button" data-act style="flex:1;background:#667eea;color:#fff;border:none;padding:8px 12px;border-radius:6px;cursor:pointer;">${this.escapeHtml(reminderData.action_label || '去处理')}</button>
                <button type="button" data-later style="flex:1;background:#f0f0f0;color:#666;border:none;padding:8px 12px;border-radius:6px;cursor:pointer;">稍后</button>
            </div>
        `;
        el.querySelector('[data-close]').onclick = () => el.remove();
        el.querySelector('[data-later]').onclick = () => el.remove();
        el.querySelector('[data-act]').onclick = () => {
            el.remove();
            this.goToAction(reminderData, true);
        };
        host.appendChild(el);
        setTimeout(() => {
            if (el.parentElement) el.remove();
        }, 20000);
    }

    renderAll() {
        this.renderBadge();
        this.renderDropdown();
        this.renderHomepageBar();
    }

    renderBadge() {
        const wrap = document.getElementById('reminderBellWrap');
        const badge = document.getElementById('reminderBellBadge');
        if (!badge || !wrap) return;
        const n = this.pending.length;
        wrap.hidden = false;
        if (n > 0) {
            badge.hidden = false;
            badge.textContent = n > 99 ? '99+' : String(n);
        } else {
            badge.hidden = true;
        }
    }

    renderDropdown() {
        const list = document.getElementById('reminderDropdownList');
        if (!list) return;
        if (!this.pending.length) {
            list.innerHTML = '<div class="reminder-empty">暂无待处理提醒</div>';
            return;
        }
        list.innerHTML = this.pending.map((n) => `
            <div class="reminder-item" data-log-id="${n.log_id}">
                <h5>${this.escapeHtml(n.title)}</h5>
                <div class="reminder-item-time">${this.escapeHtml(this.formatTime(n.triggered_at))}</div>
                <p>${this.escapeHtml(this.stripHtml(n.message))}</p>
                <div class="reminder-item-actions">
                    <button type="button" class="primary" data-act="${n.log_id}">${this.escapeHtml(n.action_label || '去处理')}</button>
                    <button type="button" class="ghost" data-dismiss="${n.log_id}">知道了</button>
                </div>
            </div>
        `).join('');
        list.querySelectorAll('[data-act]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const item = this.pending.find((x) => String(x.log_id) === btn.getAttribute('data-act'));
                if (item) this.goToAction(item, true);
            });
        });
        list.querySelectorAll('[data-dismiss]').forEach((btn) => {
            btn.addEventListener('click', () => this.dismissReminder(Number(btn.getAttribute('data-dismiss')), false));
        });
    }

    renderHomepageBar() {
        const bar = document.getElementById('inAppReminderBar');
        if (!bar) return;
        if (this.isNativeApp() || !this.pending.length) {
            bar.hidden = true;
            bar.classList.remove('show');
            bar.innerHTML = '';
            return;
        }
        const first = this.pending[0];
        const extra = this.pending.length > 1 ? `（还有 ${this.pending.length - 1} 条）` : '';
        bar.hidden = false;
        bar.classList.add('show');
        bar.innerHTML = `
            <div class="bar-body">
                <strong>🔔 ${this.escapeHtml(first.title)}${extra}</strong>
                <p>${this.escapeHtml(this.stripHtml(first.message))}</p>
            </div>
            <div class="bar-actions">
                <button type="button" class="primary" data-act>去处理</button>
                <button type="button" class="ghost" data-dismiss>知道了</button>
            </div>
        `;
        bar.querySelector('[data-act]').onclick = () => this.goToAction(first, true);
        bar.querySelector('[data-dismiss]').onclick = () => this.dismissReminder(first.log_id, false);
    }

    formatTime(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return iso;
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    goToAction(reminderData, actionTaken) {
        if (reminderData && reminderData.reminder_type === 'test') {
            this.closeDropdown();
            return;
        }
        this.dismissReminder(reminderData.log_id, actionTaken);
        this.closeDropdown();
        const type = reminderData.reminder_type;
        if (type === 'todo') {
            if (typeof navigateTo === 'function') {
                navigateTo('overview');
                return;
            }
            window.location.href = reminderData.action_url || '/static/index.html#overview';
            return;
        }
        if (type === 'action_practice') {
            if (typeof navigateTo === 'function') {
                navigateTo('actions');
                return;
            }
            window.location.href = reminderData.action_url || '/static/index.html';
            return;
        }
        if (window.location.pathname.includes('self_talk')) return;
        window.location.href = reminderData.action_url || '/static/self_talk/index.html';
    }

    async dismissReminder(logId, actionTaken = false) {
        const token = this.authToken();
        if (!token || !logId || !Number.isFinite(Number(logId))) return;
        this.pending = this.pending.filter((n) => n.log_id !== logId);
        this.renderAll();
        try {
            await fetch(`${this.apiBase}/self_talk_reminders/dismiss/${logId}?action_taken=${actionTaken}`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
        } catch (error) {
            console.error('标记提醒失败:', error);
        }
    }
}

window.reminderNotificationService = new ReminderNotificationService();

function shuranShellInfo() {
    const ua = navigator.userAgent || '';
    const uaMatch = ua.match(/ShuranApp\/([\w.\-]+)/);
    const native = window.ShuranNative;
    const hasUpdater = !!(native && typeof native.checkUpdate === 'function');
    let versionName = '';
    let versionCode = 0;
    try {
        if (native && typeof native.getAppVersion === 'function') {
            versionName = String(native.getAppVersion() || '');
        }
        if (native && typeof native.getVersionCode === 'function') {
            versionCode = Number(native.getVersionCode()) || 0;
        }
    } catch (e) { /* ignore */ }
    if (!versionName && uaMatch) {
        versionName = uaMatch[1];
    }
    return {
        inApp: !!(native || uaMatch),
        hasUpdater: hasUpdater,
        versionName: versionName,
        versionCode: versionCode
    };
}

function shuranIsNativeApp() {
    return shuranShellInfo().inApp;
}

function shuranCopyText(text) {
    function fallback() {
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            ta.setSelectionRange(0, text.length);
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            return ok;
        } catch (e) {
            return false;
        }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function () {
            return true;
        }).catch(function () {
            return fallback();
        });
    }
    return Promise.resolve(fallback());
}

function shuranStartAppUpdate() {
    const shell = shuranShellInfo();
    const origin = window.location.origin || 'http://47.236.122.207:8000';
    const pageUrl = origin + '/download';
    if (shell.hasUpdater) {
        window.ShuranNative.checkUpdate();
        return;
    }
    if (shell.inApp) {
        shuranCopyText(pageUrl).then(function (ok) {
            window.location.href = pageUrl + '?from=app' + (ok ? '&copied=1' : '');
        });
        return;
    }
    window.location.href = pageUrl;
}

function fillAppVersionLabel() {
    const label = document.getElementById('appVersionLabel');
    if (!label) return;
    const shell = shuranShellInfo();
    const group = label.closest ? label.closest('.me-group') : null;
    const hint = group ? group.querySelector('.me-hint') : null;
    if (shell.inApp && !shell.hasUpdater && hint) {
        hint.textContent = '请复制下载链接，用手机自带的浏览器打开后安装。安装时选择「更新」，不要卸载。';
    }
    if (shell.versionName) {
        const extra = shell.hasUpdater ? '' : ' · 建议更新';
        label.textContent = '当前 ' + shell.versionName + extra;
        return;
    }
    if (shell.inApp) {
        label.textContent = '当前 1.0.0 · 建议更新';
        return;
    }
    label.textContent = '网页版';
}

window.shuranStartAppUpdate = shuranStartAppUpdate;

function startReminderServiceIfLoggedIn() {
    const token = localStorage.getItem('authToken') || localStorage.getItem('token');
    if (token) window.reminderNotificationService.start();
}

function promptLegacyNativeUpdate() {
    try {
        const shell = shuranShellInfo();
        if (!shell.inApp) return;
        if (shell.hasUpdater) return;
        if (sessionStorage.getItem('shuran_update_banner_dismissed') === '1') return;
        if (document.getElementById('shuranNativeUpdateBanner')) return;
        const bar = document.createElement('div');
        bar.id = 'shuranNativeUpdateBanner';
        bar.setAttribute('role', 'dialog');
        bar.style.cssText = [
            'position:fixed',
            'left:12px',
            'right:12px',
            'bottom:16px',
            'z-index:9999',
            'background:#1a1a2e',
            'color:#fff',
            'border-radius:14px',
            'padding:16px',
            'box-shadow:0 8px 24px rgba(0,0,0,.25)',
            'font-size:15px',
            'line-height:1.55'
        ].join(';');
        const current = shell.versionName || '1.0.0';
        bar.innerHTML = '<strong style="font-size:16px;">发现新版本</strong>'
            + '<p style="margin:8px 0 14px;opacity:.92;">当前 ' + current + '，最新 1.2.1。请复制下载链接，用手机自带的浏览器（荣耀浏览器 / Chrome）打开后安装。安装时选择「更新」，不要卸载。</p>'
            + '<div style="display:flex;gap:8px;">'
            + '<button type="button" id="shuranUpdateNowBtn" style="flex:1;border:none;border-radius:10px;padding:11px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-weight:600;">立即更新</button>'
            + '<button type="button" id="shuranUpdateLaterBtn" style="border:none;border-radius:10px;padding:11px 16px;background:#333;color:#ddd;">稍后</button>'
            + '</div>';
        document.body.appendChild(bar);
        document.getElementById('shuranUpdateNowBtn').onclick = function () {
            const btnNow = document.getElementById('shuranUpdateNowBtn');
            const origin = window.location.origin || 'http://47.236.122.207:8000';
            shuranCopyText(origin + '/download').then(function (ok) {
                if (ok && btnNow) btnNow.textContent = '链接已复制';
                shuranStartAppUpdate();
            });
        };
        document.getElementById('shuranUpdateLaterBtn').onclick = function () {
            sessionStorage.setItem('shuran_update_banner_dismissed', '1');
            bar.remove();
        };
        fetch('/download/info', { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (info) {
            if (!info || !info.versionName) return;
            const p = bar.querySelector('p');
            if (p) {
                p.textContent = '当前 ' + current + '，最新 ' + info.versionName + '。请复制下载链接，用手机自带的浏览器（荣耀浏览器 / Chrome）打开后安装。安装时选择「更新」，不要卸载。';
            }
        }).catch(function () { /* keep default copy */ });
    } catch (e) {
        console.warn('promptLegacyNativeUpdate', e);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startReminderServiceIfLoggedIn);
    document.addEventListener('DOMContentLoaded', promptLegacyNativeUpdate);
    document.addEventListener('DOMContentLoaded', fillAppVersionLabel);
} else {
    startReminderServiceIfLoggedIn();
    promptLegacyNativeUpdate();
    fillAppVersionLabel();
}
window.addEventListener('auth-check-settled', startReminderServiceIfLoggedIn);
[0, 200, 800].forEach(function (ms) {
    setTimeout(fillAppVersionLabel, ms);
});
