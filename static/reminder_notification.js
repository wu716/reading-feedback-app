/**
 * 自我提醒：轮询 pending 接口。
 * Android App（WebView + ShuranNative）走系统通知（状态栏/锁屏/通知栏），后台由 AlarmManager 触发；
 * 普通浏览器保留页面内铃铛/通知条，并在允许时使用 Notification API。
 */
(function hopOffSingapore() {
    try {
        if (/^47\.236\.122\.207(?::\d+)?$/i.test(location.host || '')) {
            location.replace('http://43.161.238.165:8000/?v=20260919i18n1');
        }
    } catch (e) { /* ignore */ }
})();

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
        this.refreshReliabilityHints();
        this.checkPendingReminders();
        this.timer = setInterval(() => this.checkPendingReminders(), this.pollInterval);
        this.isPolling = true;

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.checkPendingReminders();
                this.refreshReliabilityHints();
            }
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

    stopPollingOnly() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.isPolling = false;
    }

    nativeBridge() {
        try {
            return window.ShuranNative || null;
        } catch (e) {
            return null;
        }
    }

    hasNativeMethod(name) {
        return shuranHasNativeMethod(name);
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
                    message: '看到这条就说明系统通知已打通。若状态栏没有出现，到系统设置里打开书然的通知权限。',
                    reminder_type: 'test',
                    force: true,
                    action_url: '/static/index.html#user-center',
                    triggered_at: new Date().toISOString(),
                }));
                this.showFeedback('已请求系统通知。若状态栏没有出现，到系统设置里打开书然的通知权限。', 'success');
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
        const fromLs = localStorage.getItem('authToken') || localStorage.getItem('token');
        if (fromLs) return fromLs;
        try {
            const native = window.ShuranNative;
            if (native && native.getAuthToken) {
                const nativeToken = String(native.getAuthToken() || '');
                if (nativeToken) {
                    localStorage.setItem('authToken', nativeToken);
                    return nativeToken;
                }
            }
        } catch (e) { /* ignore */ }
        return '';
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

    applyLocalSchedule(settings) {
        if (!this.isNativeApp() || !this.hasNativeMethod('scheduleReminders')) return;
        this.syncNativeSession();
        try {
            window.ShuranNative.scheduleReminders(JSON.stringify(settings || {}));
        } catch (e) {
            console.error('写入本地闹钟失败:', e);
        }
    }

    async syncNativeSchedule() {
        if (!this.isNativeApp()) return;
        const token = this.authToken();
        this.syncNativeSession();
        if (!token) {
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
                dailyEnabled: !!settings.daily_reminder_enabled || !!settings.is_enabled,
                dailyTime: settings.daily_reminder_time || '20:00',
                reminderDays: settings.reminder_days || [0, 1, 2, 3, 4, 5, 6],
                systemNotification: settings.browser_notification !== false,
                readingEnabled: !!settings.reading_reminder_enabled,
                readingTime: settings.reading_reminder_time || '21:00',
            }));
            window.ShuranNative.requestPermission();
            window.ShuranNative.pollNow();
            this.syncNativeTodos();
            this.refreshReliabilityHints();
        } catch (e) {
            console.error('同步原生提醒失败:', e);
        }
    }

    async syncNativeTodos() {
        if (!this.isNativeApp() || !this.hasNativeMethod('scheduleTodos')) return;
        const token = this.authToken();
        if (!token) return;
        try {
            const response = await fetch(`${this.apiBase}/today/todos/scheduled`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) return;
            const todos = await response.json();
            const payload = (Array.isArray(todos) ? todos : []).map((t) => ({
                id: t.id,
                text: t.text || '',
                date: t.todo_date,
                time: t.remind_time,
                completed: !!t.completed,
            }));
            window.ShuranNative.scheduleTodos(JSON.stringify(payload));
        } catch (e) {
            console.error('同步待办闹钟失败:', e);
        }
    }

    canScheduleExactAlarms() {
        if (!this.isNativeApp() || !this.hasNativeMethod('canScheduleExactAlarms')) return true;
        try {
            return !!window.ShuranNative.canScheduleExactAlarms();
        } catch (e) {
            return true;
        }
    }

    openExactAlarmSettings() {
        if (!this.hasNativeMethod('openExactAlarmSettings')) return;
        try {
            window.ShuranNative.openExactAlarmSettings();
        } catch (e) {
            console.error('打开精确闹钟设置失败:', e);
        }
    }

    openNotificationSettings() {
        if (this.hasNativeMethod('openNotificationSettings')) {
            try {
                window.ShuranNative.openNotificationSettings();
                return;
            } catch (e) {
                console.error('打开通知设置失败:', e);
            }
        }
        if (this.hasNativeMethod('requestPermission')) {
            try { window.ShuranNative.requestPermission(); } catch (e) {}
        }
    }

    openBatteryOptimizationSettings() {
        if (!this.hasNativeMethod('openBatteryOptimizationSettings')) return;
        try {
            window.ShuranNative.openBatteryOptimizationSettings();
        } catch (e) {
            console.error('打开电池优化设置失败:', e);
        }
    }

    openAutostartSettings() {
        if (!this.hasNativeMethod('openAutostartSettings')) return;
        try {
            window.ShuranNative.openAutostartSettings();
        } catch (e) {
            console.error('打开自启动设置失败:', e);
        }
    }

    reliabilityStatus() {
        if (!this.isNativeApp() || !this.hasNativeMethod('reminderReliabilityStatus')) return null;
        try {
            const raw = window.ShuranNative.reminderReliabilityStatus();
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    refreshExactAlarmHint() {
        this.refreshReliabilityHints();
    }

    refreshReliabilityHints() {
        const box = document.getElementById('reminderReliabilityBox');
        const native = this.isNativeApp();
        if (box) box.hidden = !native;
        if (!native) return;

        const status = this.reliabilityStatus() || {
            notifications: this.hasNativeMethod('hasPermission') ? !!window.ShuranNative.hasPermission() : false,
            exactAlarms: this.canScheduleExactAlarms(),
            batteryIgnored: this.hasNativeMethod('isIgnoringBatteryOptimizations')
                ? !!window.ShuranNative.isIgnoringBatteryOptimizations()
                : true,
        };

        const setRow = (descId, btnId, ok, okText, badText) => {
            const desc = document.getElementById(descId);
            const btn = document.getElementById(btnId);
            if (desc) desc.textContent = ok ? okText : badText;
            if (btn) {
                btn.textContent = ok ? '已开启' : '去开启';
                btn.disabled = !!ok;
            }
        };
        setRow(
            'notifyPermDesc',
            'notifyPermBtn',
            !!status.notifications,
            '已允许，提醒会显示在状态栏',
            '未允许时到点也不会弹出'
        );
        setRow(
            'exactAlarmDesc',
            'exactAlarmBtn',
            !!status.exactAlarms,
            '已允许，到点会准时触发',
            '未开启时，到点提醒可能被推迟到打开应用才出现'
        );
        const batteryDesc = document.getElementById('batteryOptDesc');
        const batteryBtn = document.getElementById('batteryOptBtn');
        if (batteryDesc) {
            batteryDesc.textContent = status.batteryIgnored
                ? '已忽略电池优化，后台被杀后仍更可能响'
                : '系统省电会取消已设定的闹钟，请关闭优化';
        }
        if (batteryBtn) {
            batteryBtn.textContent = status.batteryIgnored ? '已关闭' : '去关闭';
            batteryBtn.disabled = !!status.batteryIgnored;
        }
    }

    promptReliabilityIfNeeded() {
        this.refreshReliabilityHints();
        if (!this.isNativeApp()) return;
        const status = this.reliabilityStatus();
        if (!status) return;
        if (!status.notifications) {
            this.showFeedback('请先允许通知权限，否则到点无法弹出状态栏提醒。', 'error');
            this.openNotificationSettings();
            return;
        }
        if (!status.exactAlarms) {
            this.showFeedback('请开启精确闹钟，否则退出 App 后可能不准时提醒。', 'info');
            return;
        }
        if (!status.batteryIgnored) {
            this.showFeedback('请关闭电池优化并允许自启动。国产手机划掉后台后，不关省电就不会响。', 'info');
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
        if (bellBtn && dropdown && !bellBtn.dataset.reminderBound) {
            bellBtn.dataset.reminderBound = '1';
            bellBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleDropdown();
            });
        }
        const settingsLink = document.getElementById('reminderSettingsLink');
        if (settingsLink && !settingsLink.dataset.reminderBound) {
            settingsLink.dataset.reminderBound = '1';
            settingsLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.openSettings();
            });
        }
        const closeBtn = document.getElementById('reminderDropdownClose');
        if (closeBtn) {
            closeBtn.textContent = '收起';
            closeBtn.setAttribute('aria-label', '收起');
            if (!closeBtn.dataset.reminderBound) {
                closeBtn.dataset.reminderBound = '1';
                closeBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.closeDropdown();
                });
            }
        }
        this.ensureBackdrop();
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
            .reminder-bell-btn { position: relative; width: 40px; height: 40px; border: none; border-radius: 0; background: transparent; color: #f3efe6; cursor: pointer; display: flex; align-items: center; justify-content: center; }
            .reminder-bell-icon { width: 22px; height: 22px; display: block; }
            .reminder-bell-badge { position: absolute; top: 7px; right: 8px; width: 7px; height: 7px; min-width: 0; padding: 0; background: #9c3b32; color: transparent; font-size: 0; line-height: 0; border-radius: 50%; box-shadow: 0 0 0 2px #6b63c4; }
            .reminder-backdrop { display: none; position: fixed; inset: 0; background: rgba(28,27,25,0.4); z-index: 1290; }
            .reminder-backdrop.is-open { display: block; }
            .reminder-dropdown { position: absolute; top: calc(100% + 8px); right: 0; left: auto; width: 360px; max-width: calc(100vw - 24px); box-sizing: border-box; background: #fff; color: #333; border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,0.18); z-index: 1300; overflow: hidden; flex-direction: column; display: none; }
            .reminder-dropdown.is-open { display: flex !important; }
            .reminder-dropdown[hidden] { display: none !important; }
            .reminder-dropdown-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #eee; font-size: 0.95rem; flex-shrink: 0; }
            .reminder-dropdown-head-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
            .reminder-dropdown-head a { color: #667eea; text-decoration: none; font-size: 0.85rem; }
            .reminder-dropdown-close { min-width: 52px; height: 32px; border: none; border-radius: 8px; background: #f0f0f0; color: #374151; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
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
            <button type="button" class="header-icon-btn reminder-bell-btn" id="reminderBellBtn" aria-label="提醒" title="提醒"><svg class="reminder-bell-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" d="M7 17h10l-1.15-1.35V11a4.85 4.85 0 0 0-3.6-4.7V5.6a1.25 1.25 0 0 0-2.5 0v.7A4.85 4.85 0 0 0 6.15 11v4.65L5 17"/><path fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" d="M10.2 17.4a1.8 1.8 0 0 0 3.6 0"/></svg><span class="reminder-bell-badge" id="reminderBellBadge" hidden></span></button>
            <div class="reminder-dropdown" id="reminderDropdown" hidden>
                <div class="reminder-dropdown-head">
                    <strong>提醒</strong>
                    <div class="reminder-dropdown-head-actions">
                        <a href="#" id="reminderSettingsLink">提醒设置</a>
                        <button type="button" class="reminder-dropdown-close" id="reminderDropdownClose" aria-label="收起">收起</button>
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

    ensureBackdrop() {
        let backdrop = document.getElementById('reminderBackdrop');
        if (backdrop) return backdrop;
        backdrop = document.createElement('div');
        backdrop.id = 'reminderBackdrop';
        backdrop.className = 'reminder-backdrop';
        backdrop.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            this.closeDropdown();
        });
        document.body.appendChild(backdrop);
        return backdrop;
    }

    isDropdownOpen() {
        const dropdown = document.getElementById('reminderDropdown');
        return !!(dropdown && dropdown.classList.contains('is-open'));
    }

    toggleDropdown() {
        if (this.isDropdownOpen()) this.closeDropdown();
        else this.openDropdown();
    }

    openDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (!dropdown) return;
        dropdown.hidden = false;
        dropdown.removeAttribute('hidden');
        dropdown.classList.add('is-open');
        this.dropdownOpen = true;
        const backdrop = this.ensureBackdrop();
        backdrop.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        const btn = document.getElementById('reminderBellBtn');
        if (btn) btn.setAttribute('aria-expanded', 'true');
        this.positionDropdown();
    }

    closeDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (dropdown) {
            dropdown.hidden = true;
            dropdown.classList.remove('is-open');
        }
        this.dropdownOpen = false;
        const backdrop = document.getElementById('reminderBackdrop');
        if (backdrop) backdrop.classList.remove('is-open');
        document.body.style.overflow = '';
        const btn = document.getElementById('reminderBellBtn');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    isNarrowViewport() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    positionDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (!dropdown || !this.isDropdownOpen()) return;

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
                this.stopPollingOnly();
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
        badge.hidden = n === 0;
        badge.textContent = '';
        const btn = document.getElementById('reminderBellBtn');
        if (btn) {
            btn.setAttribute('aria-label', n > 0 ? `提醒，${n} 条未读` : '提醒');
            btn.title = n > 0 ? `提醒 · ${n}` : '提醒';
        }
        const head = document.querySelector('#reminderDropdown .reminder-dropdown-head strong');
        if (head) head.textContent = n > 0 ? `提醒 ${n}` : '提醒';
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
                <strong>${this.escapeHtml(first.title)}${extra}</strong>
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
        if (type === 'todo' || type === 'reading') {
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

function shuranHasNativeMethod(name) {
    try {
        const native = window.ShuranNative;
        if (!native) return false;
        const value = native[name];
        if (typeof value === 'function') return true;
        // Android addJavascriptInterface 在部分 WebView（荣耀/华为）上 typeof 不是 function。
        return value != null;
    } catch (e) {
        return false;
    }
}

function shuranCallNative(name) {
    try {
        if (!window.ShuranNative || !shuranHasNativeMethod(name)) return false;
        window.ShuranNative[name]();
        return true;
    } catch (e) {
        return false;
    }
}

function shuranShellInfo() {
    const ua = navigator.userAgent || '';
    const uaMatch = ua.match(/ShuranApp\/([\w.\-]+)/);
    const native = window.ShuranNative;
    const hasUpdater = shuranHasNativeMethod('checkUpdate');
    let versionName = '';
    let versionCode = 0;
    try {
        if (shuranHasNativeMethod('getAppVersion')) {
            versionName = String(native.getAppVersion() || '');
        }
        if (shuranHasNativeMethod('getVersionCode')) {
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

function shuranIsPhoneApp() {
    return shuranShellInfo().inApp;
}

function shuranVersionLess(current, latest) {
    const pa = String(current || '0').split(/[^\d]+/).map(function (n) { return parseInt(n, 10) || 0; });
    const pb = String(latest || '0').split(/[^\d]+/).map(function (n) { return parseInt(n, 10) || 0; });
    const n = Math.max(pa.length, pb.length);
    for (let i = 0; i < n; i++) {
        const x = pa[i] || 0;
        const y = pb[i] || 0;
        if (x < y) return true;
        if (x > y) return false;
    }
    return false;
}

function shuranMinShell(latest) {
    const floorCode = Number(window.SHURAN_MIN_SHELL_CODE) || 20;
    const floorName = String(window.SHURAN_MIN_SHELL_NAME || '1.5.4');
    const remoteMinCode = Number(latest && latest.minVersionCode) || 0;
    const remoteLatest = Number(latest && latest.versionCode) || 0;
    const remoteMinName = String((latest && latest.minVersionName) || '');
    // 仅当服务端明确把门槛设得低于「最新包」时才抬高门槛。
    // 旧接口曾把 minVersionCode 写成 latest.versionCode，那会让每发一版都锁死全员。
    let minCode = floorCode;
    if (remoteMinCode > minCode && (remoteLatest === 0 || remoteMinCode < remoteLatest)) {
        minCode = remoteMinCode;
    }
    let minName = floorName;
    if (remoteMinName && shuranVersionLess(floorName, remoteMinName)
            && (!latest || !latest.versionName || shuranVersionLess(remoteMinName, latest.versionName))) {
        minName = remoteMinName;
    }
    return { minCode: minCode, minName: minName };
}

function shuranTriggerNativeInstall() {
    if (shuranCallNative('checkUpdate')) return true;
    try {
        window.ShuranNative.checkUpdate();
        return true;
    } catch (e) { /* ignore */ }
    return false;
}

function shuranMarkUpdateButtonBusy(btn) {
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = '正在打开安装…';
    btn.style.opacity = '0.85';
}

function shuranSetUpdateGateStatus(text, isError) {
    const status = document.getElementById('shuranUpdateGateStatus');
    if (!status) return;
    status.textContent = text || '';
    status.style.display = text ? 'block' : 'none';
    status.style.color = isError ? '#ffb4b4' : 'rgba(255,255,255,0.88)';
}

function shuranClearShellUpdateGate() {
    const existing = document.getElementById('shuranShellUpdateGate');
    if (existing) existing.remove();
    window.SHURAN_SHELL_GATE_LOCKED = false;
}

function shuranStartAppUpdate(btn) {
    if (!shuranIsPhoneApp()) {
        if (typeof showMessage === 'function') {
            showMessage('电脑请下载 Windows 应用（我的 → Windows 应用），或刷新网页。安装包只给安卓手机。', 'info');
        }
        return;
    }
    const target = btn || document.getElementById('shuranUpdateNowBtn')
        || document.getElementById('shuranShellUpdateLink');
    shuranMarkUpdateButtonBusy(target);
    shuranSetUpdateGateStatus('正在应用内下载安装包…', false);
    if (shuranTriggerNativeInstall()) {
        // 安装界面返回后若仍过旧，定时再检查并给出明确提示，避免无声死循环。
        let tries = 0;
        const timer = setInterval(function () {
            tries += 1;
            const shell = shuranShellInfo();
            if (!shuranShellNeedsUpdate(shell)) {
                clearInterval(timer);
                shuranClearShellUpdateGate();
                return;
            }
            if (tries >= 8) {
                clearInterval(timer);
                if (target) {
                    target.disabled = false;
                    target.textContent = '重试更新';
                    target.style.opacity = '1';
                }
                shuranSetUpdateGateStatus(
                    '还没装上新版本。请确认系统安装窗口里点了「安装」。也可先继续使用，或用系统浏览器打开 http://43.161.238.165:8000/download 覆盖安装。',
                    true
                );
                shuranShowContinueUsing();
            }
        }, 2500);
        return;
    }
    // 极旧外壳没有原生更新器：留在挡板并给出可复制地址，禁止再跳浏览器/下载页死循环。
    if (target) {
        target.disabled = false;
        target.textContent = '重试更新';
        target.style.opacity = '1';
    }
    shuranSetUpdateGateStatus(
        '当前外壳无法应用内安装。可先继续使用书然；或用手机系统浏览器打开 http://43.161.238.165:8000/download 下载后覆盖安装。',
        true
    );
    shuranShowContinueUsing();
}

function shuranShowContinueUsing() {
    const bar = document.getElementById('shuranShellUpdateGate');
    if (!bar || document.getElementById('shuranContinueUsingBtn')) return;
    const wrap = bar.firstElementChild;
    if (!wrap) return;
    const skip = document.createElement('button');
    skip.id = 'shuranContinueUsingBtn';
    skip.type = 'button';
    skip.textContent = '先继续使用';
    skip.style.cssText = 'width:100%;margin-top:12px;border:1px solid rgba(255,255,255,0.35);border-radius:12px;padding:12px 16px;background:transparent;color:#fff;font-size:1rem;';
    skip.onclick = function () {
        window.SHURAN_SHELL_GATE_DISMISSED = true;
        shuranClearShellUpdateGate();
    };
    wrap.appendChild(skip);
}

window.SHURAN_VERSION = window.SHURAN_VERSION || '1.5.0';
window.SHURAN_MIN_SHELL_CODE = 20;
window.SHURAN_MIN_SHELL_NAME = '1.5.4';

function shuranIsOwner() {
    try {
        return !!(window.currentUser && window.currentUser.is_owner);
    } catch (e) {
        return false;
    }
}

function fillAppVersionLabel() {
    const label = document.getElementById('appVersionLabel');
    if (!label) return;
    const version = window.SHURAN_VERSION || '1.5.0';
    const shell = shuranShellInfo();
    const group = label.closest ? label.closest('.me-group') : null;
    const hint = document.getElementById('appVersionHint')
        || (group ? group.querySelector('.me-hint') : null);
    const btn = document.getElementById('appUpdateBtn');
    const title = group ? group.querySelector('.me-row-title') : null;
    if (title && (title.textContent === '版本更新' || title.textContent === '当前内容')) {
        title.textContent = '版本';
    }
    const cardTitle = document.querySelector('#appUpdateCard h2');
    if (cardTitle && (cardTitle.textContent === '当前内容' || cardTitle.textContent === '版本更新')) {
        cardTitle.textContent = '版本';
    }

    const row = document.getElementById('appVersionRow');
    const card = document.getElementById('appUpdateCard');
    const isOwner = shuranIsOwner();
    if (!isOwner) {
        if (row) row.hidden = true;
        if (hint) hint.hidden = true;
        if (btn) btn.hidden = true;
        if (card) card.hidden = true;
        label.textContent = '';
        return;
    }

    if (card) card.hidden = false;
    if (row) {
        row.hidden = false;
        row.classList.remove('me-row-static');
    }
    if (shell.versionName) {
        label.textContent = '调试 页面 ' + version + ' · 安装包 ' + shell.versionName;
    } else {
        label.textContent = '调试 页面 ' + version;
    }

    const outdated = shuranShellNeedsUpdate(shell);
    if (btn) {
        btn.hidden = true;
        btn.textContent = '立即更新';
    }
    if (hint) {
        hint.hidden = false;
        if (shell.inApp && outdated) {
            hint.textContent = '安装包过旧。点这一行下载后覆盖即可，不用卸载，登录会保留。';
        } else if (shell.inApp) {
            hint.textContent = '点这一行可下载安装包。覆盖即可，不用卸载，登录会保留。';
        } else {
            hint.textContent = '点这一行可下载安装包。电脑请用「我的 → Windows 应用」。';
        }
    }
}

window.shuranStartAppUpdate = shuranStartAppUpdate;
window.shuranPromptShellUpdate = shuranPromptShellUpdate;

function startReminderServiceIfLoggedIn() {
    const token = localStorage.getItem('authToken') || localStorage.getItem('token');
    if (token) window.reminderNotificationService.start();
}

function shuranShellNeedsUpdate(shell, latest) {
    shell = shell || shuranShellInfo();
    if (!shell.inApp) return false;
    if (window.SHURAN_SHELL_GATE_DISMISSED) return false;
    const min = shuranMinShell(latest);
    const code = Number(shell.versionCode) || 0;
    const name = String(shell.versionName || '');
    if (code > 0 && code >= min.minCode) return false;
    if (name && !shuranVersionLess(name, min.minName)) return false;
    if (code > 0 && code < min.minCode) return true;
    if (name && shuranVersionLess(name, min.minName)) return true;
    // 读不到版本时不要锁死整页：荣耀/华为 WebView 上 JS 桥方法可能检测失败。
    return false;
}

function shuranPromptShellUpdate(force) {
    try {
        if (window.SHURAN_SHELL_GATE_DISMISSED) return;
        if (!shuranShellInfo().inApp) return;
        const apply = function (latest) {
            // 每次重读外壳版本：装完 1.5.4 后必须能拆掉挡板，不能沿用进页时的旧 shell。
            const shell = shuranShellInfo();
            if (!shuranShellNeedsUpdate(shell, latest)) {
                shuranClearShellUpdateGate();
                return;
            }
            let bar = document.getElementById('shuranShellUpdateGate');
            if (!bar) {
                bar = document.createElement('div');
                bar.id = 'shuranShellUpdateGate';
                bar.setAttribute('role', 'dialog');
                bar.setAttribute('aria-modal', 'true');
                document.body.appendChild(bar);
            }
            bar.setAttribute('data-locked', '1');
            window.SHURAN_SHELL_GATE_LOCKED = true;
            bar.style.cssText = [
                'position:fixed',
                'inset:0',
                'z-index:2147483000',
                'background:#1a1a2e',
                'color:#fff',
                'display:flex',
                'flex-direction:column',
                'justify-content:center',
                'padding:28px 22px',
                'box-sizing:border-box'
            ].join(';');
            const packageMissing = latest && latest.available === false;
            const bodyText = packageMissing
                ? '服务器上的新安装包还没就绪。可先继续使用书然，或用系统浏览器打开 http://43.161.238.165:8000/download 下载后覆盖安装。'
                : '请点一次，在应用内覆盖安装最新书然。登录会保留，不必卸载。若又弹出「需要更新」窗口，请再点「立即更新」（不要点「稍后」）。系统若询问安装权限，请允许。';
            bar.innerHTML = '<div style="max-width:420px;margin:0 auto;width:100%;">'
                + '<h1 style="font-size:1.45rem;margin:0 0 12px;">需要更新书然</h1>'
                + '<p style="line-height:1.65;opacity:.92;margin:0 0 22px;">' + bodyText + '</p>'
                + '<button type="button" id="shuranUpdateNowBtn" style="width:100%;border:none;border-radius:12px;padding:14px 16px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-size:1.05rem;font-weight:700;">'
                + (packageMissing ? '我知道了' : '立即更新')
                + '</button>'
                + '<button type="button" id="shuranContinueUsingBtn" style="width:100%;margin-top:12px;border:1px solid rgba(255,255,255,0.35);border-radius:12px;padding:12px 16px;background:transparent;color:#fff;font-size:1rem;">先继续使用</button>'
                + '<p id="shuranUpdateGateStatus" style="display:none;margin:14px 0 0;line-height:1.5;font-size:0.92rem;"></p>'
                + '</div>';
            const btn = document.getElementById('shuranUpdateNowBtn');
            if (btn) {
                btn.onclick = function () {
                    if (packageMissing) {
                        window.SHURAN_SHELL_GATE_DISMISSED = true;
                        shuranClearShellUpdateGate();
                        return;
                    }
                    shuranStartAppUpdate(btn);
                };
            }
            const skip = document.getElementById('shuranContinueUsingBtn');
            if (skip) {
                skip.onclick = function () {
                    window.SHURAN_SHELL_GATE_DISMISSED = true;
                    shuranClearShellUpdateGate();
                };
            }
        };
        apply(null);
        fetch('/download/info', { cache: 'no-store' })
            .then(function (res) { return res.ok ? res.json() : {}; })
            .then(apply)
            .catch(function () { apply(null); });
    } catch (e) {
        console.warn('shuranPromptShellUpdate', e);
    }
}

function promptLegacyNativeUpdate() {
    shuranPromptShellUpdate(false);
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
window.addEventListener('auth-check-settled', promptLegacyNativeUpdate);
[0, 200, 800, 2000, 4000].forEach(function (ms) {
    setTimeout(fillAppVersionLabel, ms);
    setTimeout(promptLegacyNativeUpdate, ms);
});
