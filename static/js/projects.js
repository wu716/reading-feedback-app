(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const state = { overview: {goals:[], projects:[]}, todayTasks:[], templates:[], sessions:[], projectId:null, taskId:null, active:null, detailMode:'attributes' };
  const params = new URLSearchParams(location.search);
  state.plan = {queue:[], daily_tasks:[], work_minutes:20, break_minutes:5};
  let noticeTimer, actionBusy = false, expiring = false, hydrated = false;
  let finishedId = null, soundContext = null;

  function nativeBridge() { return globalThis.ShuranNative || null; }
  function syncFocusAlarm() {
    const native = nativeBridge();
    if (!native || !native.setFocusTimer) return;
    const active = state.active;
    const latest = state.sessions.find(s => s.source === 'timer');
    const completed = !active && latest?.ended_at && latest?.deadline_at
      && Math.abs(Date.parse(latest.ended_at) - Date.parse(latest.deadline_at)) <= 1000
      && Date.now() + (state.clockOffset || 0) - Date.parse(latest.deadline_at) < 60 * 1000;
    try {
      native.setFocusTimer(JSON.stringify(active && active.source === 'timer' ? {
        id:active.id, kind:active.kind,
        deadline_ms:Date.parse(active.deadline_at) - (state.clockOffset || 0)
      } : completed ? {id:latest.id, completed:true} : {}));
    } catch (_) { /* The persistent in-page alert remains available. */ }
  }
  function notificationSettings() {
    const native = nativeBridge(), supported = native?.hasPermission || globalThis.Notification;
    let granted = false;
    try { granted = native ? !!native.hasPermission() : globalThis.Notification?.permission === 'granted'; }
    catch (_) { /* Permission can change while the app is open. */ }
    $('#focusReminderSettings').hidden = !supported || granted;
  }
  function acknowledgeFinished() {
    if (finishedId != null) localStorage.setItem('focusFinishedSession', String(finishedId));
    finishedId = null;
    $('#focusFinished').hidden = true;
  }
  function prepareSound() {
    if (soundContext) return;
    const Audio = globalThis.AudioContext || globalThis.webkitAudioContext;
    try { if (Audio) { soundContext = new Audio(); soundContext.resume(); } } catch (_) { soundContext = null; }
  }
  function soundFinished() {
    if (!soundContext) return;
    try {
      soundContext.resume();
      const oscillator = soundContext.createOscillator(), gain = soundContext.createGain();
      oscillator.type = 'sine'; oscillator.frequency.value = 660;
      gain.gain.setValueAtTime(0.001, soundContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.11, soundContext.currentTime + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.001, soundContext.currentTime + 0.32);
      oscillator.connect(gain).connect(soundContext.destination);
      oscillator.start(); oscillator.stop(soundContext.currentTime + 0.33);
    } catch (_) { /* The visible reminder still works without audio. */ }
  }
  function showFinished(session, live = false) {
    if (!session || localStorage.getItem('focusFinishedSession') === String(session.id)) return;
    const isNew = finishedId !== session.id;
    finishedId = session.id;
    $('#focusFinishedTitle').textContent = session.kind === 'break' ? '休息到时' : '工作片到时';
    $('#focusFinishedText').textContent = session.kind === 'break'
      ? '这段休息结束了。准备好后开始下一项。'
      : '这段工作已到点并挂起。可以休息，或选择下一项。';
    $('#focusFinished').hidden = false;
    if (!isNew || !live) return;
    soundFinished();
    if (!nativeBridge() && document.hidden && globalThis.Notification?.permission === 'granted') {
      try { new globalThis.Notification('书然 · ' + $('#focusFinishedTitle').textContent, {
        body:$('#focusFinishedText').textContent, tag:'shuran-focus-' + session.id
      }); } catch (_) { /* The in-page reminder remains visible. */ }
    }
  }
  function restoreFinished() {
    const active = state.active;
    if (active && Date.parse(active.deadline_at) > Date.now() + (state.clockOffset || 0)) {
      if (finishedId && finishedId !== active.id) acknowledgeFinished();
      return;
    }
    const last = state.sessions.find(s => s.source === 'timer');
    if (!active && last?.ended_at && last?.deadline_at
        && Date.parse(last.ended_at) >= Date.parse(last.deadline_at) - 1000
        && Date.now() + (state.clockOffset || 0) - Date.parse(last.deadline_at) < 6 * 3600 * 1000) {
      showFinished(last);
    }
  }

  function notice(message, error = false) {
    const box = $('#notice'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false;
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => box.hidden = true, 5000);
  }
  async function request(path, options = {}) {
    const token = localStorage.getItem('authToken');
    if (!token) { location.href = '/static/index.html#user-center'; throw new Error('请先登录'); }
    const response = await fetch('/api/projects' + path, {
      ...options, headers: {'Authorization':'Bearer ' + token, ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {})}
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请稍后重试');
    if (data.server_now) state.clockOffset = Date.parse(data.server_now) - Date.now();
    return data;
  }
  const post = (path, body) => request(path, {method:'POST',body:JSON.stringify(body)});
  const patch = (path, body) => request(path, {method:'PATCH',body:JSON.stringify(body)});
  const put = (path, body) => request(path, {method:'PUT',body:JSON.stringify(body)});
  async function confirmReadiness(kind, id) {
    const ready = await request(`/readiness/${kind}/${id}`);
    if (ready.blockers?.length) throw new Error(ready.blockers.join('；') + '。请到开始条件与约束处理。');
    if (ready.reminders?.length && !window.confirm(ready.reminders.join('\n') + '\n\n已了解以上提醒，继续开始？')) {
      throw new Error('已保留当前安排');
    }
    return !!ready.reminders?.length;
  }
  function currentProject() { return state.overview.projects.find(p => p.id === state.projectId); }
  function currentTask() { return currentProject()?.tasks.find(t => t.id === state.taskId); }
  function allTasks() { return state.overview.projects.flatMap(p => p.tasks.map(t => ({...t, project_title:p.title}))); }
  function todayISO() {
    return new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  }
  function dailyLeaves(nodes, parents = []) {
    return (nodes || []).flatMap(task => task.children?.length
      ? dailyLeaves(task.children, [...parents, task.text])
      : [{...task, path:parents.filter(Boolean).join(' / ')}]);
  }
  async function loadTodayTasks() {
    const response = await fetch(`/api/schedule?task_date=${params.get('date') || todayISO()}`, {
      headers:{Authorization:'Bearer ' + localStorage.getItem('authToken')}
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '加载今日任务失败');
    state.historyTasks = dailyLeaves(data.tasks);
    return state.historyTasks.filter(task => !task.completed);
  }
  function executionChoices(forHistory = false) {
    const projects = allTasks();
    const byId = new Map(projects.map(task => [task.id, task]));
    const merged = new Map([...(state.plan.daily_tasks || []), ...state.todayTasks, ...(forHistory ? state.historyTasks || [] : [])].map(t => [t.id, t]));
    const today = [...merged.values()].map(task => {
      const linked = byId.get(task.project_task_id);
      return {key:`daily:${task.id}`, title:`${task.path ? task.path + ' / ' : ''}${task.text}`,
        project_task_id:linked?.id || null, daily_task_id:task.id,
        disabled:task.completed || task.readiness?.can_start === false || (!!linked && !linked.can_start),
        reason:task.readiness?.summary || linked?.readiness?.summary || '', group:'今日任务'};
    });
    const scheduled = new Set(today.map(task => task.project_task_id).filter(Boolean));
    const remaining = projects.filter(task => !scheduled.has(task.id)).map(task => ({
      key:`project:${task.id}`, title:`${task.project_title} · ${task.title}`,
      project_task_id:task.id, daily_task_id:null, disabled:!task.can_start,
      reason:task.readiness?.summary || '', group:'项目任务'
    }));
    return [...today, ...remaining];
  }
  function taskOptions(selectedKey, forHistory = false) {
    const choices = executionChoices(forHistory);
    const option = task => `<option value="${task.key}" ${task.key === selectedKey ? 'selected' : ''} ${task.disabled && !forHistory ? 'disabled' : ''}>${esc(task.title)}${task.disabled ? `（${esc(task.reason || '当前受阻')}）` : ''}</option>`;
    return '<option value="">选择任务</option>' + ['今日任务', '项目任务'].map(group => {
      const items = choices.filter(task => task.group === group);
      return items.length ? `<optgroup label="${group}">${items.map(option).join('')}</optgroup>` : '';
    }).join('');
  }
  function selectedTask(key = $('#focusTask').value) {
    return executionChoices().find(task => task.key === key && !task.disabled);
  }
  function localInput(iso) {
    if (!iso) return '';
    const d = new Date(iso), shifted = new Date(d.getTime() - d.getTimezoneOffset()*60000);
    return shifted.toISOString().slice(0,16);
  }
  function dtLabel(iso) { return iso ? new Date(iso).toLocaleString('zh-CN', {hour12:false}) : '进行中'; }
  function stageName(stage) { return stage.state === 'current' ? '当前阶段' : stage.state === 'next' ? '下一阶段' : '已结束'; }
  function goalOptions(selected) { return '<option value="">暂不关联</option>' + state.overview.goals.map(g => `<option value="${g.id}" ${g.id === selected ? 'selected' : ''}>${esc(g.title)}</option>`).join(''); }
  function stageOptions(project, selected) { return (project?.stages || []).filter(s => s.state !== 'closed').map(s => `<option value="${s.id}" ${s.id === selected ? 'selected' : ''}>${esc(s.title)} · ${stageName(s)}</option>`).join(''); }

  async function refresh() {
    state.plan = await request('/execution');
    const [overview, templates, sessions, todayTasks] = await Promise.all([request('/overview'), request('/templates'), request('/sessions'), loadTodayTasks()]);
    state.overview = overview; state.templates = templates.items; state.sessions = sessions.items; state.todayTasks = todayTasks;
    if (!overview.projects.some(p => p.id === state.projectId)) state.projectId = overview.projects[0]?.id ?? null;
    if (!currentProject()?.tasks.some(t => t.id === state.taskId)) state.taskId = null;
    state.active = state.sessions.find(s => !s.ended_at) || null;
    syncFocusAlarm(); notificationSettings();
    if (!hydrated) {
      $('#workMinutes').value = state.plan.work_minutes; $('#breakMinutes').value = state.plan.break_minutes;
      const task = allTasks().find(t => t.id === Number(params.get('task')));
      if (task) { state.projectId = task.project_id; state.taskId = task.id; state.detailMode = params.get('finish') ? 'completion' : 'attributes'; }
      hydrated = true;
    }
    render();
  }
  async function afterChange(message) { await refresh(); if (message) notice(message); }
  async function refreshExecution() {
    state.plan = await request('/execution');
    const [sessions, overview, tasks] = await Promise.all([request('/sessions'), request('/overview'), loadTodayTasks()]);
    state.sessions = sessions.items; state.overview = overview; state.todayTasks = tasks;
    state.active = state.sessions.find(s => !s.ended_at) || null;
    syncFocusAlarm(); notificationSettings();
    renderExecution(); renderSessions();
  }
  async function run(task) {
    if (actionBusy || expiring) return;
    actionBusy = true;
    try { await task(); } catch (error) { notice(error.message, true); }
    finally { actionBusy = false; }
  }

  function renderGoals() {
    $('#goalList').innerHTML = state.overview.goals.length ? state.overview.goals.map(g =>
      `<span class="chip">${esc(g.title)}${g.horizon_end ? `<small>至 ${esc(g.horizon_end)}</small>` : ''} <button type="button" class="plain-action" data-act="edit-goal" data-id="${g.id}" aria-label="修改目标 ${esc(g.title)}">修改</button></span>`).join('') : '<p class="empty">先从一个近期目标开始；简单事项也可以不建目标。</p>';
    $('#projectGoal').innerHTML = goalOptions(null);
  }
  function renderProjects() {
    const projects = state.overview.projects;
    $('#projectSelect').innerHTML = projects.length ? projects.map(p => `<option value="${p.id}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.title)}</option>`).join('') : '<option value="">还没有项目</option>';
    const project = currentProject(); $('#projectOutcome').textContent = project?.outcome || '';
    $('#projectLifecycle').innerHTML = project ? `<h3>项目执行状态</h3>
      <p>${esc(({preparation:'筹备中：正式任务需先检查条件并开始项目',started:'已正式开始',delivered:'已交付，待验收',accepted:'已验收'})[project.execution_state] || '历史项目：未记录正式启动，保留原有可用性')}${project.started_at ? ` · 首次正式开始 ${dtLabel(project.started_at)}` : ''}</p>
      <details><summary>变更项目状态</summary><form id="projectStateForm"><label>操作 <select name="state"><option value="started">检查条件并正式开始／重新开始</option><option value="delivered">确认已经交付</option><option value="accepted">确认已经验收</option><option value="preparation">交付后重新筹备（保留历史）</option></select></label><label>判断依据或原因 <input name="reason" required maxlength="4000"></label><button type="submit">确认项目状态</button></form></details>` : '';
    if (project) globalThis.ShuranConditions?.mount($('#projectConditions'), 'project', project.id, () => afterChange());
    else $('#projectConditions').innerHTML = '';
    $('#stageBoard').innerHTML = project ? project.stages.map(s => {
      const tasks = project.tasks.filter(t => t.stage_id === s.id);
      const open = s.state === 'current' || s.state === 'next';
      const stageLabel = stageName(s);
      return `<article class="stage ${esc(s.state)}"><div class="stage-header"><h3>${esc(s.title)}</h3><span class="state-tag">${stageName(s)}</span></div>
        ${tasks.length ? tasks.map(t => `<div class="task-row ${!t.can_start ? 'blocked' : ''} ${t.state === 'completed' ? 'done' : ''}"><button type="button" data-act="select-task" data-id="${t.id}">${esc(t.title)}<small>${t.execution_role === 'preparation' ? '筹备任务 · ' : ''}${t.state === 'completed' ? '已完成' : esc(t.readiness?.summary || (t.blocked_by.length ? '等待前置任务' : '可以推进'))} · 原估计 ${t.original_estimate_minutes ?? '未填'} 分 · 实耗 ${t.actual_minutes} 分</small></button></div>`).join('') : `<p class="stage-empty">这里还没有任务${open ? '，可以在下方写入第一项。' : '。'}</p>`}
        ${open ? `<form class="stage-task-form" data-stage="${s.id}">
          <label>${stageLabel}的新任务 <input name="title" maxlength="500" required placeholder="写下一件能开始、能核对的事"></label>
          <button type="submit">加入${stageLabel}</button>
          <details class="optional-fields"><summary>补充估时、任务用途与完成标准</summary>
            <div class="field-grid">
              <label>预计分钟 <input name="estimated_minutes" type="number" min="0" max="100000" placeholder="可稍后估"></label>
              <label>熟悉程度 <select name="familiarity"><option value="">暂不标记</option><option value="familiar">熟悉</option><option value="unfamiliar">陌生</option></select></label>
              <label>任务用途 <select name="execution_role"><option value="formal">正式执行（继承项目条件）</option><option value="preparation">筹备任务（只检查自身条件）</option></select></label>
              <label class="wide">对目标的作用 <textarea name="goal_reason" rows="2" maxlength="4000"></textarea></label>
              <label class="wide">怎样算完成 <textarea name="acceptance_criteria" rows="2" maxlength="4000"></textarea></label>
            </div>
          </details>
        </form>` : ''}
        ${s.state === 'next' ? `<div class="stage-transition"><p>阶段切换</p><form class="stage-change" data-stage="${s.id}"><select name="decision" aria-label="当前阶段如何处理"><option value="continue">继续当前阶段</option><option value="adjust">调整范围并切换</option><option value="close">结束当前阶段</option></select><input name="reason" placeholder="结束时说明原因" aria-label="阶段结束原因"><button type="submit">确认切换</button></form></div>` : ''}</article>`;
    }).join('') : '<p class="empty">建立项目后，这里会出现当前阶段和下一阶段。</p>';
  }
  function renderTaskDetail() {
    const root = $('#taskDetail'), task = currentTask(), project = currentProject();
    if (!task) { root.hidden = true; return; }
    root.hidden = false;
    const choices = project.tasks.filter(t => t.id !== task.id).map(t => `<option value="${t.id}">${esc(t.title)}</option>`).join('');
    const prereq = task.prerequisite_ids.map(id => project.tasks.find(t => t.id === id)).filter(Boolean);
    root.innerHTML = `<div class="detail-header"><h3>${esc(task.title)}</h3><button type="button" class="secondary" data-act="close-detail">收起</button></div>
      <p class="task-metrics">原估计 ${task.original_estimate_minutes ?? '未填'} 分 · 当前估计 ${task.estimated_minutes ?? '未填'} 分 · 实际投入 ${task.actual_minutes} 分${task.difference_minutes == null ? '' : ` · 差额 ${task.difference_minutes > 0 ? '+' : ''}${task.difference_minutes} 分`}</p>
      <p>${esc(task.readiness?.summary || '未配置启动条件')} · ${task.execution_role === 'preparation' ? '筹备任务：不继承项目条件' : '正式任务：继承项目条件'}</p>
      <p class="scheduled-dates">已安排：${(task.scheduled_dates || []).map(day => `<a href="/static/index.html?schedule_date=${day}#schedule">${day}</a>`).join(' · ') || '尚未安排到日程'}</p><div class="detail-actions"><button type="button" data-act="queue-task" ${task.can_start ? '' : 'disabled'}>加入时间片轮转</button><a href="/static/index.html#schedule">查看日程</a></div><form id="scheduleTaskForm"><label>安排到哪天 <input name="task_date" type="date" required></label><button type="submit">写入日程</button></form><div class="detail-actions" role="tablist" aria-label="任务操作分区"><button type="button" class="${state.detailMode === 'attributes' ? '' : 'secondary'}" data-act="detail-mode" data-mode="attributes">内容与估时</button><button type="button" class="${state.detailMode === 'conditions' ? '' : 'secondary'}" data-act="detail-mode" data-mode="conditions">开始条件与约束</button><button type="button" class="${state.detailMode === 'dependencies' ? '' : 'secondary'}" data-act="detail-mode" data-mode="dependencies">完成检查</button><button type="button" class="${state.detailMode === 'completion' ? '' : 'secondary'}" data-act="detail-mode" data-mode="completion">安排与验收</button></div>
      <div class="detail-zone" ${state.detailMode === 'conditions' ? '' : 'hidden'}><div id="taskConditions" class="condition-workspace"></div>
        <h4>原有任务前置关系</h4><p>${prereq.length ? prereq.map(t => `${esc(t.title)} <button type="button" class="secondary" data-act="remove-dep" data-id="${t.id}">说明原因并移除</button>`).join(' · ') : '未配置原有任务前置。其他条件见上方。'}</p>
        <form id="dependencyForm"><label>必须先完成 <select name="prerequisite_id">${choices}</select></label><button type="submit" ${choices ? '' : 'disabled'}>添加前置</button></form></div>
      <div class="detail-zone" ${state.detailMode === 'attributes' ? '' : 'hidden'}><h4>内容与估时</h4><form id="detailForm" class="detail-grid">
        <label>任务 <input name="title" maxlength="500" required value="${esc(task.title)}"></label><label>阶段 <select name="stage_id">${stageOptions(project, task.stage_id)}</select></label>
        <label>当前估计分钟 <input name="estimated_minutes" type="number" min="0" value="${task.estimated_minutes ?? ''}"></label><label>熟悉程度 <select name="familiarity"><option value="">未标记</option><option value="familiar" ${task.familiarity === 'familiar' ? 'selected' : ''}>熟悉</option><option value="unfamiliar" ${task.familiarity === 'unfamiliar' ? 'selected' : ''}>陌生</option></select></label>
        <label class="wide">为什么对目标有用 <textarea name="goal_reason" rows="2">${esc(task.goal_reason)}</textarea></label><label class="wide">怎样算完成 <textarea name="acceptance_criteria" rows="2">${esc(task.acceptance_criteria)}</textarea></label>
        <label class="wide">开始前预演（第一步、材料、难处、卡住怎么办） <textarea name="rehearsal_note" rows="3">${esc(task.rehearsal_note)}</textarea></label><label class="wide">流程步骤（每行一项） <textarea name="steps" rows="3">${esc(task.steps.join('\n'))}</textarea></label>
        <label class="wide">难点或阻碍 <textarea name="blocker_note" rows="2">${esc(task.blocker_note)}</textarea></label><button type="submit">保存任务内容</button></form></div>
      <div class="detail-zone" ${state.detailMode === 'dependencies' ? '' : 'hidden'}><p>普通检查项用于核对交付，不会暗中成为开始门槛。</p>
        <h4>检查项</h4><ul>${task.checklist.map(item => `<li><label class="check"><input type="checkbox" data-act="toggle-check" data-id="${item.id}" ${item.done ? 'checked' : ''}>${esc(item.text)}</label></li>`).join('') || '<li>还没有检查项</li>'}</ul>
        <form id="checklistForm"><label>新增检查项 <input name="text" maxlength="500" required></label><button type="submit">添加</button></form></div>
      <div class="detail-zone" ${state.detailMode === 'completion' ? '' : 'hidden'}><h4>安排与验收</h4>

        <p>完成时核对标准：${esc(task.acceptance_criteria || '尚未填写，可先判断实际结果。')}</p>
        <form id="finishTaskForm"><label>结果 <select name="result"><option value="completed">完成</option><option value="partial">部分完成</option><option value="rework">需要返工</option></select></label><label>结果说明 <input name="outcome_note" value="${esc(task.outcome_note)}"></label><label>估时偏差原因 <input name="variance_reason" value="${esc(task.variance_reason)}"></label><button type="submit">保存验收</button></form>
        <div class="detail-actions"><button type="button" class="secondary" data-act="save-template">保存为流程</button></div></div>`;
    const date = $('#scheduleTaskForm [name=task_date]', root); if (date) date.value = params.get('date') || todayISO();
    if (state.detailMode === 'conditions') globalThis.ShuranConditions?.mount($('#taskConditions', root), 'task', task.id, () => afterChange());
  }

  function choiceFor(key) {
    return executionChoices().find(t => t.key === key || (key.startsWith('project:') && t.project_task_id === Number(key.split(':')[1])));
  }
  function sessionChoice(session) {
    if (!session) return null;
    return choiceFor(session.daily_task_id ? `daily:${session.daily_task_id}` : `project:${session.project_task_id}`);
  }
  function queueChoices() { return state.plan.queue.map(choiceFor).filter(Boolean); }
  function lastWork() { return state.sessions.find(s => s.kind === 'work' && s.source === 'timer'); }
  function nextTask() { return queueChoices().find(t => !t.disabled); }
  async function saveQueue(keys = state.plan.queue) {
    state.plan = await put('/execution', {queue:keys.filter(key => choiceFor(key)), work_minutes:Number($('#workMinutes').value), break_minutes:Number($('#breakMinutes').value)});
  }
  async function addQueue(key) {
    const task = choiceFor(key);
    if (!task || task.disabled) throw new Error('该任务当前不可开始');
    if (!queueChoices().some(t => t.key === task.key)) await saveQueue([...state.plan.queue, task.key]);
    renderExecution();
  }
  function renderExecution() {
    $('#focusTask').innerHTML = taskOptions($('#focusTask').value);
    $('#manualTask').innerHTML = taskOptions($('#manualTask').value, true);
    const active = state.active, paused = state.plan.paused;
    const current = active || paused || lastWork();
    const currentChoice = sessionChoice(current);
    const warning = $('#activeConditionWarning');
    warning.hidden = !active || active.kind !== 'work' || (!!currentChoice && !currentChoice.disabled);
    warning.textContent = !warning.hidden ? `当前条件发生变化：${currentChoice?.reason || '任务当前不可开始或已移除'}。请明确暂停、补齐条件或调整；已记录投入保留。` : '';
    $('#activeTaskTitle').textContent = active?.kind === 'break' || paused?.kind === 'break' ? '休息一下' : current?.label || sessionChoice(current)?.title || nextTask()?.title || '先把要做的事加入轮转';
    const projectTask = allTasks().find(t => t.id === current?.project_task_id);
    const link = $('#activeProjectLink'); link.hidden = !projectTask;
    if (projectTask) { link.href = `/static/projects.html?task=${projectTask.id}#taskDetail`; link.textContent = `${projectTask.project_title} · 查看任务与投入`; }
    $('.focus-panel').classList.toggle('break', active?.kind === 'break');
    $('#startWork').textContent = paused ? '恢复剩余时间' : lastWork() ? '开始下一项' : '开始队首任务';
    $('#startWork').disabled = !!active || (!paused && !nextTask());
    $('#pauseWork').disabled = !active;
    $('#endWork').disabled = !active && !paused;
    $('#switchWork').disabled = !nextTask();
    $('#actualStopWrap').hidden = !active;
    const decision = !active && !paused && !!lastWork();
    $('#timeDecision').hidden = !decision;
    $('#decisionCaption').textContent = state.sessions[0]?.kind === 'break' ? '休息已结束，准备好后开始下一项。' : '这一片已挂起，未完成的任务保留在轮转中。';
    $('[data-next=break]').textContent = `休息 ${state.plan.break_minutes} 分钟`;
    $('[data-next=continue]').disabled = !sessionChoice(lastWork()) || sessionChoice(lastWork()).disabled;
    $('#rotationQueue').innerHTML = state.plan.queue.map((key, index) => {
      const task = choiceFor(key), isCurrent = task && active?.kind === 'work' && sessionChoice(active)?.key === task.key;
      return `<li class="rotation-item ${isCurrent ? 'current' : ''}"><div><strong>${esc(task?.title || '任务已移除')}</strong><small>${isCurrent ? '正在执行' : task?.disabled ? esc(task.reason || '已完成或受阻，本轮跳过') : `第 ${index + 1} 项 · 每片 ${state.plan.work_minutes} 分钟`}</small></div><div class="queue-order"><button type="button" class="secondary" data-queue="up" data-index="${index}" ${index === 0 ? 'disabled' : ''} aria-label="上移 ${esc(task?.title || '')}">上移</button><button type="button" class="secondary" data-queue="down" data-index="${index}" ${index === state.plan.queue.length - 1 ? 'disabled' : ''} aria-label="下移 ${esc(task?.title || '')}">下移</button><button type="button" class="secondary" data-queue="remove" data-index="${index}">移出</button></div></li>`;
    }).join('') || '<li class="empty">先加入 A、B、C；每片结束后，选择下一项即可轮转。</li>';
    $('#dailyProjectLink').hidden = !params.get('daily');
    $('#confirmDailyProject').disabled = !state.projectId;
    restoreFinished();
    tick();
  }
  function tick() {
    const active = state.active;
    const budget = active?.planned_seconds || state.plan.remaining_seconds || state.plan.work_minutes * 60;
    const remaining = active ? Math.max(0, Math.ceil((Date.parse(active.deadline_at) - Date.now() - (state.clockOffset || 0)) / 1000)) : state.plan.paused ? state.plan.remaining_seconds : budget;
    $('#timerDisplay').textContent = `${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}`;
    $('#timerCaption').textContent = active ? `${active.kind === 'break' ? '休息中' : '工作中'} · 到点自动挂起` : state.plan.paused ? '已暂停 · 恢复后接着剩余时间' : lastWork() ? '等待下一步 · 当前不计时' : '准备开始工作片';
    $('#sliceProgress').max = budget; $('#sliceProgress').value = active ? budget - remaining : 0;
    if (active && remaining === 0 && !expiring && !actionBusy) {
      showFinished(active, true);
      expiring = true;
      refreshExecution().then(() => notice(active.kind === 'break' ? '休息到时，准备好后开始下一项' : '工作片到时，已挂起。选择休息或轮转到下一项')).catch(error => notice(error.message, true)).finally(() => { expiring = false; });
    }
  }
  function renderSessions() {
    const names = new Map(allTasks().map(t => [t.id, t.title]));
    const dailyNames = new Map(state.todayTasks.map(t => [t.id, t.text]));
    $('#sessionList').innerHTML = state.sessions.length ? state.sessions.slice(0,40).map(s => {
      const assessment = s.assessment || {};
      return `<article class="session-card ${s.kind}"><div><strong>${s.kind === 'break' ? '休息' : esc(names.get(s.project_task_id) || dailyNames.get(s.daily_task_id) || s.label || '工作片')}</strong><div class="session-meta">${dtLabel(s.started_at)} → ${dtLabel(s.ended_at)} · ${s.duration_minutes ?? '进行中'} 分 · ${s.source === 'timer' ? '计时' : s.source === 'moment' ? '确认时刻' : '补记'}</div></div>
        ${s.ended_at ? `<details><summary>更正时间</summary><form class="correct-form" data-id="${s.id}"><label>开始 <input name="started_at" type="datetime-local" required value="${localInput(s.started_at)}"></label><label>结束 <input name="ended_at" type="datetime-local" required value="${localInput(s.ended_at)}"></label><label>更正原因 <input name="correction_note" maxlength="2000" required></label><button type="submit">保存更正</button></form></details>
        <p><a href="/static/index.html#time-log">在「记」中回看目标相关的重要性</a></p>` : ''}</article>`;
    }).join('') : '<p class="empty">还没有实际时间片。开始计时，或事后补记。</p>';
  }
  function renderTemplates() {
    $('#templateList').innerHTML = state.templates.length ? state.templates.map(t => `<article class="template-card"><h3>${esc(t.title)}</h3><p>${t.steps.length} 个步骤 · ${t.checklist.length} 个检查项</p><details class="template-content"><summary>查看步骤与完成检查</summary><ol>${t.steps.map(text=>`<li>${esc(text)}</li>`).join('')}</ol><ul>${t.checklist.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>${t.common_problems ? `<p>常见难点：${esc(t.common_problems)}</p>` : ''}${t.acceptance_criteria ? `<p>验收标准：${esc(t.acceptance_criteria)}</p>` : ''}</details><button type="button" class="secondary" data-act="edit-template" data-id="${t.id}">修改流程</button><details class="template-use"><summary>使用此流程</summary><form class="template-use-form" data-template="${t.id}"><label>放到哪里 <select name="destination" required><option value="">选择日程或项目</option><option value="schedule">日程</option><option value="project">项目</option></select></label><label class="template-day-target" hidden>安排日期 <input name="task_date" type="date" value="${esc(params.get('date') || todayISO())}" disabled></label><label class="template-project-target" hidden>选择项目 <select name="project_id" disabled><option value="">请选择项目</option>${state.overview.projects.filter(p=>!['delivered','accepted'].includes(p.execution_state)).map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('')}</select></label><label class="template-project-target" hidden>项目阶段 <select name="stage_id" disabled><option value="">先选择项目</option></select></label><button type="submit">生成任务</button></form><p>生成独立任务；流程后续修改保留已有内容和核对状态。</p></details></article>`).join('') : '<p class="empty">还没有流程。点“新建流程”写入方法，也可从项目任务保存。</p>';
  }
  function render() { renderGoals(); renderProjects(); renderTaskDetail(); renderExecution(); renderSessions(); renderTemplates(); globalThis.ShuranWorkspace?.sync(); }
  function formData(form) { return Object.fromEntries(new FormData(form)); }
  function nullableNumber(value) { return value === '' || value == null ? null : Number(value); }
  function lines(value) { return String(value || '').split(/\r?\n/).map(x => x.trim()).filter(Boolean); }

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('form')) return;
    event.preventDefault();
    run(async () => {
      const body = formData(form);
      if (form.id === 'goalForm') {
        await post('/goals', {title:body.title, horizon_end:body.horizon_end || null}); form.reset(); await afterChange('目标已保存');
      } else if (form.id === 'projectForm') {
        const result = await post('', {title:body.title, outcome:body.outcome || null, goal_id:nullableNumber(body.goal_id)});
        state.projectId = result.id; form.reset(); await afterChange('项目已建立');
      } else if (form.id === 'projectStateForm') {
        const acknowledge = body.state === 'started' ? await confirmReadiness('project', state.projectId) : false;
        await post(`/${state.projectId}/execution-state`, {state:body.state, reason:body.reason, acknowledge_reminders:acknowledge});
        await afterChange('项目状态已保存；依赖状态已重新核对');
      } else if (form.classList.contains('stage-task-form')) {
        if (!state.projectId) throw new Error('请先建立项目');
        const task = await post(`/${state.projectId}/tasks`, {title:body.title, stage_id:Number(form.dataset.stage),
          estimated_minutes:nullableNumber(body.estimated_minutes), familiarity:body.familiarity || null, execution_role:body.execution_role || 'formal',
          goal_reason:body.goal_reason || null, acceptance_criteria:body.acceptance_criteria || null});
        state.taskId = task.id; form.reset(); await afterChange('任务已加入阶段');
      } else if (form.classList.contains('stage-change')) {
        await post(`/stages/${form.dataset.stage}/activate`, {decision:body.decision, reason:body.reason || null});
        await afterChange(body.decision === 'continue' ? '继续当前阶段' : '阶段已调整');
      } else if (form.id === 'detailForm') {
        await patch(`/tasks/${state.taskId}`, {title:body.title, stage_id:nullableNumber(body.stage_id), estimated_minutes:nullableNumber(body.estimated_minutes), familiarity:body.familiarity || null,
          goal_reason:body.goal_reason || null, acceptance_criteria:body.acceptance_criteria || null,
          rehearsal_note:body.rehearsal_note || null, blocker_note:body.blocker_note || null, steps:lines(body.steps)});
        await afterChange('任务内容已保存');
      } else if (form.id === 'dependencyForm') {
        await post(`/tasks/${state.taskId}/dependencies`, {prerequisite_id:Number(body.prerequisite_id)}); await afterChange('前置关系已保存');
      } else if (form.id === 'checklistForm') {
        await post(`/tasks/${state.taskId}/checklist`, {text:body.text}); await afterChange('检查项已添加');
      } else if (form.id === 'finishTaskForm') {
        const result = await post(`/tasks/${state.taskId}/finish`, {result:body.result, outcome_note:body.outcome_note || null, variance_reason:body.variance_reason || null});
        await afterChange(result.unchecked_count ? `验收已保存；仍有 ${result.unchecked_count} 个检查项未完成` : '验收已保存');
      } else if (form.id === 'scheduleTaskForm') {
        await post(`/tasks/${state.taskId}/schedule`, {task_date:body.task_date}); await afterChange('已关联到 ' + body.task_date + ' 的日程；可从日程查看项目与投入');
      } else if (form.id === 'manualForm') {
        const source = body.source;
        const task = executionChoices(true).find(item => item.key === body.task_ref);
        if (!task) throw new Error('请先选择要补记的任务');
        await post('/sessions/manual', {project_task_id:task.project_task_id, daily_task_id:task.daily_task_id, label:task.title, source, kind:'work',
          time_log_node_id:source === 'moment' ? nullableNumber(body.time_log_node_id) : null, correction_note:body.correction_note || null,
          started_at:new Date(body.started_at).toISOString(), ended_at:new Date(body.ended_at).toISOString()});
        form.reset(); $('#momentNodeLabel').hidden = true; await afterChange('实际投入已保存');
      } else if (form.classList.contains('correct-form')) {
        await patch(`/sessions/${form.dataset.id}`, {started_at:new Date(body.started_at).toISOString(), ended_at:new Date(body.ended_at).toISOString(), correction_note:body.correction_note});
        await afterChange('片段已更正');
      } else if (form.id === 'templateForm') {
        const payload = {title:body.title, steps:lines(body.steps), checklist:lines(body.checklist), common_problems:body.common_problems || null, acceptance_criteria:body.acceptance_criteria || null};
        if (body.id) await put(`/templates/${body.id}`, payload); else await post('/templates', payload);
        form.reset(); $('#templateEditor').open = false; $('#templateEditor').hidden = true; await afterChange('流程已保存');
      } else if (form.classList.contains('template-use-form')) {
        if (body.destination === 'schedule') {
          await post(`/templates/${form.dataset.template}/schedule`, {task_date:body.task_date});
          location.href = `/static/index.html?schedule_date=${encodeURIComponent(body.task_date)}#schedule`;
        } else if (body.destination === 'project') {
          const projectId = Number(body.project_id);
          if (!projectId || !body.stage_id) throw new Error('请选择项目及阶段');
          const task = await post(`/templates/${form.dataset.template}/instantiate`, {project_id:projectId,stage_id:Number(body.stage_id)});
          state.projectId = projectId; state.taskId = task.id;
          await afterChange('流程已生成独立项目任务');
          globalThis.ShuranWorkspace?.show('projects');
          $('#taskDetail').scrollIntoView({block:'start'});
        }
      }
    });
  });

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-act], [data-next]');
    if (!button) return;
    run(async () => {
      const id = Number(button.dataset.id), action = button.dataset.act;
      if (action === 'select-task') { state.taskId = id; state.detailMode = 'attributes'; renderTaskDetail(); $('#taskDetail').scrollIntoView({behavior:'smooth',block:'start'}); }
      else if (action === 'queue-task') { await addQueue(`project:${state.taskId}`); globalThis.ShuranWorkspace?.show('execution'); notice('已加入轮转，准备好后开始'); }
      else if (action === 'close-detail') { state.taskId = null; renderTaskDetail(); }
      else if (action === 'detail-mode') { state.detailMode = button.dataset.mode; renderTaskDetail(); }
      else if (action === 'remove-dep') {
        const reason = window.prompt('移除前置会改变可执行状态，历史与实际投入仍保留。请说明原因：');
        if (reason?.trim()) { await request(`/tasks/${state.taskId}/dependencies/${id}?reason=${encodeURIComponent(reason.trim())}`, {method:'DELETE'}); await afterChange('前置关系已移除并留存原因'); }
      }
      else if (action === 'edit-goal') {
        const goal = state.overview.goals.find(g => g.id === id), title = window.prompt('修改目标', goal.title);
        if (title && title.trim()) { await patch(`/goals/${id}`, {title:title.trim()}); await afterChange('目标已修改；历史评价仍保留当时目标文字'); }
      }
      else if (action === 'save-template') { await post(`/tasks/${state.taskId}/save-template`, {}); await afterChange('已从任务保存流程'); globalThis.ShuranWorkspace?.show('templates'); }
      else if (action === 'edit-template') {
        const template = state.templates.find(t => t.id === id), form = $('#templateForm');
        form.elements.id.value = template.id; form.elements.title.value = template.title;
        form.elements.steps.value = template.steps.join('\n'); form.elements.checklist.value = template.checklist.join('\n');
        form.elements.common_problems.value = template.common_problems || '';
        form.elements.acceptance_criteria.value = template.acceptance_criteria || '';
        $('#templateEditor').hidden = false; $('#templateEditor').open = true;
        form.scrollIntoView({behavior:'smooth',block:'center'});
      }
      else if (action === 'instantiate') {
        const project = currentProject(), stage = project?.stages.find(s => s.state === 'current');
        if (!project) throw new Error('请先建立项目');
        const task = await post(`/templates/${id}/instantiate`, {project_id:project.id, stage_id:stage?.id || null});
        state.taskId = task.id; await afterChange('已生成可编辑任务');
      }
      else if (button.dataset.next) await chooseNext(button.dataset.next);
    });
  });
  document.addEventListener('change', event => {
    const el = event.target;
    if (el.id === 'projectSelect') { state.projectId = Number(el.value) || null; state.taskId = null; render(); }
    if (el.matches('[data-act=toggle-check]')) run(async () => { await patch(`/checklist/${el.dataset.id}?done=${el.checked}`, {}); await afterChange('检查项已更新'); });
    if (el.id === 'manualSource' || el.matches('#manualForm [name=started_at]')) run(loadMomentChoices);
    if (el.id === 'workMinutes' && !state.active) tick();
    const useForm = el.closest?.('.template-use-form');
    if (useForm && el.name === 'destination') {
      useForm.querySelectorAll('.template-day-target').forEach(label => {label.hidden = el.value !== 'schedule'; const input = $('input',label); input.disabled = label.hidden; input.required = !label.hidden;});
      useForm.querySelectorAll('.template-project-target').forEach(label => {label.hidden = el.value !== 'project'; const input = $('select',label); input.disabled = label.hidden; input.required = !label.hidden;});
    }
    if (useForm && el.name === 'project_id') {
      const project = state.overview.projects.find(p=>p.id === Number(el.value));
      useForm.elements.stage_id.innerHTML = stageOptions(project, null) || '<option value="">没有可用阶段</option>';
    }
  });

  async function loadMomentChoices() {
    const source = $('#manualSource').value, box = $('#momentNodeLabel');
    box.hidden = source !== 'moment';
    if (source !== 'moment') return;
    const started = $('#manualForm [name=started_at]').value;
    if (!started) { $('#momentNode').innerHTML = '<option value="">先填写开始时间</option>'; return; }
    const token = localStorage.getItem('authToken');
    const day = started.slice(0,10);
    const response = await fetch(`/api/time-log?log_date=${encodeURIComponent(day)}`, {headers:{Authorization:'Bearer ' + token}});
    if (!response.ok) throw new Error('加载时刻记录失败');
    const data = await response.json();
    $('#momentNode').innerHTML = '<option value="">选择并确认来源</option>' + (data.nodes || []).map(n => `<option value="${n.id}">${esc(dtLabel(n.logged_at))} · ${esc(n.label || '未填写')}</option>`).join('');
  }

  async function stopCurrent(message, pause = false) {
    if (!state.active) {
      if (state.plan.paused) { await post('/execution/discard-pause', {}); await afterChange(message); }
      return;
    }
    const endInput = $('#actualStopAt');
    const endedAt = endInput.value ? new Date(endInput.value).toISOString() : null;
    await post(`/sessions/${state.active.id}/stop`, {ended_at:endedAt, pause});
    endInput.value = '';
    await afterChange(message);
  }
  async function startWork(task = nextTask()) {
    if (!task || task.disabled) throw new Error('请先选择可开始的任务');
    const minutes = Number($('#workMinutes').value) || 20;
    const links = {project_task_id:task.project_task_id, daily_task_id:task.daily_task_id, label:task.title};
    const acknowledge = await confirmReadiness(task.project_task_id ? 'task' : 'daily', task.project_task_id || task.daily_task_id);
    const body = {...links, kind:'work', planned_minutes:minutes, acknowledge_reminders:acknowledge};
    if (state.active) await post('/sessions/switch', {...body, from_session_id:state.active.id});
    else await post('/sessions/start', body);
    await afterChange('工作片已开始');
  }
  async function chooseNext(choice) {
    if (choice === 'break') {
      if (state.active) await post(`/sessions/${state.active.id}/stop`, {});
      await post('/sessions/start', {kind:'break', planned_minutes:Number($('#breakMinutes').value) || 5});
      await afterChange('休息开始；这段时间不计任务实耗');
    } else if (choice === 'continue') {
      const task = sessionChoice(state.active?.kind === 'work' ? state.active : lastWork());
      await startWork(task);
    } else if (choice === 'switch') {
      const current = sessionChoice(state.active?.kind === 'work' ? state.active : state.plan.paused?.kind === 'work' ? state.plan.paused : lastWork());
      const index = state.plan.queue.findIndex(key => choiceFor(key)?.key === current?.key);
      if (index >= 0) { const keys = [...state.plan.queue]; keys.push(...keys.splice(index, 1)); await saveQueue(keys); }
      const task = nextTask();
      if (!task) throw new Error('轮转中没有可开始的任务，请先加入任务');
      await startWork(task);
    }
  }
  $('#startWork').addEventListener('click', () => { prepareSound(); run(async () => {
    if (state.plan.paused) {
      const old = state.plan.paused;
      const acknowledge = old.kind === 'work' ? await confirmReadiness(old.project_task_id ? 'task' : 'daily', old.project_task_id || old.daily_task_id) : false;
      await post('/execution/resume' + (acknowledge ? '?acknowledge_reminders=true' : ''), {}); await afterChange('已恢复剩余时间');
    }
    else if (lastWork()) await chooseNext('switch');
    else await startWork();
  }); });
  $('#focusAcknowledge').addEventListener('click', acknowledgeFinished);
  $('#focusEnableNotifications').addEventListener('click', async () => {
    const native = nativeBridge();
    if (native?.requestPermission) native.requestPermission();
    else if (globalThis.Notification?.requestPermission) await globalThis.Notification.requestPermission();
    notificationSettings();
  });
  $('#pauseWork').addEventListener('click', () => run(() => stopCurrent('已暂停；暂停期间不计任务实耗', true)));
  $('#endWork').addEventListener('click', () => run(() => stopCurrent('片段已结束')));
  $('#switchWork').addEventListener('click', () => run(() => chooseNext('switch')));
  $('#resetTemplate').addEventListener('click', () => { $('#templateForm').reset(); $('#templateEditor').open = false; $('#templateEditor').hidden = true; });
  $('#addQueueTask').addEventListener('click', () => run(() => addQueue($('#focusTask').value)));
  $('#addTodayQueue').addEventListener('click', () => run(async () => {
    const keys = new Set(state.plan.queue);
    executionChoices().filter(t => t.group === '今日任务' && !t.disabled).forEach(t => keys.add(t.key));
    await saveQueue([...keys]); renderExecution();
  }));
  $('#rotationQueue').addEventListener('click', event => {
    const button = event.target.closest('[data-queue]'); if (!button) return;
    run(async () => {
      const keys = [...state.plan.queue], i = Number(button.dataset.index), act = button.dataset.queue;
      if (act === 'remove') keys.splice(i, 1);
      else { const j = i + (act === 'up' ? -1 : 1); [keys[i], keys[j]] = [keys[j], keys[i]]; }
      await saveQueue(keys); renderExecution();
    });
  });
  for (const id of ['workMinutes', 'breakMinutes']) $("#" + id).addEventListener('change', () => run(async () => { await saveQueue(); renderExecution(); }));
  $('#confirmDailyProject').addEventListener('click', () => run(async () => {
    const task = await post(`/daily/${Number(params.get('daily'))}/project`, {project_id:state.projectId});
    params.delete('daily'); state.taskId = task.id; await afterChange('已纳入项目，原日程和投入记录已关联');
  }));
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !actionBusy) run(refreshExecution); });

  setInterval(tick, 1000);
  refresh().then(async () => {
    const key = params.get('execute');
    if (key && choiceFor(key) && !choiceFor(key).disabled) await addQueue(key);
    if (params.get('finish') || params.get('task')) $('#taskDetail').scrollIntoView({block:'start'});
  }).catch(error => notice(error.message, true));
})();
