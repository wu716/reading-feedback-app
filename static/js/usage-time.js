(() => {
  const HEARTBEAT_MS = 30 * 1000;
  const IDLE_MS = 2 * 60 * 1000;
  const NOTICE_KEY = 'shuranUsageTimeNotice20261026';
  const state = { days: 7, selectedDate: null, response: null, requestId: 0 };
  const byId = id => document.getElementById(id);

  function formatDuration(seconds) {
    const minutes = Math.round((Number(seconds) || 0) / 60);
    if (!minutes) return Number(seconds) > 0 ? '不足1分钟' : '0分钟';
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    if (hours && remainder) return `${hours}小时${remainder}分钟`;
    if (hours) return `${hours}小时`;
    return `${minutes}分钟`;
  }

  function formatDate(date) {
    const [year, month, day] = date.split('-').map(Number);
    const local = new Date(Date.UTC(year, month - 1, day, 4));
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', weekday: 'short',
    }).format(local);
  }

  function dayOffset(date, offset) {
    const [year, month, day] = date.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day + offset, 4)).toISOString().slice(0, 10);
  }

  function renderOwnerUsage() {
    const data = state.response;
    if (!data) return;
    const selected = data.selected_summary || {};
    byId('ownerUsageDateLabel').textContent = `${formatDate(data.selected_date)} · ${data.selected_date.slice(0, 4)}`;
    byId('ownerUsageTableTitle').textContent = `${data.selected_date} 用户明细`;
    byId('ownerUsageTotal').textContent = formatDuration(selected.active_seconds);
    byId('ownerUsageAccounts').textContent = String(selected.active_users || 0);
    byId('ownerUsageAverage').textContent = formatDuration(selected.average_active_seconds);
    byId('ownerUsagePrev').disabled = data.selected_date <= data.start_date;
    byId('ownerUsageNext').disabled = data.selected_date >= data.end_date;

    const chart = byId('ownerUsageChart');
    chart.replaceChildren();
    const daily = data.daily || [];
    const max = Math.max(1, ...daily.map(item => Number(item.active_seconds) || 0));
    for (const item of daily) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `owner-usage-bar-button${item.date === data.selected_date ? ' is-selected' : ''}`;
      button.setAttribute('aria-pressed', String(item.date === data.selected_date));
      button.setAttribute('aria-label', `${item.date}，总时长 ${formatDuration(item.active_seconds)}，${item.active_users} 个账号`);
      const total = document.createElement('span');
      total.className = 'owner-usage-bar-total';
      total.textContent = Number(item.active_seconds) > 0
        ? `${(Number(item.active_seconds) / 3600).toFixed(1)}h`
        : '0h';
      const bar = document.createElement('span');
      bar.className = 'owner-usage-bar';
      bar.style.height = `${Math.max(3, (Number(item.active_seconds) || 0) / max * 104)}px`;
      const label = document.createElement('span');
      label.className = 'owner-usage-bar-date';
      label.textContent = `${Number(item.date.slice(5, 7))}/${Number(item.date.slice(8, 10))}`;
      button.append(total, bar, label);
      button.addEventListener('click', () => loadOwnerUsageStats(item.date));
      chart.append(button);
    }

    const search = (byId('ownerUsageSearch').value || '').trim().toLocaleLowerCase();
    const rows = (data.users || []).filter(row => String(row.account || '').toLocaleLowerCase().includes(search));
    const tbody = byId('ownerUsageRows');
    tbody.replaceChildren();
    for (const row of rows) {
      const tr = document.createElement('tr');
      const dateCell = document.createElement('td');
      dateCell.textContent = data.selected_date;
      const emailCell = document.createElement('td');
      emailCell.textContent = row.account || `账号 ${row.user_id}`;
      const durationCell = document.createElement('td');
      durationCell.textContent = formatDuration(row.active_seconds);
      durationCell.className = 'owner-usage-duration';
      tr.append(dateCell, emailCell, durationCell);
      tbody.append(tr);
    }
    if (!rows.length) {
      const tr = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 3;
      cell.className = 'owner-usage-empty';
      cell.textContent = search ? '没有匹配的账号记录' : '这一天还没有使用时长记录';
      tr.append(cell);
      tbody.append(tr);
    }
  }

  async function loadOwnerUsageStats(date) {
    if (date) state.selectedDate = date;
    const requestId = ++state.requestId;
    const status = byId('ownerUsageStatus');
    if (status) status.textContent = '正在读取统计…';
    try {
      const query = new URLSearchParams({ days: String(state.days) });
      if (state.selectedDate) query.set('day', state.selectedDate);
      const data = await apiRequest(`/owner/usage?${query.toString()}`);
      if (requestId !== state.requestId) return;
      state.response = data;
      state.selectedDate = data.selected_date;
      renderOwnerUsage();
      status.textContent = `数据按北京时间统计，最近 ${data.retention_days} 天保留。`;
    } catch (error) {
      if (requestId === state.requestId && status) status.textContent = `读取失败：${error.message || '请稍后重试'}`;
    }
  }

  window.loadOwnerUsageStats = loadOwnerUsageStats;

  document.querySelectorAll('[data-owner-usage-days]').forEach(button => {
    button.addEventListener('click', () => {
      state.days = Number(button.dataset.ownerUsageDays) === 30 ? 30 : 7;
      state.selectedDate = null;
      document.querySelectorAll('[data-owner-usage-days]').forEach(item => {
        item.setAttribute('aria-pressed', String(item === button));
      });
      loadOwnerUsageStats();
    });
  });
  byId('ownerUsagePrev')?.addEventListener('click', () => {
    if (state.response) loadOwnerUsageStats(dayOffset(state.response.selected_date, -1));
  });
  byId('ownerUsageNext')?.addEventListener('click', () => {
    if (state.response) loadOwnerUsageStats(dayOffset(state.response.selected_date, 1));
  });
  byId('ownerUsageSearch')?.addEventListener('input', renderOwnerUsage);

  // Telemetry is gated until the one-time, in-app disclosure is acknowledged.
  let enabled = false;
  let lastActivityAt = 0;
  let lastPulseAttemptAt = 0;
  let pulseTimer = null;
  let pulseInFlight = false;
  let lastPointer = null;
  const notice = byId('usageDisclosureModal');

  function token() {
    return localStorage.getItem('authToken') || '';
  }

  function stopTracking() {
    enabled = false;
    if (pulseTimer) clearInterval(pulseTimer);
    pulseTimer = null;
  }

  function sendPulse({ allowHidden = false, resetBaseline = false } = {}) {
    const now = Date.now();
    const authToken = token();
    if (!enabled || !authToken || pulseInFlight || (!allowHidden && document.visibilityState !== 'visible')
      || now - lastActivityAt > IDLE_MS
      || now - lastPulseAttemptAt < (allowHidden || resetBaseline ? 2000 : HEARTBEAT_MS - 2000)) return;
    lastPulseAttemptAt = now;
    pulseInFlight = true;
    fetch('/api/usage/pulse', {
      method: 'POST',
      headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ reset_baseline: resetBaseline }),
      credentials: 'same-origin',
      keepalive: allowHidden,
    }).catch(() => {}).finally(() => { pulseInFlight = false; });
  }

  function startTracking() {
    if (enabled || !token() || localStorage.getItem(NOTICE_KEY) !== '1') return;
    enabled = true;
    lastActivityAt = Date.now();
    lastPulseAttemptAt = 0;
    sendPulse();
    pulseTimer = setInterval(() => sendPulse(), HEARTBEAT_MS);
  }

  function maybeShowNotice() {
    if (!window.authCheckSettled || !token()) {
      if (!token()) stopTracking();
      return;
    }
    if (localStorage.getItem(NOTICE_KEY) === '1') {
      startTracking();
      return;
    }
    stopTracking();
    notice?.classList.remove('hidden');
    byId('usageDisclosureAcknowledge')?.focus();
  }

  byId('usageDisclosureAcknowledge')?.addEventListener('click', () => {
    localStorage.setItem(NOTICE_KEY, '1');
    notice?.classList.add('hidden');
    lastActivityAt = Date.now();
    startTracking();
  });
  window.addEventListener('auth-check-settled', maybeShowNotice);
  window.addEventListener('shuran-auth-change', () => {
    if (token()) maybeShowNotice();
    else {
      stopTracking();
      notice?.classList.add('hidden');
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') sendPulse({ allowHidden: true });
    else {
      lastActivityAt = Date.now();
      sendPulse({ resetBaseline: true });
    }
  });
  document.addEventListener('pagehide', () => sendPulse({ allowHidden: true }));

  const markActivity = () => {
    lastActivityAt = Date.now();
    if (enabled) sendPulse();
  };
  ['pointerdown', 'keydown', 'wheel', 'touchstart', 'touchmove', 'scroll', 'input', 'click'].forEach(type => {
    document.addEventListener(type, markActivity, { passive: true, capture: true });
  });
  document.addEventListener('pointermove', event => {
    if (!lastPointer || Math.hypot(event.clientX - lastPointer.x, event.clientY - lastPointer.y) >= 8) {
      lastPointer = { x: event.clientX, y: event.clientY };
      markActivity();
    }
  }, { passive: true });
})();
