/**
 * 应用内自我提醒：轮询 pending 接口，首页通知条 + 铃铛列表必显示；
 * 浏览器允许时额外弹出 Notification，拒绝权限也不影响页面内提醒。
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
            this.checkPendingReminders();
            return;
        }
        this.requestNotificationPermission();
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
        if (!('Notification' in window)) return false;
        if (Notification.permission === 'granted') return true;
        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        }
        return false;
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
        document.addEventListener('click', (e) => {
            const wrap = document.getElementById('reminderBellWrap');
            if (wrap && !wrap.contains(e.target)) this.closeDropdown();
        });

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
            .reminder-dropdown { position: absolute; top: calc(100% + 8px); right: 0; width: min(360px, calc(100vw - 24px)); background: #fff; color: #333; border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,0.18); z-index: 1200; overflow: hidden; }
            .reminder-dropdown-head { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border-bottom: 1px solid #eee; font-size: 0.95rem; }
            .reminder-dropdown-head a { color: #667eea; text-decoration: none; font-size: 0.85rem; }
            .reminder-dropdown-list { max-height: 360px; overflow-y: auto; }
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
            .reminder-bell-wrap.floating { position: fixed; right: 16px; bottom: 20px; z-index: 1100; }
            .reminder-bell-wrap.floating .reminder-bell-btn { background: #667eea; width: 48px; height: 48px; border-radius: 50%; box-shadow: 0 4px 14px rgba(102,126,234,0.4); }
            .reminder-bell-wrap.floating .reminder-dropdown { top: auto; bottom: calc(100% + 8px); }
            @keyframes inAppSlideIn { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
            @media (max-width: 768px) {
                .in-app-toast-host { top: 76px; left: 12px; right: 12px; }
                .in-page-notification { max-width: none; }
                .in-app-reminder-bar { flex-direction: column; }
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
                    <strong>应用内提醒</strong>
                    <a href="#" id="reminderSettingsLink">提醒设置</a>
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
            wrap.classList.add('floating');
            document.body.appendChild(wrap);
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
    }

    closeDropdown() {
        const dropdown = document.getElementById('reminderDropdown');
        if (dropdown) dropdown.hidden = true;
        this.dropdownOpen = false;
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
                    if (list[0]) this.announceNew(list[0]);
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
        this.showInPageToast(notification);
        this.maybeShowOsNotification(notification);
    }

    maybeShowOsNotification(reminderData) {
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
        if (!this.pending.length) {
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
        this.dismissReminder(reminderData.log_id, actionTaken);
        this.closeDropdown();
        const type = reminderData.reminder_type;
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
        if (!token || !logId) return;
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

function startReminderServiceIfLoggedIn() {
    const token = localStorage.getItem('authToken') || localStorage.getItem('token');
    if (token) window.reminderNotificationService.start();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startReminderServiceIfLoggedIn);
} else {
    startReminderServiceIfLoggedIn();
}
window.addEventListener('auth-check-settled', startReminderServiceIfLoggedIn);
