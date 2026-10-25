(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels = {task:'前置任务',project:'前置项目',resource:'材料与资源',external:'外部条件',time:'时间条件',constraint:'执行约束'};
  async function request(path, method = 'GET', body) {
    const response = await fetch('/api/projects' + path, {method,
      headers:{Authorization:'Bearer ' + localStorage.getItem('authToken'), ...(body ? {'Content-Type':'application/json'} : {})},
      ...(body ? {body:JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查填写内容');
    return data;
  }
  function options(values, current) { return Object.entries(values).map(([value, text]) => `<option value="${value}" ${value === current ? 'selected' : ''}>${text}</option>`).join(''); }
  const confirmations = {unknown:'未确认',unmet:'未满足',met:'已满足',not_applicable:'不适用（需说明）'};
  const strengths = {required:'必须满足',reminder:'提醒事项'};
  const timings = {start:'开始前',throughout:'开始及执行期间',delivery:'交付前'};
  function describeEvent(event) {
    const before = JSON.parse(event.before_json || 'null'), after = JSON.parse(event.after_json || 'null');
    const title = after?.title || before?.title || '';
    const action = ({condition_created:'添加条件',condition_updated:'修改条件',condition_removed:'移除条件',
      dependency_added:'添加任务前置',dependency_removed:'移除任务前置',project_state_changed:'项目执行状态变化',
      actual_work_recorded:'补记实际工作'})[event.action] || '执行条件记录';
    const status = value => value ? [strengths[value.strength], confirmations[value.confirmation], value.evidence].filter(Boolean).join(' · ') : '';
    const changed = event.action === 'condition_updated' ? `（${status(before)} → ${status(after)}）` : '';
    return `${action}${title ? '：' + title : ''}${changed}`;
  }

  async function mount(root, kind, id, onChange) {
    if (!root) return;
    const token = `${kind}:${id}`; root.dataset.owner = token;
    const generation = root._conditionGeneration = (root._conditionGeneration || 0) + 1;
    root.innerHTML = '<p role="status">正在核对开始条件…</p>';
    try {
      const [ready, overview, history] = await Promise.all([
        request(`/readiness/${kind}/${id}`), request('/overview'), request(`/conditions/${kind}/${id}/history`)]);
      if (root.dataset.owner !== token || root._conditionGeneration !== generation) return;
      const own = ready.conditions.filter(c => !c.inherited), inherited = ready.conditions.filter(c => c.inherited);
      const tasks = overview.projects.flatMap(p => p.tasks.map(t => ({...t, project_title:p.title})));
      root.innerHTML = `<h4>开始条件与约束</h4>
        <p class="condition-summary">${esc(ready.summary)}</p>
        <p class="condition-help">只核对明确配置的条件；连续可用时间、预算和外部事实需自己确认。条件属于本项，不自动作用于独立子任务。项目条件仅由正式执行任务继承。</p>
        ${inherited.length ? `<details><summary>继承项目条件（${inherited.length}项）</summary>${inherited.map(c => `<p>${esc(c.source_title)} → ${esc(c.title)} · ${esc(strengths[c.strength])} · ${esc(c.detail)}</p>`).join('')}<p>请在所属项目的条件区修改。</p></details>` : ''}
        <div class="condition-list">${own.map(c => `<details class="condition-item"><summary>${esc(c.title)} · ${esc(strengths[c.strength])} · ${esc(c.detail)}</summary>
          <p>${esc(labels[c.kind])} · ${esc(timings[c.check_at])}${c.evidence ? ` · 依据：${esc(c.evidence)}` : ''}</p>
          <form data-update-condition="${c.id}">
            <label>要求强度 <select name="strength">${options(strengths, c.strength)}</select></label>
            <label>检查时机 <select name="check_at">${options(timings, c.check_at)}</select></label>
            ${c.kind === 'task' || c.kind === 'project' || c.not_before ? '<p>此条件由系统判断，不能手动勾选。</p>' : `<label>确认状态 <select name="confirmation">${options(confirmations, c.confirmation)}</select></label>`}
            <label>依据或不适用说明 <textarea name="evidence" maxlength="4000" rows="2">${esc(c.evidence)}</textarea></label>
            <label>本次更改原因 <input name="reason" maxlength="4000" required></label>
            <button type="submit">保存确认与变更</button>
          </form><button type="button" class="secondary" data-remove-condition="${c.id}">说明原因并移除条件</button>
        </details>`).join('') || `<p>${inherited.length ? '没有单独配置的任务条件；继承项目条件见上方。' : '本项尚未配置条件，可以逐步补充。'}</p>`}</div>
        <details class="condition-create"><summary>添加开始条件或执行约束</summary>
          <form data-create-condition class="condition-form">
            <label>条件内容 <input name="title" maxlength="500" required placeholder="例如：收到对方确认，或设备可用"></label>
            <label>类型 <select name="kind">${options(labels, 'resource')}</select></label>
            <label>要求强度 <select name="strength">${options(strengths, 'required')}</select></label>
            <label>检查时机 <select name="check_at">${options(timings, 'start')}</select></label>
            <label data-field="task" hidden>先完成任务 <select name="task_id"><option value="">请选择</option>${tasks.map(t => `<option value="${t.id}">${esc(t.project_title)} → ${esc(t.title)}</option>`).join('')}</select></label>
            <label data-field="project" hidden>前置项目 <select name="project_id"><option value="">请选择</option>${overview.projects.map(p => `<option value="${p.id}">${esc(p.title)}</option>`).join('')}</select></label>
            <label data-field="project" hidden>所需交付状态 <select name="required_state"><option value="accepted">已验收</option><option value="delivered">已交付</option></select></label>
            <label data-field="time" hidden>允许开始时间（本机时区 ${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}；可留空，改为人工核对连续时段等条件） <input type="datetime-local" name="not_before" data-paper-date></label>
            <label data-field="manual">确认状态 <select name="confirmation">${options(confirmations, 'unknown')}</select></label>
            <label>依据或不适用说明 <textarea name="evidence" maxlength="4000" rows="2"></textarea></label>
            <button type="submit">保存条件</button>
          </form>
        </details>
        <details><summary>变更记录（${history.items.length}条）</summary>${history.items.map(e => `<p>${esc(new Date(e.created_at + (e.created_at.endsWith('Z') ? '' : 'Z')).toLocaleString('zh-CN'))} · ${esc(describeEvent(e))}${e.reason ? ' · ' + esc(e.reason) : ''}</p>`).join('') || '<p>暂无变更记录。</p>'}</details>
        <p role="status" class="condition-message"></p>`;
      const createForm = root.querySelector('[data-create-condition]');
      function updateFields() {
        const type = createForm.elements.kind.value;
        root.querySelectorAll('[data-field]').forEach(field => { field.hidden = field.dataset.field === 'manual'
          ? ['task','project'].includes(type) || (type === 'time' && !!createForm.elements.not_before.value)
          : field.dataset.field !== type; });
      }
      createForm.addEventListener('change', updateFields); updateFields();
      let busy = false;
      async function perform(task) {
        if (busy) return; busy = true;
        try { await task(); if (onChange) await onChange(); await mount(root, kind, id, onChange); }
        catch (error) { root.querySelector('.condition-message').textContent = error.message; }
        finally { busy = false; }
      }
      root.onsubmit = async function submit(event) {
        const form = event.target;
        if (!form.matches('[data-create-condition], [data-update-condition]')) return;
        event.preventDefault(); event.stopPropagation();
        perform(async () => {
          const values = Object.fromEntries(new FormData(form));
          if (form.dataset.updateCondition) {
            const c = own.find(item => item.id === Number(form.dataset.updateCondition));
            const body = {title:c.title, kind:c.kind, target_id:c.target_id, required_state:c.required_state,
              not_before:c.not_before ? c.not_before + 'Z' : null, confirmation:c.confirmation, ...values};
            await request(`/conditions/${c.id}`, 'PUT', body);
          } else {
            const type = values.kind;
            await request(`/conditions/${kind}/${id}`, 'POST', {title:values.title, kind:type,
              strength:values.strength, check_at:values.check_at,
              target_id:['task','project'].includes(type) ? Number(values[type + '_id']) || null : null,
              required_state:type === 'task' ? 'completed' : type === 'project' ? values.required_state : null,
              not_before:type === 'time' && values.not_before ? new Date(values.not_before).toISOString() : null,
              confirmation:['task','project'].includes(type) || (type === 'time' && values.not_before) ? 'unknown' : values.confirmation,
              evidence:values.evidence || null});
          }
        });
      };
      root.onclick = event => {
        const button = event.target.closest('[data-remove-condition]');
        if (!button) return;
        const input = button.closest('.condition-item')?.querySelector('[name=reason]');
        const reason = input?.value.trim();
        if (!reason) {
          root.querySelector('.condition-message').textContent = '移除条件会改变可执行状态。请先填写本次更改原因；历史与投入仍保留。';
          input?.focus(); return;
        }
        perform(() => request(`/conditions/${button.dataset.removeCondition}/remove`, 'POST', {reason}));
      };
    } catch (error) { root.textContent = error.message; }
  }
  function open(kind, id, onChange) {
    let dialog = document.getElementById('startConditionsDialog');
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.id = 'startConditionsDialog'; dialog.className = 'conditions-dialog';
      dialog.innerHTML = '<form method="dialog"><button type="submit" class="secondary">关闭</button></form><div class="conditions-body"></div>';
      document.body.append(dialog);
    }
    dialog.showModal();
    mount(dialog.querySelector('.conditions-body'), kind, id, onChange);
  }
  globalThis.ShuranConditions = {mount, open};
})();
