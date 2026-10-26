(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const state = { overview: {goals:[], projects:[]}, todayTasks:[], templates:[], sessions:[], projectId:null, taskId:null, active:null, detailMode:'attributes' };
  const params = new URLSearchParams(location.search);
  state.plan = {queue:[], daily_tasks:[], work_minutes:20, break_minutes:5};
  let noticeTimer, actionBusy = false, expiring = false, hydrated = false;
  let finishedId = null, soundContext = null, finishedTimer;

  const desktopNative = /ShuranDesktop\//.test(globalThis.navigator?.userAgent || '') && globalThis.chrome?.webview;
  function nativeBridge() { return globalThis.ShuranNative || (desktopNative ? {
    hasPermission: () => true,
    setFocusTimer: json => desktopNative.postMessage({type:'focusTimer', data:JSON.parse(json)}),
  } : null); }
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
        deadline_ms:Date.parse(active.deadline_at) - (state.clockOffset || 0),
        server_deadline_ms:Date.parse(active.deadline_at),
        break_minutes:state.plan.break_minutes
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
    clearTimeout(finishedTimer);
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
      const audio = new globalThis.Audio('/static/audio/focus-falling-pluck.wav');
      audio.play().catch(() => {});
    } catch (_) { /* The visible reminder still works without audio. */ }
  }
  function showFinished(session, live = false) {
    if (!session || localStorage.getItem('focusFinishedSession') === String(session.id)) return;
    const isNew = finishedId !== session.id;
    finishedId = session.id;
    $('#focusFinishedTitle').textContent = session.kind === 'break' ? '休息结束，准备好再开始' : `工作片结束，休息 ${state.plan.break_minutes} 分钟`;
    $('#focusFinishedText').textContent = session.kind === 'break'
      ? '这段休息结束了。准备好后开始下一项。'
      : '休息已自动开始。先不看手机，也不查看消息。站起来走走，让眼睛离开屏幕。';
    $('#focusFinished').hidden = false;
    if (isNew) {
      clearTimeout(finishedTimer);
      finishedTimer = setTimeout(acknowledgeFinished, 8000);
    }
    if (!isNew || !live) return;
    if (!nativeBridge()) soundFinished();
    if (!nativeBridge() && document.hidden && globalThis.Notification?.permission === 'granted') {
      try { new globalThis.Notification('书然 · ' + $('#focusFinishedTitle').textContent, {
        body:$('#focusFinishedText').textContent, tag:'shuran-focus-' + session.id
      }); } catch (_) { /* The in-page reminder remains visible. */ }
    }
  }
  function restoreFinished() {
    const active = state.active;
    if (active?.kind === 'break') {
      const previous = state.sessions.find(s => s.kind === 'work' && s.ended_at === active.started_at);
      if (previous) showFinished(previous);
      return;
    }
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
        project_task_id:linked?.id || null, daily_task_id:task.id, project_day_plan:task.project_day_plan || null,
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
  function stageName(stage) { return stage.unassigned ? '不分阶段' : stage.state === 'current' ? '当前阶段' : stage.state === 'next' ? '下一阶段' : '已结束'; }
  function dailyProgress(task) {
    const rows = task.daily_progress || [];
    return rows.length ? `<details class="project-daily-progress"><summary>每日推进 · ${rows.length} 项安排</summary>${rows.map(row => `<p><a href="/static/index.html?schedule_date=${encodeURIComponent(row.date)}#schedule">${esc(row.date)}</a> · ${esc(row.text)} · ${row.completed ? '当天已完成' : '继续推进'}${row.note ? `<br>${esc(row.note)}` : ''}</p>`).join('')}</details>` : '';
  }
  function goalOptions(selected) { return '<option value="">暂不关联</option>' + state.overview.goals.map(g => `<option value="${g.id}" ${g.id === selected ? 'selected' : ''}>${esc(g.title)}</option>`).join(''); }
  function stageOptions(project, selected) { return '<option value="" '+(selected==null?'selected':'')+'>不分阶段</option>'+(project?.stages || []).filter(s => s.state !== 'closed').map(s => `<option value="${s.id}" ${s.id === selected ? 'selected' : ''}>${esc(s.title)} · ${stageName(s)}</option>`).join(''); }

  async function refresh() {
    state.plan = await request('/execution');
    const [overview, templates, sessions, todayTasks] = await Promise.all([request('/overview'), request('/templates'), request('/sessions'), loadTodayTasks()]);
    state.overview = overview; state.templates = templates.items; state.sessions = sessions.items; state.todayTasks = todayTasks;
    if (!overview.projects.some(p => p.id === state.projectId)) state.projectId = overview.projects[0]?.id ?? null;
    if (!currentProject()?.tasks.some(t => t.id === state.taskId)) state.taskId = null;
    state.active = state.sessions.find(s => !s.ended_at) || null;
    syncFocusAlarm(); notificationSettings();
    if (!hydrated) {
      const selected=overview.projects.find(p=>p.id===Number(params.get('project')));
      if(selected)state.projectId=selected.id;
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
      `<span class="chip">${esc(g.title)}${g.horizon_end ? `<small>至 ${esc(g.horizon_end)}</small>` : ''}${g.status==='stopped'?'<small>已停止，历史保留</small>':''} <button type="button" class="plain-action" data-act="edit-goal" data-id="${g.id}" aria-label="修改目标 ${esc(g.title)}">修改</button><button type="button" class="plain-action" data-act="goal-feasibility" data-id="${g.id}">可行性</button></span>`).join('') : '<p class="empty">先从一个近期目标开始；简单事项也可以不建目标。</p>';
    $('#projectGoal').innerHTML = goalOptions(null);
  }
  function renderProjects() {
    const projects = state.overview.projects;
    $('#projectSelect').innerHTML = projects.length ? projects.map(p => `<option value="${p.id}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.title)}</option>`).join('') : '<option value="">还没有项目</option>';
    const project = currentProject(); $('#projectOutcome').textContent = project?.outcome || '';
    const deleteButton = $('#deleteProject');
    if (deleteButton) { deleteButton.disabled = !project; deleteButton.setAttribute?.('data-project-delete', `project:${project?.id || ''}`); }
    globalThis.ShuranDeletion?.refreshCount();
    $('#projectLifecycle').innerHTML = project ? `<h3>项目执行状态</h3>
      <p>${esc(({preparation:'筹备中：正式任务需先检查条件并开始项目',started:'已正式开始',delivered:'已交付，待验收',accepted:'已验收'})[project.execution_state] || '历史项目：未记录正式启动，保留原有可用性')}${project.started_at ? ` · 首次正式开始 ${dtLabel(project.started_at)}` : ''}</p>
      <details><summary>变更项目状态</summary><p>当前列表是本阶段的执行承诺。严格执行有助于集中投入、完成关键工作，并检验原先的计划是否合理。后续想法先放入下一阶段，避免不断打断当前任务。</p><form id="projectStateForm"><label>操作 <select name="state"><option value="started">检查条件并正式开始／重新开始</option><option value="delivered">确认已经交付</option><option value="accepted">确认已经验收</option><option value="preparation">交付后重新筹备（保留历史）</option></select></label><label>判断依据或原因 <input name="reason" required maxlength="4000"></label><button type="submit">确认项目状态</button></form></details>` : '';
    if (project) globalThis.ShuranConditions?.mount($('#projectConditions'), 'project', project.id, () => afterChange());
    else $('#projectConditions').innerHTML = '';
    const stages=project?[...project.stages]:[];
    if(project?.tasks.some(t=>t.stage_id==null))stages.push({id:null,title:'项目任务（未分阶段）',state:'current',unassigned:true});
    $('#stageBoard').innerHTML = project ? stages.map(s => {
      const tasks = project.tasks.filter(t => t.stage_id === s.id);
      const open = !s.unassigned && (s.state === 'current' || s.state === 'next');
      const stageLabel = stageName(s);
      return `<article class="stage ${esc(s.state)}"><div class="stage-header"><h3>${esc(s.title)}</h3><div class="stage-delete-actions"><span class="state-tag">${stageName(s)}</span>${s.unassigned ? '' : `<button type="button" class="project-delete-button" data-project-delete="stage:${s.id}">删除阶段</button>`}</div></div>
        ${s.state === 'current' && !s.unassigned ? '<div data-stage-commitment></div>' : ''}
        ${tasks.length ? tasks.map(t => `<div class="task-row ${!t.can_start ? 'blocked' : ''} ${t.state === 'completed' ? 'done' : ''}"><button type="button" data-act="select-task" data-id="${t.id}">${esc(t.title)}<small>${t.execution_role === 'preparation' ? '筹备任务 · ' : ''}${t.state === 'completed' ? '已完成' : esc(t.readiness?.summary || (t.blocked_by.length ? '等待前置任务' : '可以推进'))} · ${{simple:'简单',difficult:'困难'}[t.practice?.difficulty]||'难度未标'} · ${{unimportant:'不重要',ordinary:'一般',important:'重要'}[t.practice?.importance]||'重要性未标'}${t.practice?.reviewed_at?'':' · 待审视'} · 原估计 ${t.original_estimate_minutes ?? '未填'} 分 · 实耗 ${t.actual_minutes} 分</small></button><button type="button" class="project-delete-button" data-project-delete="task:${t.id}" aria-label="删除任务：${esc(t.title)}">删除</button></div>`).join('') : `<p class="stage-empty">这里还没有任务${open ? '，可以在下方写入第一项。' : '。'}</p>`}
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
        ${s.state === 'next' ? `<div class="stage-transition"><button type="button" class="secondary" data-act="stage-handover" data-id="${s.id}">核对结果并交接到此阶段</button></div>` : ''}</article>`;
    }).join('') : '<p class="empty">建立项目后，这里会出现当前阶段和下一阶段。</p>';
    if(project && !project.stages.some(s => s.state === 'current')) $('#stageBoard').insertAdjacentHTML?.('afterbegin', '<p class="stage-empty">项目暂时没有当前阶段。可以在“已删除”中恢复，或切换到“下一阶段”主动交接。</p>');
    if(project)globalThis.ShuranCommitments?.mount($('#stageBoard').querySelector('[data-stage-commitment]'),project.id,{onChanged:()=>afterChange()});
  }
  function renderTaskDetail() {
    const root = $('#taskDetail'), task = currentTask(), project = currentProject();
    if (!task) { root.hidden = true; return; }
    root.hidden = false;
    const choices = project.tasks.filter(t => t.id !== task.id).map(t => `<option value="${t.id}">${esc(t.title)}</option>`).join('');
    const prereq = task.prerequisite_ids.map(id => project.tasks.find(t => t.id === id)).filter(Boolean);
    const readRow = (label, value, emptyLabel, control) => `<div class="detail-read-row"><div><span>${label}</span><p>${value ? esc(value) : '尚未填写'}</p></div><details><summary>${value ? '修改' : `＋${emptyLabel}`}</summary>${control}</details></div>`;
    const scheduled = (task.scheduled_dates || []).map(day => `<a href="/static/index.html?schedule_date=${day}#schedule">${day}</a>`).join(' · ');
    root.innerHTML = `<div class="detail-header"><div><span class="detail-kicker">当前任务</span><h3>${esc(task.title)}</h3></div><button type="button" class="secondary" data-act="close-detail">收起</button></div>
      <div class="task-metrics"><span>原估计 ${task.original_estimate_minutes ?? '未填'} 分</span><span>当前估计 ${task.estimated_minutes ?? '未填'} 分</span><span>实际投入 ${task.actual_minutes} 分</span>${task.difference_minutes == null ? '' : `<span>差额 ${task.difference_minutes > 0 ? '+' : ''}${task.difference_minutes} 分</span>`}</div>
      <p class="detail-status">${esc(task.readiness?.summary || '未配置启动条件')} · ${task.execution_role === 'preparation' ? '筹备任务：不继承项目条件' : '正式任务：继承项目条件'}</p>
      ${dailyProgress(task)}
      <div class="detail-command-row"><button type="button" data-act="queue-task" ${task.can_start ? '' : 'disabled'}>加入时间片轮转</button><details class="schedule-editor"><summary>${scheduled ? '调整日期' : '＋安排日期'}</summary><form id="scheduleTaskForm"><label>安排到哪天<input name="task_date" type="date" required></label><button type="submit">写入日程</button></form></details><a href="/static/index.html#schedule">查看日程</a><span class="scheduled-dates">${scheduled || '尚未安排日程'}</span></div>
      <div class="detail-tabs" role="tablist" aria-label="任务操作分区"><button type="button" aria-selected="${state.detailMode === 'attributes'}" data-act="detail-mode" data-mode="attributes">任务内容</button><button type="button" aria-selected="${state.detailMode === 'conditions'}" data-act="detail-mode" data-mode="conditions">开始准备</button><button type="button" aria-selected="${state.detailMode === 'dependencies'}" data-act="detail-mode" data-mode="dependencies">完成检查</button><button type="button" aria-selected="${state.detailMode === 'completion'}" data-act="detail-mode" data-mode="completion">结果反馈</button></div>
      <div class="detail-zone" data-detail-zone="attributes" ${state.detailMode === 'attributes' ? '' : 'hidden'}><form id="detailForm" class="compact-detail-form">
        <div class="detail-property-row"><label>阶段<select name="stage_id">${stageOptions(project, task.stage_id)}</select></label><label>熟悉程度<select name="familiarity"><option value="">未标记</option><option value="familiar" ${task.familiarity === 'familiar' ? 'selected' : ''}>熟悉</option><option value="unfamiliar" ${task.familiarity === 'unfamiliar' ? 'selected' : ''}>陌生</option></select></label><button type="button" class="secondary" data-act="practice-task">难度与重要性</button></div>
        ${readRow('任务名称', task.title, '修改任务名称', `<label>任务名称<input name="title" maxlength="500" required value="${esc(task.title)}"></label>`)}
        ${readRow('任务目的', task.goal_reason, '补充任务目的', `<label>为什么对目标有用<textarea name="goal_reason" rows="2">${esc(task.goal_reason)}</textarea></label>`)}
        ${readRow('完成标准', task.acceptance_criteria, '补充完成标准', `<label>怎样算完成<textarea name="acceptance_criteria" rows="2">${esc(task.acceptance_criteria)}</textarea></label>`)}
        ${readRow('预计用时', task.estimated_minutes == null ? '' : `${task.estimated_minutes} 分钟`, '填写预计用时', `<label>当前估计分钟<input name="estimated_minutes" type="number" min="0" value="${task.estimated_minutes ?? ''}"></label>`)}
        <input type="hidden" name="rehearsal_note" value="${esc(task.rehearsal_note)}">
        <details class="detail-advanced"><summary>流程步骤与原有笔记</summary>
          ${readRow('流程步骤', task.steps.join('；'), '补充流程步骤', `<label>每行一项<textarea name="steps" rows="3">${esc(task.steps.join('\n'))}</textarea></label>`)}
          ${readRow('难点或阻碍', task.blocker_note, '补充难点或阻碍', `<label>难点或阻碍<textarea name="blocker_note" rows="2">${esc(task.blocker_note)}</textarea></label>`)}
          <p class="detail-note">原有预演笔记：${esc(task.rehearsal_note || '尚未记录；可到“开始准备”填写。')}</p>
        </details><button type="submit" class="detail-save">保存任务内容</button></form></div>
      <div class="detail-zone" data-detail-zone="conditions" ${state.detailMode === 'conditions' ? '' : 'hidden'}><div class="detail-section-head"><div><h4>开始前核对</h4><p>先确认真正影响开始的条件，需要时再补充。</p></div><button type="button" data-act="practice-rehearsal">开始前预演</button></div><div id="taskConditions" class="condition-workspace"></div>
        <details class="detail-advanced"><summary>原有任务前置关系</summary><p>${prereq.length ? prereq.map(t => `${esc(t.title)} <button type="button" class="secondary" data-act="remove-dep" data-id="${t.id}">说明原因并移除</button>`).join(' · ') : '未配置原有任务前置。其他条件见上方。'}</p>${prereq.length ? '<label>移除前置关系的原因<input id="dependencyRemovalReason" maxlength="4000" placeholder="说明为什么该前置不再适用"></label>' : ''}
        <form id="dependencyForm"><label>必须先完成<select name="prerequisite_id">${choices}</select></label><button type="submit" ${choices ? '' : 'disabled'}>添加前置</button></form></details></div>
      <div class="detail-zone" data-detail-zone="dependencies" ${state.detailMode === 'dependencies' ? '' : 'hidden'}><div class="detail-section-head"><div><h4>完成检查</h4><p>这些项目用于核对交付，不会暗中成为开始门槛。</p></div><button type="button" class="secondary" data-act="practice-checklist">编辑顺序与不适用说明</button></div><ul class="detail-checklist">${task.checklist.map(item => `<li><label class="check"><input type="checkbox" data-act="toggle-check" data-id="${item.id}" ${item.done ? 'checked' : ''}>${item.group==='preparation'?'准备核对：':'交付核对：'}${esc(item.text)}</label>${item.not_applicable?`<small>本次不适用：${esc(item.not_applicable)}</small>`:''}</li>`).join('') || '<li class="detail-note">还没有检查项</li>'}</ul>
        <details class="inline-add"><summary>＋新增检查项</summary><form id="checklistForm"><label>检查项<input name="text" maxlength="500" required></label><button type="submit">添加</button></form></details></div>
      <div class="detail-zone" data-detail-zone="completion" ${state.detailMode === 'completion' ? '' : 'hidden'}><div class="detail-section-head"><div><h4>结果与用时</h4><p>完成后一次核对实际结果、累计用时和下次经验。</p></div><button type="button" data-act="practice-feedback">记录结果与用时</button></div>
        <div class="detail-result-summary"><span>完成标准</span><p>${esc(task.acceptance_criteria || '尚未填写，可先判断实际结果。')}</p></div>
        <details class="inline-add"><summary>保存为可复用流程</summary><p class="detail-note">会保留这项任务的步骤和检查方式，供以后生成新任务。</p><button type="button" class="secondary" data-act="save-template">保存为流程</button></details></div>`;
    const date = $('#scheduleTaskForm [name=task_date]', root); if (date) date.value = params.get('date') || todayISO();
    globalThis.ShuranConditions?.mount($('#taskConditions', root), 'task', task.id, () => afterChange());
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
    const practice = $('#executionPractice');
    if (practice) {
      const target = current?.kind === 'work' ? current : nextTask();
      const scoped = target?.project_day_plan || (target?.daily_task_id && sessionChoice(target)?.project_day_plan);
      const taskId = scoped ? target.daily_task_id : target?.project_task_id || target?.daily_task_id;
      const kind = target?.project_task_id && !scoped ? 'task' : 'daily';
      const r = current?.practice_snapshot?.rehearsal || {};
      practice.hidden = !taskId;
      practice.innerHTML = taskId ? `${kind==='task'&&!active?'<p class="practice-note">当前列表是本阶段的执行承诺；先集中完成关键工作，后续想法放入下一阶段。</p>':''}${r.first_step?`<p><strong>第一步</strong> ${esc(r.first_step)}</p>`:''}${r.preparation?`<p>关键准备：${esc(r.preparation)}</p>`:''}${r.response?`<p>卡住时：${esc(r.response)}</p>`:''}<button type="button" data-execution-practice="${kind}:${taskId}" data-section="rehearsal">预演与有点难开始</button><button type="button" data-execution-practice="${kind}:${taskId}" data-section="feedback">核对结果与用时</button>` : '';
    }
    const link = $('#activeProjectLink'); link.hidden = !projectTask;
    if (projectTask) { link.href = `/static/projects.html?task=${projectTask.id}#taskDetail`; link.textContent = `${projectTask.project_title} · 查看任务与投入`; }
    $('.focus-panel').classList.toggle('break', active?.kind === 'break');
    $('#startWork').textContent = paused ? '恢复剩余时间' : lastWork() ? '开始下一项' : '开始队首任务';
    $('#startWork').disabled = !!active || (!paused && !nextTask());
    $('#pauseWork').disabled = !active;
    $('#endWork').disabled = !active && !paused;
    $('#endWork').textContent = active?.kind === 'break' ? '提前结束休息' : '结束片段';
    $('#completeCurrentTask').hidden = !active || active.kind !== 'work';
    $('#completeCurrentTask').textContent = currentChoice?.project_day_plan ? '今日目标完成' : '完成当前任务';
    const handoff = state.plan.handoff;
    $('#timerControls').hidden = !!handoff;
    $('[data-next=break]').classList.toggle('secondary', !!handoff);
    $('#switchWork').disabled = !nextTask();
    $('#actualStopWrap').hidden = !active;
    const decision = !active && !paused && !!lastWork();
    $('#timeDecision').hidden = !decision;
    const remainingLabel = `${Math.floor((state.plan.remaining_seconds || 0) / 60)}分${(state.plan.remaining_seconds || 0) % 60}秒`;
    $('#decisionCaption').textContent = handoff ? `任务已完成，本次实际投入已保存。工作片还剩 ${remainingLabel}；等待选择期间不计时。` : state.sessions[0]?.kind === 'break' ? '休息已结束，准备好后开始下一项。' : '这一片已挂起，未完成的任务保留在轮转中。';
    $('[data-next=switch]').textContent = handoff ? `用余下 ${remainingLabel} 做下一项` : '做下一项';
    $('[data-next=switch]').disabled = !nextTask();
    $('[data-next=continue]').hidden = !!handoff;
    if (handoff) {
      $('#startWork').textContent = '用剩余时间做下一项';
      $('#switchWork').textContent = '用剩余时间做下一项';
    } else $('#switchWork').textContent = '挂起并做下一项';
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
    $('#focusRestRemaining').textContent = active?.kind === 'break' ? `休息中 ${$('#timerDisplay').textContent}` : '当前未计工作时间';
    $('#timerCaption').textContent = active ? active.kind === 'break' ? '休息中 · 结束后提醒你主动开始下一片' : '工作中 · 到时自动进入休息' : state.plan.paused ? '已暂停 · 恢复后接着剩余时间' : lastWork() ? '等待下一步 · 当前不计时' : '准备开始工作片';
    $('#sliceProgress').max = budget; $('#sliceProgress').value = active ? budget - remaining : 0;
    if (active && remaining === 0 && !expiring && !actionBusy) {
      showFinished(active, true);
      expiring = true;
      refreshExecution().then(() => notice(active.kind === 'break' ? '休息到时，准备好后开始下一项' : '休息已自动开始。先不看手机，也不查看消息。站起来走走，让眼睛离开屏幕。')).catch(error => notice(error.message, true)).finally(() => { expiring = false; });
    }
  }
  function renderSessions() {
    const names = new Map(allTasks().map(t => [t.id, t.title]));
    const dailyNames = new Map(state.todayTasks.map(t => [t.id, t.text]));
    $('#sessionList').innerHTML = state.sessions.length ? state.sessions.slice(0,40).map(s => {
      const assessment = s.assessment || {};
      return `<article class="session-card ${s.kind}"><div><strong>${s.kind === 'break' ? '休息' : esc(names.get(s.project_task_id) || dailyNames.get(s.daily_task_id) || s.label || '工作片')}</strong>${s.source_deleted ? '<small> · 来源已删除，历史投入保留</small>' : ''}<div class="session-meta">${dtLabel(s.started_at)} → ${dtLabel(s.ended_at)} · ${s.duration_minutes ?? '进行中'} 分 · ${s.source === 'timer' ? '计时' : s.source === 'moment' ? '确认时刻' : '补记'}</div></div>
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
    if (form.closest?.('.practice-dialog')) return;
    if (!form.matches('form')) return;
    event.preventDefault();
    run(async () => {
      const body = formData(form);
      if (form.id === 'goalForm') {
        const goal=await post('/goals', {title:body.title, horizon_end:body.horizon_end || null}); form.reset(); await afterChange('目标已保存'); await globalThis.ShuranPractice?.openGoal(goal.id);
      } else if (form.id === 'projectForm') {
        const result = await post('', {title:body.title, outcome:body.outcome || null, goal_id:nullableNumber(body.goal_id),tasks:ShuranFeedback.composer.read(form)});
        state.projectId = result.id; form.reset(); ShuranFeedback.composer.reset(form); await afterChange('项目与阶段任务已保存'); await globalThis.ShuranPractice?.openProject(result.id,'feasibility');
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
        if (body.decision !== 'continue') { await globalThis.ShuranPractice?.openProject(state.projectId,'commitment'); return; }
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
        await globalThis.ShuranPractice?.openTask('task',state.taskId,'feedback');
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
      else if (action === 'stage-handover') {
        if (!currentProject()?.stages.some(s => s.state === 'current')) globalThis.ShuranDeletion?.activateStage(id, currentProject()?.stages.find(s => s.id === id)?.title || '下一阶段');
        else await globalThis.ShuranPractice?.openProject(state.projectId,'commitment',id);
      }
      else if (action === 'practice-task') await globalThis.ShuranPractice?.openTask('task',state.taskId,'attributes');
      else if (action === 'practice-rehearsal') await globalThis.ShuranPractice?.openTask('task',state.taskId,'rehearsal');
      else if (action === 'practice-feedback') await globalThis.ShuranPractice?.openTask('task',state.taskId,'feedback');
      else if (action === 'practice-checklist') await globalThis.ShuranPractice?.openTask('task',state.taskId,'checklist');
      else if (action === 'queue-task') { await addQueue(`project:${state.taskId}`); globalThis.ShuranWorkspace?.show('execution'); notice('已加入轮转，准备好后开始'); }
      else if (action === 'close-detail') { state.taskId = null; renderTaskDetail(); }
      else if (action === 'detail-mode') {
        state.detailMode = button.dataset.mode;
        const root = button.closest('#taskDetail');
        root?.querySelectorAll('[data-act="detail-mode"]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.mode === state.detailMode)));
        root?.querySelectorAll('[data-detail-zone]').forEach(zone => { zone.hidden = zone.dataset.detailZone !== state.detailMode; });
      }
      else if (action === 'remove-dep') {
        const input = $('#dependencyRemovalReason'), reason = input?.value.trim();
        if (!reason) {input?.focus();throw new Error('请先填写移除前置关系的原因；历史与实际投入仍保留');}
        await request(`/tasks/${state.taskId}/dependencies/${id}?reason=${encodeURIComponent(reason)}`, {method:'DELETE'}); await afterChange('前置关系已移除并留存原因');
      }
      else if (action === 'goal-feasibility') await globalThis.ShuranPractice?.openGoal(id);
      else if (action === 'edit-goal') await globalThis.ShuranPractice?.openGoal(id,'goal-settings');
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
  $('#completeCurrentTask').addEventListener('click', () => run(async () => {
    if (!state.active || state.active.kind !== 'work') return;
    await post(`/sessions/${state.active.id}/complete`, {});
    await afterChange('任务已完成，实际用时已保存；选择接着做下一项或现在休息');
  }));
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
  globalThis.addEventListener?.('shuran-practice-change', () => run(() => afterChange()));
  for (const [id,section] of [['projectFeasibility','feasibility'],['projectCommitment','commitment'],['projectCycles','cycles']]) {
    $('#' + id)?.addEventListener('click', () => { if(state.projectId) globalThis.ShuranPractice?.openProject(state.projectId,section); });
  }
  document.addEventListener('click', event => {
    const el=event.target.closest('[data-execution-practice]'); if(!el)return;
    const [kind,id]=el.dataset.executionPractice.split(':'); globalThis.ShuranPractice?.openTask(kind,Number(id),el.dataset.section);
  });


  globalThis.ShuranDeletion?.configure({onChanged: message => {state.taskId = null;return afterChange(message);}});
  setInterval(tick, 1000);
  refresh().then(async () => {
    const key = params.get('execute');
    if (key && choiceFor(key) && !choiceFor(key).disabled) await addQueue(key);
    if (params.get('finish') || params.get('task')) $('#taskDetail').scrollIntoView({block:'start'});
  }).catch(error => notice(error.message, true));
})();
