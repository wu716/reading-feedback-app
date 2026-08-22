(function () {
    const TABS = [
        { id: 'overview', label: '今日', icon: '📅', href: '/static/index.html#overview' },
        { id: 'actions', label: '行动', icon: '🎯', href: '/static/index.html#actions' },
        { id: 'self-talk', label: 'Self-talk', icon: '🎤', href: '/static/index.html#self-talk' },
        { id: 'user-center', label: '我的', icon: '👤', href: '/static/index.html#user-center' },
    ];

    function currentTab() {
        const path = location.pathname || '';
        if (path.includes('self_talk')) return 'self-talk';
        if (path.includes('dashboard') || path.includes('user_center')) return 'user-center';
        const hash = (location.hash || '').replace('#', '');
        if (hash === 'upload' || hash === 'actions') return 'actions';
        if (hash === 'stats' || hash === 'guide' || hash === 'user-center') return 'user-center';
        if (hash === 'self-talk') return 'self-talk';
        return 'overview';
    }

    function go(tab) {
        if (typeof navigateTo === 'function') {
            navigateTo(tab.id);
            return;
        }
        location.href = tab.href;
    }

    function highlight() {
        const active = currentTab();
        document.querySelectorAll('#appTabbar .tab-item').forEach((el) => {
            el.classList.toggle('active', el.dataset.tab === active);
        });
        document.querySelectorAll('.nav-item[data-section]').forEach((el) => {
            el.classList.toggle('active', el.dataset.section === active);
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
            bar.setAttribute('aria-label', '主导航');
            bar.innerHTML = TABS.map((t) => `
                <button type="button" class="tab-item" data-tab="${t.id}">
                    <span class="tab-icon">${t.icon}</span>
                    <span class="tab-text">${t.label}</span>
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
        highlight();
    }

    window.syncAppTabbar = highlight;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
    window.addEventListener('hashchange', highlight);
})();
