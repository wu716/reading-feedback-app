(function () {
    const TABS = [
        { id: 'schedule', labelKey: 'nav.schedule', label: '日程', icon: '程' },
        { id: 'reading', labelKey: 'nav.reading', label: '阅读', icon: '读', action: 'reading' },
        { id: 'actions', labelKey: 'nav.actions', label: '行动', icon: '行' },
        { id: 'capture', labelKey: 'nav.capture', label: '记', icon: '记', action: 'capture' },
        { id: 'self-talk', labelKey: 'nav.selfTalk', label: 'Self-talk', icon: '谈' },
        { id: 'user-center', labelKey: 'nav.me', label: '我的', icon: '我' },
    ];

    function t(key, fallback) {
        return window.shuranI18n ? window.shuranI18n.t(key, fallback) : fallback;
    }

    function tabHref(id) {
        if (id === 'self-talk' && location.pathname.includes('self_talk')) {
            return location.pathname + location.search;
        }
        if (id === 'user-center' && (location.pathname.includes('dashboard') || location.pathname.includes('user_center'))) {
            return location.pathname + location.search;
        }
        return '/static/index.html#' + id;
    }

    function currentTab() {
        const path = location.pathname || '';
        if (path.includes('self_talk')) return 'self-talk';
        if (path.includes('dashboard') || path.includes('user_center')) return 'user-center';
        const hash = (location.hash || '').replace('#', '');
        if (hash === 'actions') return 'actions';
        if (hash === 'upload' && document.getElementById('upload')?.classList.contains('epub-only')) return 'reading';
        if (hash === 'self-talk') return 'self-talk';
        if (hash === 'schedule' || hash === '') return 'schedule';
        return 'user-center';
    }

    function openCapture() {
        if (typeof window.punchTimeLog === 'function') {
            window.punchTimeLog(false);
            return;
        }
        location.href = '/static/index.html?capture=1#schedule';
    }

    function go(tab) {
        if (tab.action === 'reading') {
            if (typeof window.openEpubLibrary === 'function') window.openEpubLibrary();
            else location.href = '/static/index.html#upload';
            setTimeout(highlight, 0);
            return;
        }
        if (tab.action === 'capture') {
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
                <button type="button" class="tab-item${t.action === 'capture' ? ' tab-capture' : ''}" data-tab="${t.id}">
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
