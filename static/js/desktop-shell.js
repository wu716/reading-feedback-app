/**
 * 电脑端导航密度：宽屏完整侧栏，半屏自动收成图标轨，可手动钉住。
 */
(function () {
    const KEY = 'shuran.sidebarMode';
    const RAIL_MAX = 980;
    let lastNarrow = null;

    function isDesktop() {
        return window.innerWidth > 768;
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
        const viewport = window.visualViewport;
        const height = viewport ? Math.round(viewport.height) : window.innerHeight;
        document.documentElement.style.setProperty('--shuran-frame', height + 'px');
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
        apply();
        window.addEventListener('resize', onResize);
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', apply);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
