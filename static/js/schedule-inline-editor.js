// Keep long-form schedule edits beside the task, without leaving or resetting the list.
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const request = (path, options) => apiRequest(path, options || {});
  const fields = form => Object.fromEntries(new FormData(form));
  const draftPath = key => `/api/editor-drafts/${encodeURIComponent(key)}`;
  const option = (name, values, selected) => `<select name="${name}">${Object.entries(values).map(([key,label]) => `<option value="${key}" ${selected === key ? 'selected' : ''}>${label}</option>`).join('')}</select>`;
  let active = null;

  async function persist(entry) {
    if (!entry?.form?.isConnected && !entry?.content) return;
    clearTimeout(entry.timer);
    if (entry.form?.isConnected) entry.content = fields(entry.form);
    if (entry.kind === 'feedback' && entry.form?.isConnected) entry.content.scope_changed = entry.form.elements.scope_changed.checked;
    const content = entry.id ? (entry.content || {}) : {...entry.base,...entry.content};
    entry.writing = entry.writing.catch(() => {}).then(() => request(draftPath(entry.key), {method:'PUT',body:JSON.stringify({content})}));
    return entry.writing;
  }

  async function close() {
    if (!active) return;
    const entry = active;
    try { await persist(entry); }
    catch (error) { entry.status.textContent = `草稿保存失败：${error.message}`; return; }
    if (entry.id == null) entry.newTask(entry.content || {});
    entry.root.innerHTML = '';
    active = null;
  }

  function bind(entry) {
    entry.form = entry.root.querySelector('form');
    entry.status = entry.root.querySelector('[role="status"]');
    entry.form.addEventListener('input', () => {
      entry.content = fields(entry.form);
      if (entry.kind === 'feedback') entry.content.scope_changed = entry.form.elements.scope_changed.checked;
      clearTimeout(entry.timer);
      entry.timer = setTimeout(() => persist(entry).then(() => { if (entry.status.isConnected) entry.status.textContent = '草稿已保存'; }).catch(error => { if (entry.status.isConnected) entry.status.textContent = error.message; }), 350);
    });
    entry.root.querySelector('[data-inline-close]').addEventListener('click', close);
    entry.form.addEventListener('submit', event => save(event, entry));
    entry.form.querySelector('textarea,select')?.focus({preventScroll:true});
  }

  function expectationHTML(value, isNew) {
    return `<form class="schedule-inline-form" data-inline-kind="expectation"><h3>预期结果与完成依据</h3><p>做之前想一想希望得到什么，以及怎样确认已经做到；两项都可留空。</p><div class="schedule-inline-fields"><label>预期结果 <small>选填</small><textarea name="expected_result" maxlength="4000" placeholder="希望做完这件事得到什么？">${esc(value.expected_result)}</textarea></label><label>完成依据 <small>选填</small><textarea name="completion_basis" maxlength="4000" placeholder="怎样确认已经做到？">${esc(value.completion_basis)}</textarea></label></div><div class="schedule-inline-actions"><button type="submit">${isNew?'保留到新任务':'保存任务内容'}</button><button type="button" data-inline-close>收起</button><span role="status"></span></div></form>`;
  }

  function feedbackHTML(data, value, day) {
    const f = data.feedback || {}, progress = data.history?.find(event => event.type === 'progress')?.data || {};
    const v = (name, fallback) => esc(value[name] ?? fallback ?? '');
    const choose = (name, choices, fallback) => option(name, choices, String(value[name] ?? fallback));
    return `<form class="schedule-inline-form" data-inline-kind="feedback"><h3>结果与用时 · ${esc(data.title)}</h3><div class="schedule-inline-comparison"><span>原来预计 ${data.original_estimate ?? '未填'} 分</span><span>区间已记录 ${data.recorded_minutes} 分</span><span>上次确认总量 ${f.actual_minutes ?? '待核对'} 分</span></div><p>自报总用时不会新增工作片；更正每日投入请到“执行 → 投入记录”。</p><div class="schedule-inline-fields"><label>实际结果${choose('result',{completed:'完成',partial:'部分完成',rework:'需要返工'},f.result || (data.completed?'completed':'partial'))}</label><label>反馈依据${choose('basis',{self_report:'自报总用时（不新增区间）',timer_checked:'核对计时区间',manual_checked:'核对补记区间',pending:'稍后核对'},f.basis || 'self_report')}</label><label>本次结果日期 <small>必填</small><input name="feedback_date" type="date" required value="${v('feedback_date',f.feedback_date || f.date || day)}"></label><label>累计实际用时（分钟） <small>选填</small><input name="actual_minutes" type="number" min="0" max="1000000" step="0.01" value="${v('actual_minutes',f.actual_minutes)}"></label><label>实际得到什么结果？ <small>选填</small><textarea name="outcome" maxlength="4000">${v('outcome',f.outcome)}</textarea></label><label>偏差原因 <small>选填</small><textarea name="reason" maxlength="4000">${v('reason',f.reason)}</textarea></label><label>下次类似任务怎样估计？ <small>选填</small><textarea name="next_estimate" maxlength="4000">${v('next_estimate',f.next_estimate)}</textarea></label><label class="schedule-inline-check"><input name="scope_changed" type="checkbox" value="true" ${String(value.scope_changed ?? f.scope_changed) === 'true' ? 'checked' : ''}>本次任务范围发生变化</label><label>完成检查例外说明 <small>选填</small><textarea name="checklist_exception" maxlength="4000">${v('checklist_exception',f.checklist_exception)}</textarea></label></div><h4>当天进展 <small>选填</small></h4><div class="schedule-inline-fields"><label>记录状态${choose('progress_status',{missing:'待核对',recorded:'有投入或进展',no_work:'已核对，今天没有投入'},progress.status || 'missing')}</label><label>推进了什么？ <small>选填</small><textarea name="advanced" maxlength="4000">${v('advanced',progress.advanced)}</textarea></label><label>解决了什么问题？ <small>选填</small><textarea name="solved" maxlength="4000">${v('solved',progress.solved)}</textarea></label><label>卡点或欠缺条件 <small>选填</small><textarea name="blocker" maxlength="4000">${v('blocker',progress.blocker)}</textarea></label><label>下一步 <small>选填</small><textarea name="next_step" maxlength="4000">${v('next_step',progress.next_step)}</textarea></label></div><div class="schedule-inline-actions"><button type="submit">保存结果与用时反馈</button><button type="button" data-inline-close>收起</button><span role="status"></span></div></form>`;
  }

  async function open({kind, id, day, root, task, onSaved, newTask}) {
    const key = kind === 'feedback' ? `feedback:daily:${id}` : id ? `task:${id}` : `task-new:${day}`;
    if (active?.key === key && active.kind === kind) { await close(); return; }
    await close();
    if (active) return;
    const entry = {kind,id,day,root,key,onSaved,newTask,writing:Promise.resolve(),content:null};
    active = entry;
    root.innerHTML = '<p class="schedule-inline-loading">正在读取填写内容…</p>';
    try {
      const draft = (await request(draftPath(key))).content || {};
      if (active !== entry) return;
      entry.base = draft;
      if (kind === 'feedback') {
        entry.data = await request(`/api/projects/practice/tasks/daily/${id}`);
        root.innerHTML = feedbackHTML(entry.data,draft,day);
      } else root.innerHTML = expectationHTML({...task,...draft},!id);
      bind(entry);
    } catch (error) { root.innerHTML = `<p class="schedule-inline-error">${esc(error.message)}</p>`; active = null; }
  }

  async function save(event, entry) {
    event.preventDefault();
    const form = entry.form, button = form.querySelector('[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    try {
      await persist(entry);
      const b = fields(form);
      if (entry.kind === 'feedback') {
        const f = entry.data.feedback || {}, progress = entry.data.history?.find(item => item.type === 'progress')?.data || {};
        await request(`/api/projects/practice/tasks/daily/${entry.id}/feedback`,{method:'POST',body:JSON.stringify({result:b.result,basis:b.basis,feedback_date:b.feedback_date,actual_minutes:b.actual_minutes === '' ? null : Number(b.actual_minutes),outcome:b.outcome,reason:b.reason,next_estimate:b.next_estimate,scope_changed:form.elements.scope_changed.checked,checklist_exception:b.checklist_exception})});
        const changed = b.progress_status !== (progress.status || 'missing') || ['advanced','solved','blocker','next_step'].some(key => b[key] !== String(progress[key] || ''));
        if (changed) await request(`/api/projects/practice/tasks/daily/${entry.id}/progress`,{method:'POST',body:JSON.stringify({date:b.feedback_date,status:b.progress_status,advanced:b.advanced,solved:b.solved,blocker:b.blocker,next_step:b.next_step,help_choice:progress.help_choice || 'none',reduce_prompts:!!progress.reduce_prompts})});
      } else if (entry.id) {
        await request(`/api/schedule/tasks/${entry.id}`,{method:'PATCH',body:JSON.stringify({expected_result:b.expected_result,completion_basis:b.completion_basis})});
      } else {
        entry.newTask(b);
      }
      if (entry.id) await request(draftPath(entry.key),{method:'DELETE'});
      entry.status.textContent = entry.id ? '已保存' : '已保留，添加任务时一起保存';
      if (entry.id) {
        const anchor = document.querySelector(`[data-task-id="${entry.id}"]`);
        const top = anchor?.getBoundingClientRect().top;
        active = null;
        await entry.onSaved();
        const next = document.querySelector(`[data-task-id="${entry.id}"]`);
        if (next && top != null) window.scrollBy(0,next.getBoundingClientRect().top-top);
        next?.querySelector(`[data-act="${entry.kind === 'feedback' ? 'feedback' : 'expectation'}"]`)?.focus({preventScroll:true});
      }
    } catch (error) { entry.status.textContent = `保存未全部完成，草稿仍在服务器：${error.message}`; }
    finally { button.disabled = false; }
  }

  function restore(rootFor) {
    if (!active || active.id == null || !active.form || !active.root) return;
    const next = rootFor(active.id);
    if (!next || next === active.root) return;
    clearTimeout(active.timer);
    active.content = fields(active.form);
    if (active.kind === 'feedback') active.content.scope_changed = active.form.elements.scope_changed.checked;
    next.appendChild(active.form);
    active.root = next;
    active.status = active.form.querySelector('[role="status"]');
  }
  function completeNew() {
    if (active?.id != null) return;
    clearTimeout(active.timer);
    active.root.innerHTML = '';
    active = null;
  }
  function readNew(day) {
    if (!active || active.id != null || active.day !== day || !active.form?.isConnected) return null;
    return fields(active.form);
  }
  globalThis.ShuranScheduleInline = {open,restore,close,completeNew,readNew};
})();
