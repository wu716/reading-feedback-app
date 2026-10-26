/* Three explicit deletion entries share one server-reviewed recovery flow. */
(() => {
  'use strict';
  const labels={project:'项目',stage:'阶段',task:'任务'};
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let dialog,options={},current=null,items=[],tab='project',timer=null,busy=false,beating=false,reason='',waiting=false,restoreItem=null,generation=0;
  const token=globalThis.crypto?.randomUUID?.()||`delete-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const find=s=>dialog.querySelector(s);
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  async function api(path,body,base='/deletions',keepalive=false) {
    const response=await fetch('/api/projects'+base+path,{method:body===undefined?'GET':'POST',keepalive,
      headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),'Content-Type':'application/json'},
      body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:data.detail?.message||'操作失败，请稍后重试');
    return data;
  }
  async function refreshCount() {
    const entry=document.querySelector('[data-project-trash]');
    if(!entry)return;
    try {items=(await api('')).items;entry.textContent=`已删除（${items.length}）`;}catch(_){entry.textContent='已删除';}
  }
  function stopWait() {
    generation+=1;
    clearInterval(timer);timer=null;
    if(waiting&&current&&!current.confirmed_at)api(`/${current.id}/visible`,{token,visible:false},'/deletions',true).catch(()=>{});
    waiting=false;
  }
  function shell(title,description,body) {
    if(!dialog){dialog=document.createElement('dialog');dialog.className='project-delete-dialog';dialog.setAttribute('aria-labelledby','projectDeleteHeading');document.body.append(dialog);dialog.addEventListener('close',stopWait);dialog.addEventListener('cancel',stopWait);dialog.addEventListener('click',handle);dialog.addEventListener('input',onInput);}
    dialog.innerHTML=`<div class="delete-heading"><h2 id="projectDeleteHeading">${esc(title)}</h2><button type="button" class="delete-close" data-close aria-label="关闭删除与恢复窗口">×</button></div><p class="delete-note">${esc(description)}</p>${body}<p class="delete-message" role="alert" data-error></p>`;
    if(!dialog.open)dialog.showModal();
    find('[data-close]').focus();
  }
  function error(message){find('[data-error]').textContent=message;}
  function blocked(){return current.impact.running.length||current.impact.affected.length;}
  function drawDelete() {
    const row=current,impact=row.impact;
    const keepStageTasks=row.kind==='stage'&&impact.stage_tasks==='keep';
    const stageChoice=row.kind==='stage'?`<fieldset class="delete-stage-choice"><legend>${impact.stage_has_execution?'已有执行记录，任务与投入必须保留':'这个阶段的任务尚未执行，选择任务去向'}</legend>${impact.task_titles.map(t=>`<div>· ${esc(t.title)}</div>`).join('')||'<div>这个阶段没有任务。</div>'}${impact.stage_has_execution?'<p>删除阶段后，任务放到本项目“未分阶段”。</p>':`<label><input type="radio" name="stage-tasks" value="delete" ${keepStageTasks?'':'checked'}> 连同尚未执行的计划任务一起删除</label><label><input type="radio" name="stage-tasks" value="keep" ${keepStageTasks?'checked':''}> 保留任务，放到本项目“未分阶段”</label>`}</fieldset>`:'';
    const confirmLabel=row.kind==='stage'?(keepStageTasks?'只删除阶段，保留任务':impact.tasks?`删除阶段和 ${impact.tasks} 项计划任务`:'删除阶段'):'确认删除';
    shell(`删除${labels[row.kind]}“${row.title}”？`,'从工作区删除；现有删除记录可用于恢复。',
      stageChoice+`<dl class="delete-impact"><dt>移出工作区</dt><dd>${row.kind==='project'?'整个项目、':''}${impact.stages?impact.stages+' 个阶段、':''}${keepStageTasks?0:impact.tasks} 项任务</dd><dt>移出待办</dt><dd>${keepStageTasks?0:impact.daily} 条关联未完成日程，相关轮转项一并移出</dd><dt>继续保留</dt><dd>${impact.sessions} 条历史投入（已结束 ${impact.minutes} 分钟）、已完成日程、反馈历史，以及独立目标和流程模板</dd></dl>`+
      (impact.running.length?`<div class="delete-warning"><h3>先结束正在进行的工作计时</h3><p>已发生的投入会保留；暂停等待不计入工作。</p>${impact.running.map(s=>`<p>${esc(s.title)} <button type="button" data-stop="${s.id}">结束计时并保留投入</button></p>`).join('')}</div>`:'')+
      (impact.affected.length?`<div class="delete-warning"><h3>还有其他内容依赖这里</h3><p>先在对应项目或日程中明确调整前置条件，然后回来重新预览。删除不会自动满足依赖。</p>${impact.affected.map(a=>`<p>${esc(a.title)} · ${esc(a.condition)}<br><a href="${a.kind==='daily'?'/static/index.html#schedule':`/static/projects.html?project=${a.project_id}${a.kind==='task'?'&task='+a.id:''}`}">查看${a.kind==='daily'?'日程':'所属项目与任务'}</a></p>`).join('')}</div>`:'')+
      (impact.requires_wait?`<div class="delete-warning"><h3>这会改变已确认的当前承诺</h3><p>${esc(impact.notice)}</p><p>本次删除会缩减当前范围，且不会将未完成内容算作完成。请核对交付与验收是否仍然可达。</p></div>`:'')+
      `<label class="delete-reason">${impact.requires_wait?'调整原因（必填）':'删除原因（选填）'}<input type="text" data-reason maxlength="4000" value="${esc(reason)}" placeholder="说明为什么需要删除"></label>`+
      (impact.requires_wait?`<p class="delete-wait" data-wait aria-live="polite">尚未开始30秒暂停</p><button type="button" data-wait-start ${blocked()||!reason.trim()?'disabled':''}>开始30秒暂停</button>`:'')+
      `<p class="delete-note">恢复不会自动开始计时、加入轮转或重新启用提醒。此前单独删除的内容不会随上级恢复。</p><div class="delete-actions"><button type="button" data-close>保留${labels[row.kind]}</button><button type="button" data-repreview>重新预览</button><button type="button" class="delete-confirm" data-confirm ${blocked()||impact.requires_wait?'disabled':''}>${confirmLabel}</button></div>`);
  }
  async function preview(kind,id,keepReason=false,stageTasks='delete') {
    stopWait();if(!keepReason)reason='';restoreItem=null;
    const version=generation,result=await api('/preview',{kind,target_id:Number(id),stage_tasks:stageTasks});
    if(version===generation){current=result;drawDelete();}
  }
  async function beat() {
    if(beating||!waiting||!dialog.open)return;
    beating=true;
    const version=generation,id=current.id;
    try {
      const result=await api(`/${id}/visible`,{token,visible:!document.hidden});
      if(version!==generation||!waiting||!dialog.open||current?.id!==id)return;
      current=result;
      find('[data-wait]').textContent=document.hidden?'离开页面，暂停累计':current.remaining_seconds?`请再考虑 ${current.remaining_seconds} 秒`:'30秒暂停已完成，仍可选择保留原计划。';
      find('[data-confirm]').disabled=blocked()||current.remaining_seconds>0||!reason.trim();
      if(current.remaining_seconds===0){clearInterval(timer);timer=null;}
    }catch(e){if(version===generation){stopWait();if(dialog.open){error(e.message+'。请重新预览。');find('[data-confirm]').disabled=true;}}}
    finally{beating=false;}
  }
  function drawTrash() {
    const rows=items.filter(r=>r.kind===tab);
    shell('已删除','恢复本次删除涉及的内容，保留历史记录。',
      `<nav class="delete-tabs" aria-label="已删除内容类型">${Object.entries(labels).map(([k,v])=>`<button type="button" data-trash-tab="${k}" aria-pressed="${k===tab}">${v}（${items.filter(r=>r.kind===k).length}）</button>`).join('')}</nav>`+
      (rows.map(r=>`<article class="delete-item"><div class="delete-item-head"><h3>${esc(r.title)}${r.restored_at?' · 内容已恢复':''}</h3><button type="button" data-restore="${r.id}">${r.restored_at?'恢复日程':'恢复'}</button></div><p class="delete-note">${r.restored_at?'还有 '+r.pending_daily.length+' 条关联日程尚未恢复':r.impact.tasks+' 项任务 · '+r.impact.stages+' 个阶段 · '+new Date(r.confirmed_at+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 删除'}</p>${r.reason?`<p class="delete-note">删除原因：${esc(r.reason)}</p>`:''}</article>`).join('')||'<p>暂无已删除的'+labels[tab]+'。</p>'));
  }
  function drawRestore(row) {
    stopWait();current=null;restoreItem=row;
    shell(`恢复“${row.title}”${row.restored_at?'的关联日程':''}？`,'此前单独删除的内容保持原样。上级仍被删除时，请先恢复上级。',
      `<p>${row.restored_at?'内容已经恢复。':`恢复 ${row.impact.tasks} 项任务${row.impact.stages?'和 '+row.impact.stages+' 个阶段':''}。`}</p>`+
      (row.pending_daily.length?`<label class="delete-check"><input type="checkbox" data-daily ${row.restored_at?'checked disabled':''}>${row.restored_at?'恢复':'同时恢复'}关联未完成日程</label><details open><summary>选择要恢复的日程（${row.pending_daily.length} 条）</summary>${row.pending_daily.map(d=>`<div class="delete-item"><label class="delete-check"><input type="checkbox" data-daily-id="${d.id}" checked>${esc(d.date)} · ${esc(d.title)}</label>${d.date<today()?`<label>这条过去的日程重新安排到<input type="date" data-daily-date="${d.id}" min="${today()}"></label>`:''}</div>`).join('')}</details>`:'')+
      (row.kind==='stage'?'<label class="delete-check"><input type="checkbox" data-stage-next>若已有其他当前阶段，将原阶段恢复为下一阶段，不自动开始</label>':'')+
      `<p class="delete-note">未恢复的日程仍留在“已删除”，可稍后处理。计时、轮转和提醒需要重新安排；已解除的外部依赖不会自动接回。</p><div class="delete-actions"><button type="button" data-back-trash>返回已删除列表</button><button type="button" data-do-restore>确认恢复</button></div>`);
  }
  function onInput(e) {
    if(e.target.matches('[name="stage-tasks"]')){preview(current.kind,current.target_id,true,e.target.value).catch(error=>{if(dialog.open)find('[data-error]').textContent=error.message;});return;}
    if(!e.target.matches('[data-reason]'))return;
    reason=e.target.value;
    const start=find('[data-wait-start]');if(start)start.disabled=!!(blocked()||!reason.trim()||waiting);
    if(current.impact.requires_wait)find('[data-confirm]').disabled=!!(blocked()||!waiting||current.remaining_seconds>0||!reason.trim());
  }
  async function handle(e) {
    const b=e.target.closest('button');if(!b||b.disabled||busy)return;
    if(b.hasAttribute('data-close')){dialog.close();return;}
    if(b.dataset.trashTab){tab=b.dataset.trashTab;drawTrash();return;}
    if(b.dataset.restore){drawRestore(items.find(r=>r.id===Number(b.dataset.restore)));return;}
    if(b.hasAttribute('data-wait-start')){waiting=true;b.disabled=true;await beat();if(waiting&&current.remaining_seconds>0)timer=setInterval(beat,1000);return;}
    busy=true;b.disabled=true;
    try {
      if(b.dataset.stop){await api(`/sessions/${b.dataset.stop}/stop`,{},'');await options.onChanged?.('计时已结束，投入已保留');await preview(current.kind,current.target_id,true);}
      else if(b.hasAttribute('data-repreview'))await preview(current.kind,current.target_id,true,current.impact.stage_tasks||'delete');
      else if(b.hasAttribute('data-confirm')){await api(`/${current.id}/confirm`,{reason});dialog.close();await options.onChanged?.('已移入“已删除”，历史投入已保留');await refreshCount();}
      else if(b.hasAttribute('data-do-restore')){
        const dates=Object.fromEntries([...dialog.querySelectorAll('[data-daily-date]')].filter(n=>n.value).map(n=>[n.dataset.dailyDate,n.value]));
        const result=await api(`/${restoreItem.id}/restore`,{with_daily:!!find('[data-daily]')?.checked,daily_ids:[...dialog.querySelectorAll('[data-daily-id]:checked')].map(n=>Number(n.dataset.dailyId)),daily_dates:dates,stage_as_next:!!find('[data-stage-next]')?.checked});
        dialog.close();await options.onChanged?.(result.warnings?.join('；')||'内容已恢复；计时、轮转和提醒需要重新安排');await refreshCount();
      }else if(b.dataset.activateStage){
        const explanation=find('[data-stage-reason]').value.trim();
        if(!explanation)throw new Error('请说明本次阶段交接的原因');
        await api(`/stages/${b.dataset.activateStage}/activate`,{decision:'close',reason:explanation},'');
        dialog.close();await options.onChanged?.('已主动交接到所选阶段');
      }else if(b.hasAttribute('data-back-trash')){items=(await api('')).items;drawTrash();}
    }catch(e){error(e.message);}finally{busy=false;if(b.isConnected)b.disabled=false;}
  }
  document.addEventListener('click',async e=>{
    const trigger=e.target.closest('[data-project-delete],[data-project-trash]');if(!trigger||trigger.disabled||busy)return;
    busy=true;trigger.disabled=true;
    try{
      if(trigger.hasAttribute('data-project-trash')){stopWait();current=null;items=(await api('')).items;drawTrash();}
      else {const [kind,id]=trigger.dataset.projectDelete.split(':');await preview(kind,id);}
    }catch(e){if(dialog?.open)error(e.message);else alert(e.message);}finally{busy=false;if(trigger.isConnected)trigger.disabled=false;}
  });
  document.addEventListener('visibilitychange',()=>{if(waiting)beat();});
  globalThis.addEventListener('pagehide',stopWait);
  function activateStage(id,title){
    stopWait();current=null;
    shell(`将“${title}”设为当前阶段？`,'当前没有正在推进的阶段。确认后才会开始所选阶段，历史阶段和投入继续保留。',
      `<label class="delete-reason">交接原因<input type="text" data-stage-reason maxlength="2000" placeholder="说明为什么开始这个阶段"></label><div class="delete-actions"><button type="button" data-close>暂不开始</button><button type="button" data-activate-stage="${Number(id)}">确认交接</button></div>`);
  }
  globalThis.ShuranDeletion={configure(value){options=value;},refreshCount,activateStage};
})();
