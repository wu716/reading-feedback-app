/** Shared navigation: each workspace has one purpose; old deep links remain valid. */
(() => {
  'use strict';
  const projectPage = location.pathname.endsWith('/projects.html');
  const query = new URLSearchParams(location.search);
  const validViews = new Set(['projects', 'execution', 'templates']);
  let view = validViews.has(query.get('view')) ? query.get('view') :
    query.has('execute') || location.hash === '#execution' ? 'execution' :
    location.hash === '#templateTitle' ? 'templates' : 'projects';
  let executionTab = query.get('tab') === 'records' ? 'records' : 'focus';
  let stageView = 'current';
  const routes = [
    ['schedule', '日程', '/static/index.html#schedule', 'M3 6h18v15H3z M7 3v6 M17 3v6 M3 11h18'],
    ['execution', '执行', '/static/projects.html?view=execution', 'M9 2h6 M12 6v7l4 2 M19 5l2 2 M20 14a8 8 0 1 1-16 0 8 8 0 0 1 16 0'],
    ['projects', '项目', '/static/projects.html', 'm12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5'],
    ['templates', '流程库', '/static/projects.html?view=templates', 'M3 4h4v17H3z M10 4h4v17h-4z M17 4l4 16'],
    ['capture', '记', '/static/index.html#capture', 'M5 3h14v18H5z M9 8h6 M9 12h6 M9 16h4'],
    ['long-term', '长期目标', '/static/index.html#long-term', 'M5 22V3 M5 4h14l-3 5 3 5H5'],
    ['user-center', '我的', '/static/index.html#user-center', 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 22v-3a8 8 0 0 1 16 0v3'],
  ];
  const icon = path => `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
  function activeRoute() {
    if (projectPage) return view;
    const hash = location.hash.slice(1) || 'schedule';
    return ['time-log','ideas','future-actions'].includes(hash) ? 'capture' : ['guide','owner'].includes(hash) ? 'user-center' : hash;
  }
  function sync() {
    window.syncAppTabbar?.();
    document.querySelectorAll('[data-workspace-route]').forEach(link => {
      if (link.dataset.workspaceRoute === activeRoute()) link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    });
    if (!projectPage) return;
    document.body.dataset.workspaceView = view;
    document.querySelectorAll('[data-workspace-view]').forEach(section => section.hidden = section.dataset.workspaceView !== view);
    document.querySelectorAll('[data-execution-panel]').forEach(panel => panel.hidden = panel.dataset.executionPanel !== executionTab);
    document.querySelectorAll('[data-execution-tab]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.executionTab === executionTab)));
    document.querySelectorAll('[data-stage-view]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.stageView === stageView)));
    document.querySelectorAll('#stageBoard .stage').forEach(stage => stage.hidden = !stage.classList.contains(stageView));
    const title = document.getElementById('workspaceTitle');
    if (title) title.textContent = ({projects:'项目',execution:'执行',templates:'流程库'})[view];
    const subtitle = document.getElementById('workspaceSubtitle');
    if (subtitle) subtitle.textContent = ({projects:'围绕交付结果，拆分阶段与任务',execution:new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(new Date()),templates:'可复用的步骤、检查项和验收标准'})[view];
    const templateAction = document.querySelector('[data-new-template]');
    if (templateAction) templateAction.hidden = view !== 'templates';
    document.title = ({projects:'项目',execution:'执行',templates:'流程库'})[view] + ' · 书然';
  }
  function show(next, tab, replace = false) {
    if (!validViews.has(next)) return;
    view = next;
    if (tab) executionTab = tab;
    const url = new URL(location.href);
    url.searchParams.set('view', next);
    url.searchParams.delete('tab');
    url.hash = '';
    history[replace ? 'replaceState' : 'pushState'](null, '', url);
    sync();
    window.scrollTo(0,0);
  }
  function onReady() {
    document.body.classList.add('workspace-layout');
    if (projectPage) {
      const templateAction = document.querySelector('[data-new-template]');
      document.querySelector('.workspace-page-header').appendChild(templateAction);
    }
    const nav = document.createElement('aside');
    nav.className = 'workspace-sidebar';
    nav.innerHTML = `<a class="workspace-brand" href="/static/index.html#schedule">书然</a><nav aria-label="工作区">${routes.map((r,i) => `${i===4?'<div class="workspace-nav-label">记录与回看</div>':''}<a href="${r[2]}" data-workspace-route="${r[0]}">${icon(r[3])}<span>${r[1]}</span></a>`).join('')}</nav>`;
    document.body.appendChild(nav);
    const compact = document.createElement('nav');
    compact.className = 'workspace-mobile-tabs'; compact.setAttribute('aria-label','计划与执行');
    compact.innerHTML = routes.slice(0,4).map(r=>`<a href="${r[2]}" data-workspace-route="${r[0]}">${r[1]}</a>`).join('');
    (document.querySelector('.app-header, .app-head') || document.body).after(compact);
    document.addEventListener('click', event => {
      const route = event.target.closest('[data-workspace-route]');
      if (route && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
        const next = route.dataset.workspaceRoute;
        if (projectPage && validViews.has(next)) { event.preventDefault(); show(next); }
        else if (!projectPage && !validViews.has(next) && typeof window.navigateTo === 'function') {
          event.preventDefault(); window.navigateTo(next);
        }
      }
      const tab = event.target.closest('[data-execution-tab]');
      if (tab) { executionTab = tab.dataset.executionTab; sync(); }
      const stage = event.target.closest('[data-stage-view]');
      if (stage) { stageView = stage.dataset.stageView; sync(); }
      if (event.target.closest('[data-new-template]')) {
        const editor = document.getElementById('templateEditor');
        document.getElementById('templateForm').reset(); editor.hidden = false; editor.open = true;
        editor.querySelector('input[name=title]').focus();
      }
    });
    window.addEventListener('hashchange', () => {
      if (projectPage && location.hash === '#execution') show('execution', undefined, true);
      else if (projectPage && location.hash === '#templateTitle') show('templates', undefined, true);
      else sync();
    });
    window.addEventListener('popstate', () => {
      const requested = new URLSearchParams(location.search).get('view');
      if (projectPage) view = validViews.has(requested) ? requested : 'projects';
      sync();
    });
    sync();
  }
  window.ShuranWorkspace = {sync, show};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
  else onReady();
})();
