(function () {
    const TABS = [
        { id: 'schedule', labelKey: 'nav.schedule', label: '日程', icon: '程' },
        { id: 'projects', labelKey: 'nav.projects', label: '项目', icon: '项', action: 'projects' },
        { id: 'long-term', labelKey: 'nav.longTerm', label: '目标', icon: '目' },
        { id: 'capture', labelKey: 'nav.capture', label: '记', icon: '记' },
        { id: 'user-center', labelKey: 'nav.me', label: '我的', icon: '我' },
    ];

    function t(key, fallback) {
        return window.shuranI18n ? window.shuranI18n.t(key, fallback) : fallback;
    }

    function tabHref(id) {
        return '/static/index.html#' + id;
    }

    function currentTab() {
        const path = location.pathname || '';
        if (path.includes('projects')) {
            const view = new URLSearchParams(location.search).get('view');
            return view === 'execution' || view === 'templates' ? view : 'projects';
        }
        const hash = (location.hash || '').replace('#', '');
        if (hash === '' || hash === 'overview') return 'schedule';
        if (hash === 'capture' || hash === 'time-log' || hash === 'ideas' || hash === 'future-actions') return 'capture';
        if (hash === 'schedule') return 'schedule';
        if (hash === 'long-term') return 'long-term';
        return 'user-center';
    }

    function openCapture() {
        if (typeof navigateTo === 'function') navigateTo('capture');
        else location.href = tabHref('capture');
    }

    function go(tab) {
        if (tab.action === 'projects') {
            location.href = '/static/projects.html';
            return;
        }
        if (tab.id === 'capture') {
            openCapture();
            return;
        }
        if (typeof navigateTo === 'function') {
            navigateTo(tab.id);
            return;
        }
        location.href = tabHref(tab.id);
    }

    function highlight() {
        const active = currentTab();
        document.querySelectorAll('#appTabbar .tab-item').forEach((el) => {
            el.classList.toggle('active', el.dataset.tab === active);
        });
    }

    function render() {
        if (new URLSearchParams(location.search).get('embed') === '1') {
            return;
        }
        if (!document.getElementById('appTabbar')) {
            const bar = document.createElement('nav');
            bar.id = 'appTabbar';
            bar.className = 'app-tabbar';
            bar.setAttribute('aria-label', t('tabbar.aria', '出门时用'));
            bar.innerHTML = TABS.map((t) => `
                <button type="button" class="tab-item${t.id === 'capture' ? ' tab-capture' : ''}" data-tab="${t.id}">
                    <span class="tab-icon">${t.icon}</span>
                    <span class="tab-text" data-tab-label="${t.id}">${window.shuranI18n ? window.shuranI18n.t(t.labelKey, t.label) : t.label}</span>
                </button>
            `).join('');
            bar.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-tab]');
                if (!btn) return;
                const tab = TABS.find((item) => item.id === btn.dataset.tab);
                if (tab) go(tab);
            });
            document.body.appendChild(bar);
        }
        document.body.classList.add('has-app-tabbar');
        updateLabels();
        highlight();
    }

    function updateLabels() {
        const bar = document.getElementById('appTabbar');
        if (!bar) return;
        bar.setAttribute('aria-label', t('tabbar.aria', '出门时用'));
        TABS.forEach((tab) => {
            const label = bar.querySelector(`[data-tab-label="${tab.id}"]`);
            if (label) label.textContent = t(tab.labelKey, tab.label);
        });
    }

    window.syncAppTabbar = highlight;
    window.shuranOpenCapture = openCapture;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
    window.addEventListener('hashchange', highlight);
    window.addEventListener('shuran-language-change', updateLabels);
})();
