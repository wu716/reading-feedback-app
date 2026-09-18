/**
 * 电脑端导航密度：宽屏完整侧栏，半屏自动收成图标轨，可手动钉住。
 * Windows 壳（ShuranDesktop）下标出「已在应用中」。
 */
(function () {
    const KEY = 'shuran.sidebarMode';
    const RAIL_MAX = 980;
    let lastNarrow = null;

    function isDesktop() {
        return window.innerWidth > 768;
    }

    function isShuranDesktopApp() {
        return /ShuranDesktop/i.test(navigator.userAgent || '');
    }

    function syncDesktopAppRows() {
        const inApp = isShuranDesktopApp();
        document.body.classList.toggle('shuran-desktop-app', inApp);
        const download = document.getElementById('windowsAppDownloadRow');
        const running = document.getElementById('windowsAppRunningRow');
        const hint = document.getElementById('windowsAppHint');
        if (download) download.hidden = inApp;
        if (running) running.hidden = !inApp;
        if (hint) {
            hint.textContent = inApp
                ? '出门用手机看日程和「记」。本窗口可用 Ctrl+Shift+K 随时记下。'
                : '不要用电脑管家打开安卓安装包。坐下做事用 Windows 应用，出门用手机。';
        }
    }

    function isNarrow() {
        return window.innerWidth <= RAIL_MAX;
    }

    function preferredRail() {
        const saved = localStorage.getItem(KEY);
        if (!isDesktop()) return false;
        if (isNarrow()) {
            return saved !== 'full';
        }
        if (saved === 'full') return false;
        if (saved === 'rail') return true;
        return false;
    }

    function syncToggle(rail) {
        const btn = document.getElementById('sidebarToggleBtn');
        if (!btn) return;
        const label = rail ? '展开导航' : '收起导航';
        btn.title = label;
        btn.setAttribute('aria-label', label);
        btn.setAttribute('aria-expanded', rail ? 'false' : 'true');
        btn.classList.toggle('is-rail', rail);
    }

    function syncFrameHeight() {
        if (!isDesktop()) {
            document.documentElement.style.removeProperty('--shuran-frame');
            return;
        }
        document.documentElement.style.setProperty('--shuran-frame', window.innerHeight + 'px');
    }

    function apply() {
        if (!isDesktop()) {
            document.documentElement.style.removeProperty('--shuran-frame');
            document.body.classList.remove('sidebar-rail', 'sidebar-full');
            return;
        }
        syncFrameHeight();
        const rail = preferredRail();
        document.body.classList.toggle('sidebar-rail', rail);
        document.body.classList.toggle('sidebar-full', !rail);
        syncToggle(rail);
        if (typeof window.syncTimeLogFabDock === 'function') {
            window.syncTimeLogFabDock();
        }
    }

    function toggle() {
        if (!isDesktop()) return;
        localStorage.setItem(KEY, document.body.classList.contains('sidebar-rail') ? 'full' : 'rail');
        apply();
    }

    function onResize() {
        const narrow = isNarrow();
        if (lastNarrow !== null && lastNarrow !== narrow) {
            localStorage.removeItem(KEY);
        }
        lastNarrow = narrow;
        apply();
    }

    function onReady() {
        lastNarrow = isNarrow();
        const btn = document.getElementById('sidebarToggleBtn');
        if (btn) btn.addEventListener('click', toggle);
        syncDesktopAppRows();
        apply();
        window.addEventListener('resize', onResize);
    }

    window.isShuranDesktopApp = isShuranDesktopApp;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
