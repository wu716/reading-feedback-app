(() => {
  'use strict';
  const params = new URLSearchParams(location.search), type = params.get('type');
  const kind = params.get('kind') || 'daily', id = Number(params.get('id'));
  const day = params.get('day') || new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const root = document.getElementById('editorContent'), status = document.getElementById('editorStatus');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const back = (() => { try { const url = new URL(params.get('return') || '/', location.origin); return url.origin === location.origin ? url.href : location.origin + '/'; } catch { return location.origin + '/'; } })();
  document.getElementById('editorBack').href = back;
  const setHead = (name, title, intro) => { document.getElementById('editorKind').textContent=name;document.getElementById('editorTitle').textContent=title;document.getElementById('editorIntro').textContent=intro;document.title=title+' · 书然'; };
  const message = (text, error=false) => {status.textContent=text;status.classList.toggle('editor-error',error);};
  const request = async (path, method='GET', body) => {
    const response=await fetch(path,{method,headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
    const value=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'保存失败，请重试');
    return value;
  };
  const draftKey = type==='expectation' ? (id ? `task:${id}` : `task-new:${day}`) : ['feedback','rehearsal'].includes(type) ? `${type}:${kind}:${id}` : type==='condition' ? `condition:${kind}:${id}` : null;
  const draftPath = draftKey ? '/api/editor-drafts/'+encodeURIComponent(draftKey) : null;
  let timer, writing=Promise.resolve();
  const fields = form => Object.fromEntries(new FormData(form));
  const queueDraft = content => {if(!draftPath)return Promise.resolve();writing=writing.catch(()=>{}).then(()=>request(draftPath,'PUT',{content}));return writing;};
  const clearDraft = async () => {if(draftPath)await request(draftPath,'DELETE');};
  const attachDraft = (form, extra=()=>({})) => {
    form.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>queueDraft({...extra(),...fields(form)}).then(()=>message('草稿已保存在服务器')).catch(e=>message(e.message,true)),300);});
    return async () => {clearTimeout(timer);await queueDraft({...extra(),...fields(form)});};
  };
  async function restore() {return draftPath ? (await request(draftPath)).content || {} : {};}
  async function expectation() {
    if(id && !Number.isInteger(id))throw new Error('任务编号无效');
    setHead('日程任务','预期结果与完成依据','做之前想一想希望得到什么，以及怎样确认已经做到。两项都可稍后填写。');
    const task=id ? await request(`/api/schedule?task_date=${encodeURIComponent(day)}`).then(r=>{const walk=rows=>rows.flatMap(t=>[t,...walk(t.children||[])]);return walk(r.tasks).find(t=>t.id===id);}) : null;
    if(id&&!task)throw new Error('这项任务不存在或不属于所选日期');
    const draft=await restore(),expected=draft.expected_result??task?.expected_result??'',basis=draft.completion_basis??task?.completion_basis??'';
    root.innerHTML=`${task?`<p class="editor-summary">${esc(task.text)}</p>`:''}<form id="contentForm"><label>预期结果 <small>选填</small><textarea name="expected_result" maxlength="4000" placeholder="希望做完这件事得到什么？">${esc(expected)}</textarea></label><label>完成依据 <small>选填</small><textarea name="completion_basis" maxlength="4000" placeholder="怎样确认已经做到？">${esc(basis)}</textarea></label><div class="editor-actions"><button type="submit">${task?'保存任务内容':'保存并返回写任务'}</button></div></form><p class="editor-hint">返回时未提交的输入会保存在服务器草稿；正式任务记录仅在点击保存或添加任务后更新。</p>`;
    const form=document.getElementById('contentForm'),flush=attachDraft(form,()=>draft);
    document.getElementById('editorBack').onclick=async e=>{e.preventDefault();try{await flush();location.href=back;}catch(err){message(err.message,true);}};
    form.onsubmit=async e=>{e.preventDefault();try{await flush();if(task){await request(`/api/schedule/tasks/${id}`,'PATCH',fields(form));await clearDraft();}message('已保存');location.href=back;}catch(err){message(err.message,true);}};
  }
  async function feedback() {
    if(!Number.isInteger(id)||id<1||!['daily','task'].includes(kind))throw new Error('任务编号无效');
    setHead('任务反馈','记录实际结果、进展与原因','原有用时、结果日期和反馈依据继续分别记录。没有填写的文字说明可以留空。');
    const data=await request(`/api/projects/practice/tasks/${kind}/${id}`),f=data.feedback||{},progress=data.history?.find(event=>event.type==='progress')?.data||{},draft=await restore();
    const value=(name,fallback)=>esc(draft[name]??fallback??'');
    const option=(name,items,selected)=>`<select name="${name}">${Object.entries(items).map(([key,label])=>`<option value="${key}" ${String(draft[name]??selected)===key?'selected':''}>${label}</option>`).join('')}</select>`;
    root.innerHTML=`<p class="editor-summary">${esc(data.title)}</p><div class="editor-comparison"><span>原来预计<strong>${data.original_estimate??'未填'} 分</strong></span><span>区间已记录<strong>${data.recorded_minutes} 分</strong></span><span>上次确认总量<strong>${f.actual_minutes??'待核对'} 分</strong></span></div><p class="editor-hint">自报用时不会新增工作片；更正每日投入请到“执行 → 投入记录”。</p><form id="contentForm"><label>实际结果${option('result',{completed:'完成',partial:'部分完成',rework:'需要返工'},f.result||(data.completed?'completed':'partial'))}</label><label>反馈依据${option('basis',{self_report:'自报总用时（不新增区间）',timer_checked:'核对计时区间',manual_checked:'核对补记区间',pending:'稍后核对'},f.basis||'self_report')}</label><label>本次结果日期 <small>必填</small><input name="feedback_date" type="date" required value="${value('feedback_date',f.feedback_date||f.date||day)}"></label><label>累计实际用时（分钟） <small>选填</small><input name="actual_minutes" type="number" min="0" max="1000000" step="0.01" value="${value('actual_minutes',f.actual_minutes??'')}"></label><label>实际得到什么结果？ <small>选填</small><textarea name="outcome" maxlength="4000">${value('outcome',f.outcome)}</textarea></label><label>偏差原因 <small>选填</small><textarea name="reason" maxlength="4000">${value('reason',f.reason)}</textarea></label><label>下次类似任务怎样估计？ <small>选填</small><textarea name="next_estimate" maxlength="4000">${value('next_estimate',f.next_estimate)}</textarea></label><label><input name="scope_changed" type="checkbox" value="true" ${String(draft.scope_changed??f.scope_changed)==='true'?'checked':''}>本次任务范围发生变化</label><label>完成检查例外说明 <small>选填</small><textarea name="checklist_exception" maxlength="4000">${value('checklist_exception',f.checklist_exception)}</textarea></label><div class="editor-actions"><button type="submit">保存结果与用时反馈</button></div></form>`;
    const form=document.getElementById('contentForm');
    form.querySelector('.editor-actions').insertAdjacentHTML('beforebegin',`<h2>当天进展 <small>选填</small></h2><label>记录状态${option('progress_status',{missing:'待核对',recorded:'有投入或进展',no_work:'已核对，今天没有投入'},progress.status||'missing')}</label><label>推进了什么？ <small>选填</small><textarea name="advanced" maxlength="4000">${value('advanced',progress.advanced)}</textarea></label><label>解决了什么问题？ <small>选填</small><textarea name="solved" maxlength="4000">${value('solved',progress.solved)}</textarea></label><label>卡点或欠缺条件 <small>选填</small><textarea name="blocker" maxlength="4000">${value('blocker',progress.blocker)}</textarea></label><label>下一步 <small>选填</small><textarea name="next_step" maxlength="4000">${value('next_step',progress.next_step)}</textarea></label>`);
    const flush=attachDraft(form,()=>({scope_changed:form.elements.scope_changed.checked}));
    document.getElementById('editorBack').onclick=async e=>{e.preventDefault();try{await flush();location.href=back;}catch(err){message(err.message,true);}};
    form.onsubmit=async e=>{e.preventDefault();try{await flush();const b=fields(form);await request(`/api/projects/practice/tasks/${kind}/${id}/feedback`,'POST',{result:b.result,basis:b.basis,feedback_date:b.feedback_date,actual_minutes:b.actual_minutes===''?null:Number(b.actual_minutes),outcome:b.outcome,reason:b.reason,next_estimate:b.next_estimate,scope_changed:form.elements.scope_changed.checked,checklist_exception:b.checklist_exception});const changedProgress=b.progress_status!==(progress.status||'missing')||['advanced','solved','blocker','next_step'].some(key=>b[key]!==String(progress[key]||''));if(changedProgress)await request(`/api/projects/practice/tasks/${kind}/${id}/progress`,'POST',{date:b.feedback_date,status:b.progress_status,advanced:b.advanced,solved:b.solved,blocker:b.blocker,next_step:b.next_step,help_choice:progress.help_choice||'none',reduce_prompts:!!progress.reduce_prompts});await clearDraft();message('已保存');location.href=back;}catch(err){message('保存未全部完成；草稿仍在服务器。'+err.message,true);}};
  }
  async function rehearsal() {
    if(!Number.isInteger(id)||id<1||!['daily','task'].includes(kind))throw new Error('任务编号无效');
    setHead('任务准备','开始前预演','只填写需要的内容，也可以直接行动。预演不会替代必要的开始条件。');
    const data=await request(`/api/projects/practice/tasks/${kind}/${id}`),draft=await restore(),old=data.rehearsal||{};
    const rows=[['first_step','第一步：现在能做的小行动'],['sequence','接下来按什么顺序做？'],['preparation','需要哪些材料、工具或条件？'],['difficulty','最可能卡在哪里？'],['response','如果卡住，怎样应对？'],['comparison','事后对照：哪里与预想不同？']];
    root.innerHTML=`<p class="editor-summary">${esc(data.title)}</p>${data.legacy_rehearsal?`<details><summary>原来的预演笔记</summary><p>${esc(data.legacy_rehearsal)}</p></details>`:''}<form id="contentForm">${rows.map(([name,label])=>`<label>${label} <small>选填</small><textarea name="${name}" maxlength="${name==='first_step'?2000:4000}">${esc(draft[name]??old[name]??'')}</textarea></label>`).join('')}<label>把准备内容明确转换为<select name="preparation_action"><option value="none">只保留预演</option><option value="checklist">独立准备检查项</option><option value="task">独立筹备任务</option></select></label><div class="editor-actions"><button type="submit">保存预演</button></div></form>`;
    const form=document.getElementById('contentForm');form.elements.preparation_action.value=draft.preparation_action||'none';const flush=attachDraft(form);
    document.getElementById('editorBack').onclick=async e=>{e.preventDefault();try{await flush();location.href=back;}catch(err){message(err.message,true);}};
    form.onsubmit=async e=>{e.preventDefault();try{await flush();await request(`/api/projects/practice/tasks/${kind}/${id}/rehearsal`,'PUT',fields(form));await clearDraft();location.href=back;}catch(err){message(err.message,true);}};
  }
  async function condition() {
    if(!Number.isInteger(id)||id<1||!['daily','task','project'].includes(kind))throw new Error('条件对象无效');
    setHead('项目与日程','开始条件与执行约束','条件内容、类型、要求强度、检查时机和依据保留；变更仍记录原因与历史。');
    await globalThis.ShuranConditions.mount(root,kind,id,async()=>{clearTimeout(timer);await writing.catch(()=>{});await clearDraft();});
    const draft=await restore();
    const restoreFields=()=>{for(const form of root.querySelectorAll('[data-create-condition],[data-update-condition]')){const key=form.dataset.updateCondition||'create',values=draft[key]||{};for(const [name,value] of Object.entries(values)){const input=form.elements[name];if(input&&typeof value==='string')input.value=value;}form.elements.kind?.dispatchEvent(new Event('change',{bubbles:true}));}};
    restoreFields();
    root.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{const content={};for(const form of root.querySelectorAll('[data-create-condition],[data-update-condition]'))content[form.dataset.updateCondition||'create']=fields(form);queueDraft(content).then(()=>message('草稿已保存在服务器')).catch(e=>message(e.message,true));},300);});
    document.getElementById('editorBack').onclick=async e=>{e.preventDefault();clearTimeout(timer);const content={};for(const form of root.querySelectorAll('[data-create-condition],[data-update-condition]'))content[form.dataset.updateCondition||'create']=fields(form);try{await queueDraft(content);location.href=back;}catch(err){message(err.message,true);}};
  }
  async function commitment() {
    if(!Number.isInteger(id)||id<1)throw new Error('项目编号无效');
    setHead('当前阶段','本轮承诺','承诺文字与任务范围分别保存；草稿保存在服务器，确认后保留版本历史。');
    await globalThis.ShuranCommitments.mount(root,id,{page:true});
    if(params.get('adjust')==='1')await globalThis.ShuranPractice?.openProject(id,'commitment');
  }
  if(!localStorage.getItem('authToken')){location.href='/';return;}
  ({expectation,feedback,rehearsal,condition,commitment}[type]||(()=>{throw new Error('填写页类型无效');}))().catch(e=>{root.innerHTML='<p role="alert"></p>';root.firstChild.textContent=e.message;message(e.message,true);});
})();
