(function () {
    const STORAGE_KEY = 'shuran.language';
    const DEFAULT_LANGUAGE = 'zh-CN';
    const SUPPORTED = ['zh-CN', 'en'];

    const messages = {
        'zh-CN': {
            'app.title': '书然',
            'app.tagline': '把读书笔记，变成真正在做的行动',
            'auth.colophon': '开卷有益 · 知行合一',
            'nav.collapse': '收起导航',
            'nav.back': '返回',
            'nav.today': '今日',
            'nav.schedule': '日程',
            'nav.actions': '行动',
            'nav.upload': '上传笔记',
            'nav.selfTalk': 'Self-talk',
            'nav.me': '我的',
            'nav.capture': '记',
            'tabbar.aria': '出门时用',
            'schedule.title': '日程安排',
            'upload.title': '读书笔记',
            'reminder.title': '提醒',
            'reminder.settings': '提醒设置',
            'reminder.collapse': '收起',
            'common.close': '关闭',
            'common.cancel': '取消',
            'common.save': '保存',
            'common.update': '更新',
            'common.enable': '去开启',
            'common.turnOff': '去关闭',
            'common.settings': '去设置',
            'status.checking': '检测中…',
            'auth.entry.title': '入册',
            'auth.entry.desc': '登录已有账户，或注册开启书然',
            'auth.login.tab': '登录',
            'auth.register.tab': '注册',
            'auth.login.title': '入册',
            'auth.login.desc': '手机号或邮箱登录，新用户需邀请码',
            'auth.register.title': '开卷',
            'auth.register.desc': '用手机号和邀请码注册',
            'auth.account.label': '手机号或邮箱',
            'auth.account.placeholder': '手机号或邮箱',
            'auth.password.label': '密码',
            'auth.password.placeholder': '密码',
            'auth.password.hint': '至少 6 位，建议字母与数字搭配',
            'auth.password.show': '显示密码',
            'auth.password.hide': '隐藏密码',
            'auth.phone.label': '手机号',
            'auth.phone.placeholder': '11 位手机号',
            'auth.name.label': '真实姓名',
            'auth.name.placeholder': '姓名',
            'auth.invite.label': '邀请码',
            'auth.invite.placeholder': '4 位数字邀请码',
            'auth.login.submit': '登录',
            'auth.login.loading': '登录中...',
            'auth.register.submit': '注册',
            'auth.register.loading': '注册中...',
            'auth.logout': '退出登录',
            'auth.logout.confirm': '退出当前账号？',
            'auth.logout.confirmButton': '确定退出',
            'me.profile.loading': '加载中…',
            'me.editName': '修改昵称',
            'me.language.group': '语言',
            'me.language.title': '界面语言',
            'me.language.desc': '切换后会保存在本机。',
            'me.language.zh': '中文',
            'me.language.en': 'English',
            'me.account.group': '账户与套餐',
            'me.quota.today': '今日额度',
            'me.plan.hint': '付费和续期在微信产品群找站长开通，开通后当天额度按新套餐生效。',
            'me.plans.plan': '套餐',
            'me.plans.price': '价格',
            'me.plans.extracts': '抽取 / 天',
            'me.plans.advice': '建议 / 天',
            'me.plans.duration': '时长',
            'me.bindPhone.group': '绑定手机号',
            'me.bindPhone.hint': '绑定后可用手机号登录。一个号码只能绑定一个账户。验证码绑定稍后开放。',
            'me.bindPhone.placeholder': '11 位手机号',
            'me.bindPhone.action': '绑定',
            'me.quick.today.title': '今日',
            'me.quick.today.desc': '日历、待办和今天的进展',
            'me.quick.actions.title': '行动',
            'me.quick.actions.desc': '坐下时在电脑上更好做',
            'me.quick.upload.title': '上传笔记',
            'me.quick.upload.desc': '从笔记抽出行动项',
            'me.menu.owner': '站长开通',
            'me.menu.timeLog': '时间日志',
            'me.menu.ideas': '灵感',
            'me.menu.stats': '实践统计',
            'me.menu.dashboard': '数据看板',
            'me.menu.guide': '使用说明',
            'me.version.title': '版本',
            'me.windows.title': 'Windows 应用',
            'me.windows.desc': '电脑请用这个打开。出门用手机看日程和「记」。',
            'me.windows.running.title': '已在 Windows 应用中',
            'me.windows.running.desc': '全局 Ctrl+Shift+K 打开「记」。窗口内也可用 Ctrl+K。',
            'me.windows.hint': '不要用电脑管家打开安卓安装包。坐下做事用 Windows 应用，出门用手机。',
            'me.capture.group': '快捷记下',
            'me.capture.default.title': '默认记下',
            'me.capture.default.desc': '三击或点「记」时先落到时刻，仍可当场改。',
            'me.capture.volume.title': '三击音量减 → 记',
            'me.capture.volume.desc': '书然开着时，约 1.5 秒内连按三下音量减即可打开「记」。',
            'me.capture.updateApp': '换安装包',
            'capture.kind.moment': '时刻',
            'capture.kind.idea': '灵感',
            'capture.kind.todo': '待办',
            'me.reminders.group': '提醒',
            'me.reminders.hint': '待办时间在添加时单独设置；阅读时间在今日待办里设置。到点后会弹出系统通知。',
            'me.reminders.enable': '启用提醒',
            'me.reminders.dailyGroup': '每日提醒',
            'me.reminders.daily': '每天提醒',
            'me.reminders.time': '提醒时间',
            'me.reminders.repeat': '重复',
            'me.reminders.repeatDays': '重复日期',
            'weekday.sun.short': '日',
            'weekday.mon.short': '一',
            'weekday.tue.short': '二',
            'weekday.wed.short': '三',
            'weekday.thu.short': '四',
            'weekday.fri.short': '五',
            'weekday.sat.short': '六',
            'me.actionReminders.group': '行动提醒',
            'me.actionReminders.afterDone': '完成行动后',
            'me.actionReminders.afterNew': '新增行动后',
            'me.actionReminders.inactive': '非活跃提醒',
            'me.actionReminders.inactiveDesc': '超过设定天数未使用时提醒',
            'me.notifications.group': '通知',
            'me.notifications.hint': '系统通知出现在状态栏与锁屏。网页版会在应用内提示。',
            'me.notifications.reliabilityHint': '退出 App 后也要到点提醒，请完成下面几项。荣耀 / 华为 / 小米等国产系统默认会杀掉后台闹钟。',
            'me.notifications.permission': '通知权限',
            'me.notifications.exactAlarm': '精确闹钟',
            'me.notifications.exactAlarmDesc': '未开启时，到点提醒可能被推迟到打开应用才出现',
            'me.notifications.battery': '关闭电池优化',
            'me.notifications.batteryDesc': '系统省电会取消已设定的闹钟',
            'me.notifications.autostart': '允许自启动',
            'me.notifications.autostartDesc': '划掉后台后仍要响：允许书然自启动 / 关联启动',
            'me.notifications.system': '系统通知',
            'me.notifications.email': '邮件通知',
            'me.password.group': '修改密码',
            'me.password.hint': '改密后，其它已登录设备会退出。',
            'me.password.old': '当前密码',
            'me.password.new': '新密码（至少 6 位）'
        },
        en: {
            'app.title': 'Shuran',
            'app.tagline': 'Turn reading notes into action you actually take',
            'auth.colophon': 'Read well · Act well',
            'nav.collapse': 'Collapse navigation',
            'nav.back': 'Back',
            'nav.today': 'Today',
            'nav.schedule': 'Schedule',
            'nav.actions': 'Actions',
            'nav.upload': 'Notes',
            'nav.selfTalk': 'Self-talk',
            'nav.me': 'Me',
            'nav.capture': 'Capture',
            'tabbar.aria': 'Mobile shortcuts',
            'schedule.title': 'Schedule',
            'upload.title': 'Reading Notes',
            'reminder.title': 'Reminders',
            'reminder.settings': 'Settings',
            'reminder.collapse': 'Collapse',
            'common.close': 'Close',
            'common.cancel': 'Cancel',
            'common.save': 'Save',
            'common.update': 'Update',
            'common.enable': 'Enable',
            'common.turnOff': 'Turn off',
            'common.settings': 'Settings',
            'status.checking': 'Checking...',
            'auth.entry.title': 'Sign in',
            'auth.entry.desc': 'Sign in to your account, or create one to start Shuran',
            'auth.login.tab': 'Sign in',
            'auth.register.tab': 'Register',
            'auth.login.title': 'Sign in',
            'auth.login.desc': 'Use phone or email. New users need an invite code.',
            'auth.register.title': 'Start',
            'auth.register.desc': 'Register with a phone number and invite code',
            'auth.account.label': 'Phone or email',
            'auth.account.placeholder': 'Phone or email',
            'auth.password.label': 'Password',
            'auth.password.placeholder': 'Password',
            'auth.password.hint': 'At least 6 characters. Letters and numbers are recommended.',
            'auth.password.show': 'Show password',
            'auth.password.hide': 'Hide password',
            'auth.phone.label': 'Phone',
            'auth.phone.placeholder': '11-digit phone number',
            'auth.name.label': 'Real name',
            'auth.name.placeholder': 'Name',
            'auth.invite.label': 'Invite code',
            'auth.invite.placeholder': '4-digit invite code',
            'auth.login.submit': 'Sign in',
            'auth.login.loading': 'Signing in...',
            'auth.register.submit': 'Register',
            'auth.register.loading': 'Registering...',
            'auth.logout': 'Sign out',
            'auth.logout.confirm': 'Sign out of this account?',
            'auth.logout.confirmButton': 'Sign out',
            'me.profile.loading': 'Loading...',
            'me.editName': 'Edit name',
            'me.language.group': 'Language',
            'me.language.title': 'Interface language',
            'me.language.desc': 'This choice is saved on this device.',
            'me.language.zh': '中文',
            'me.language.en': 'English',
            'me.account.group': 'Account & Plan',
            'me.quota.today': "Today's quota",
            'me.plan.hint': 'Paid plans and renewals are opened by the site owner. New quotas take effect the same day.',
            'me.plans.plan': 'Plan',
            'me.plans.price': 'Price',
            'me.plans.extracts': 'Extracts / day',
            'me.plans.advice': 'Advice / day',
            'me.plans.duration': 'Duration',
            'me.bindPhone.group': 'Bind Phone',
            'me.bindPhone.hint': 'After binding, you can sign in with this phone number. One number can bind only one account. Verification-code binding will open later.',
            'me.bindPhone.placeholder': '11-digit phone number',
            'me.bindPhone.action': 'Bind',
            'me.quick.today.title': 'Today',
            'me.quick.today.desc': "Calendar, todos, and today's progress",
            'me.quick.actions.title': 'Actions',
            'me.quick.actions.desc': 'Best handled on desktop when you sit down',
            'me.quick.upload.title': 'Upload Notes',
            'me.quick.upload.desc': 'Extract actions from reading notes',
            'me.menu.owner': 'Owner Console',
            'me.menu.timeLog': 'Time Log',
            'me.menu.ideas': 'Ideas',
            'me.menu.stats': 'Practice Stats',
            'me.menu.dashboard': 'Dashboard',
            'me.menu.guide': 'Guide',
            'me.version.title': 'Version',
            'me.windows.title': 'Windows App',
            'me.windows.desc': 'Use this on desktop. Use mobile for schedule and Capture on the go.',
            'me.windows.running.title': 'Running in the Windows app',
            'me.windows.running.desc': 'Use global Ctrl+Shift+K for Capture. Ctrl+K also works inside the window.',
            'me.windows.hint': 'Do not open the Android APK with PC manager tools. Use the Windows app at your desk, and the mobile app outside.',
            'me.capture.group': 'Quick Capture',
            'me.capture.default.title': 'Default destination',
            'me.capture.default.desc': 'Triple tap or Capture starts as a moment. You can still change it before saving.',
            'me.capture.volume.title': 'Triple volume-down → Capture',
            'me.capture.volume.desc': 'When Shuran is open, press volume-down three times within about 1.5 seconds to open Capture.',
            'me.capture.updateApp': 'Get update',
            'capture.kind.moment': 'Moment',
            'capture.kind.idea': 'Idea',
            'capture.kind.todo': 'Todo',
            'me.reminders.group': 'Reminders',
            'me.reminders.hint': 'Set todo times when adding todos. Set reading time in Today. System notifications appear when due.',
            'me.reminders.enable': 'Enable reminders',
            'me.reminders.dailyGroup': 'Daily reminder',
            'me.reminders.daily': 'Daily reminder',
            'me.reminders.time': 'Reminder time',
            'me.reminders.repeat': 'Repeat',
            'me.reminders.repeatDays': 'Repeat days',
            'weekday.sun.short': 'Sun',
            'weekday.mon.short': 'Mon',
            'weekday.tue.short': 'Tue',
            'weekday.wed.short': 'Wed',
            'weekday.thu.short': 'Thu',
            'weekday.fri.short': 'Fri',
            'weekday.sat.short': 'Sat',
            'me.actionReminders.group': 'Action Reminders',
            'me.actionReminders.afterDone': 'After completing an action',
            'me.actionReminders.afterNew': 'After adding an action',
            'me.actionReminders.inactive': 'Inactivity reminder',
            'me.actionReminders.inactiveDesc': 'Remind after the selected number of inactive days',
            'me.notifications.group': 'Notifications',
            'me.notifications.hint': 'System notifications appear in the status bar and lock screen. Web will show in-app prompts.',
            'me.notifications.reliabilityHint': 'To receive reminders after closing the app, finish the checks below. Some Android systems stop background alarms by default.',
            'me.notifications.permission': 'Notification permission',
            'me.notifications.exactAlarm': 'Exact alarms',
            'me.notifications.exactAlarmDesc': 'If disabled, reminders may be delayed until you open the app.',
            'me.notifications.battery': 'Battery optimization',
            'me.notifications.batteryDesc': 'Battery saving can cancel scheduled alarms.',
            'me.notifications.autostart': 'Auto start',
            'me.notifications.autostartDesc': 'Allow Shuran to auto start so reminders still fire after the app is swiped away.',
            'me.notifications.system': 'System notifications',
            'me.notifications.email': 'Email notifications',
            'me.password.group': 'Change Password',
            'me.password.hint': 'Other signed-in devices will be signed out after the password changes.',
            'me.password.old': 'Current password',
            'me.password.new': 'New password (at least 6 characters)'
        }
    };

    function normalizeLanguage(value) {
        const lang = String(value || '').trim();
        if (!lang) return DEFAULT_LANGUAGE;
        if (lang.toLowerCase().startsWith('zh')) return 'zh-CN';
        if (lang.toLowerCase().startsWith('en')) return 'en';
        return DEFAULT_LANGUAGE;
    }

    function readStoredLanguage() {
        try {
            return normalizeLanguage(localStorage.getItem(STORAGE_KEY) || navigator.language || DEFAULT_LANGUAGE);
        } catch (e) {
            return DEFAULT_LANGUAGE;
        }
    }

    let currentLanguage = readStoredLanguage();

    function translate(key, fallback) {
        const table = messages[currentLanguage] || messages[DEFAULT_LANGUAGE];
        return table[key] || messages[DEFAULT_LANGUAGE][key] || fallback || key;
    }

    function applyToElements(root, selector, setter) {
        Array.prototype.forEach.call(root.querySelectorAll(selector), setter);
    }

    function apply(root) {
        const target = root || document;
        document.documentElement.lang = currentLanguage === 'en' ? 'en' : 'zh-CN';
        document.documentElement.dataset.lang = currentLanguage;
        document.body && document.body.classList.toggle('lang-en', currentLanguage === 'en');
        document.title = translate('app.title', '书然');

        applyToElements(target, '[data-i18n]', function (el) {
            el.textContent = translate(el.dataset.i18n, el.textContent);
        });
        applyToElements(target, '[data-i18n-placeholder]', function (el) {
            el.setAttribute('placeholder', translate(el.dataset.i18nPlaceholder, el.getAttribute('placeholder') || ''));
        });
        applyToElements(target, '[data-i18n-title]', function (el) {
            el.setAttribute('title', translate(el.dataset.i18nTitle, el.getAttribute('title') || ''));
        });
        applyToElements(target, '[data-i18n-aria-label]', function (el) {
            el.setAttribute('aria-label', translate(el.dataset.i18nAriaLabel, el.getAttribute('aria-label') || ''));
        });
        applyToElements(target, '[data-i18n-alt]', function (el) {
            el.setAttribute('alt', translate(el.dataset.i18nAlt, el.getAttribute('alt') || ''));
        });

        Array.prototype.forEach.call(document.querySelectorAll('input[name="languageChoice"]'), function (input) {
            input.checked = input.value === currentLanguage;
        });

        const displayName = document.getElementById('userDisplayName');
        if (displayName && /^(加载中…|Loading\.\.\.)$/.test(displayName.textContent.trim())) {
            displayName.textContent = translate('me.profile.loading', '加载中…');
        }
    }

    function setLanguage(language) {
        const next = normalizeLanguage(language);
        if (!SUPPORTED.includes(next)) return;
        currentLanguage = next;
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (e) {
            /* localStorage can be unavailable in some embedded modes */
        }
        apply(document);
        window.dispatchEvent(new CustomEvent('shuran-language-change', {
            detail: { language: currentLanguage }
        }));
    }

    document.addEventListener('change', function (event) {
        const target = event.target;
        if (target && target.name === 'languageChoice') {
            setLanguage(target.value);
        }
    });

    window.shuranI18n = {
        t: translate,
        apply: apply,
        setLanguage: setLanguage,
        getLanguage: function () { return currentLanguage; }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { apply(document); });
    } else {
        apply(document);
    }
})();
