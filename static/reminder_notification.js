/**
 * Self-talk 提醒通知服务
 * 轮询后端API获取待处理的提醒并显示浏览器通知
 */

class ReminderNotificationService {
    constructor() {
        this.pollInterval = 2 * 60 * 1000; // 2分钟轮询一次
        this.timer = null;
        this.isPolling = false;
        this.apiBase = '/api';
    }

    /**
     * 启动通知服务
     */
    start() {
        if (this.isPolling) {
            console.log('通知服务已在运行');
            return;
        }

        console.log('启动 Self-talk 提醒通知服务');
        
        // 请求通知权限
        this.requestNotificationPermission();
        
        // 立即检查一次
        this.checkPendingReminders();
        
        // 开始定时轮询
        this.timer = setInterval(() => {
            this.checkPendingReminders();
        }, this.pollInterval);
        
        this.isPolling = true;
    }

    /**
     * 停止通知服务
     */
    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.isPolling = false;
        console.log('通知服务已停止');
    }

    /**
     * 请求浏览器通知权限
     */
    async requestNotificationPermission() {
        if (!('Notification' in window)) {
            console.warn('浏览器不支持通知功能');
            return false;
        }

        if (Notification.permission === 'granted') {
            return true;
        }

        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        }

        return false;
    }

    /**
     * 检查待处理的提醒
     */
    async checkPendingReminders() {
        const token = localStorage.getItem('token') || localStorage.getItem('authToken');
        if (!token) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/self_talk_reminders/pending`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.pending_count > 0) {
                    console.log(`发现 ${data.pending_count} 条待处理提醒`);
                    this.handlePendingReminders(data.notifications);
                }
            } else if (response.status === 401) {
                // 未授权，停止轮询
                this.stop();
            }
        } catch (error) {
            console.error('检查待处理提醒失败:', error);
        }
    }

    /**
     * 处理待处理的提醒
     */
    async handlePendingReminders(notifications) {
        for (const notification of notifications) {
            await this.showNotification(notification);
        }
    }

    /**
     * 显示浏览器通知
     */
    async showNotification(reminderData) {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            // 浏览器不支持或没有权限，使用页面内通知
            this.showInPageNotification(reminderData);
            return;
        }

        try {
            const notification = new Notification(reminderData.title, {
                body: reminderData.message,
                icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🎤</text></svg>',
                badge: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🔔</text></svg>',
                tag: `reminder-${reminderData.log_id}`,
                requireInteraction: true,
                silent: false
            });

            // 点击通知时跳转到 self-talk 页面
            notification.onclick = () => {
                window.focus();
                window.location.href = '/static/self_talk/index.html';
                notification.close();
                this.dismissReminder(reminderData.log_id, true);
            };

            // 自动关闭后标记为已忽略
            notification.onclose = () => {
                this.dismissReminder(reminderData.log_id, false);
            };

        } catch (error) {
            console.error('显示浏览器通知失败:', error);
            this.showInPageNotification(reminderData);
        }
    }

    /**
     * 显示页面内通知（当浏览器通知不可用时）
     */
    showInPageNotification(reminderData) {
        // 创建通知元素
        const notificationEl = document.createElement('div');
        notificationEl.className = 'in-page-notification';
        notificationEl.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            max-width: 350px;
            z-index: 9999;
            border-left: 4px solid #667eea;
            animation: slideInRight 0.3s ease;
        `;

        notificationEl.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                <h4 style="margin: 0; color: #667eea; font-size: 1.1rem;">${reminderData.title}</h4>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #999;">×</button>
            </div>
            <p style="margin: 0 0 15px 0; color: #555; line-height: 1.5;">${reminderData.message}</p>
            <div style="display: flex; gap: 10px;">
                <button onclick="window.location.href='/static/self_talk/index.html'" style="flex: 1; background: #667eea; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer;">
                    立即记录
                </button>
                <button onclick="this.closest('.in-page-notification').remove()" style="flex: 1; background: #f0f0f0; color: #666; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer;">
                    稍后提醒
                </button>
            </div>
        `;

        document.body.appendChild(notificationEl);

        // 添加动画
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideInRight {
                from {
                    transform: translateX(400px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
        `;
        document.head.appendChild(style);

        // 10秒后自动关闭
        setTimeout(() => {
            if (notificationEl.parentElement) {
                notificationEl.remove();
                this.dismissReminder(reminderData.log_id, false);
            }
        }, 10000);
    }

    /**
     * 标记提醒为已处理
     */
    async dismissReminder(logId, actionTaken = false) {
        const token = localStorage.getItem('token') || localStorage.getItem('authToken');
        if (!token) return;

        try {
            await fetch(`${this.apiBase}/self_talk_reminders/dismiss/${logId}?action_taken=${actionTaken}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        } catch (error) {
            console.error('标记提醒失败:', error);
        }
    }
}

// 创建全局实例
window.reminderNotificationService = new ReminderNotificationService();

// 页面加载完成后自动启动
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        // 检查是否已登录
        const token = localStorage.getItem('token') || localStorage.getItem('authToken');
        if (token) {
            window.reminderNotificationService.start();
        }
    });
} else {
    // 已经加载完成
    const token = localStorage.getItem('token') || localStorage.getItem('authToken');
    if (token) {
        window.reminderNotificationService.start();
    }
}

