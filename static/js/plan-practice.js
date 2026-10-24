/* A single focused editor, shared by schedule and project task identities. */
(() => {
  'use strict';
  const labels = {unimportant:'不重要',ordinary:'一般',important:'重要',simple:'简单',difficult:'困难'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const localStamp = value => value ? new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value)?value:value+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '未记录';
  const dayISO = () => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  let dialog, context, tab, data, projectData, commitmentData, cycles, timer, beating = false, adjustment, dirty = false, loadEpoch = 0, saving = false;
  const lease = globalThis.crypto?.randomUUID?.() || String(Date.now()) + Math.random().toString(36);
  const $ = selector => dialog.querySelector(selector);
  const select = (name, values, value, empty = '未标记') => `<select name="${name}">${empty === null ? '' : `<option value="">${empty}</option>`}${Object.entries(values).map(([k,v])=>`<option value="${k}" ${String(value)===k?'selected':''}>${esc(v)}</option>`).join('')}</select>`;
  const input = (name, label, value='', type='text', attrs='') => `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${attrs}></label>`;
  const area = (name,label,value='', attrs='') => `<label>${label}<textarea name="${name}" rows="2" maxlength="4000" ${attrs}>${esc(value)}</textarea></label>`;
  const note = text => `<p class="practice-note">${esc(text)}</p>`;
  const decisionLabel = value => ({keep:'维持跨度',shorten:'缩短跨度',extend:'延长跨度',stop:'停止此目标'})[value]||value;
  const button = (action,text,attrs='') => `<button type="button" data-practice="${action}" ${attrs}>${text}</button>`;
  const form = (name, content, submit='保存') => `<form data-practice-form="${name}" class="practice-form">${content}<div class="practice-form-actions"><button type="submit">${submit}</button><span class="practice-status" role="status"></span></div></form>`;
  async function api(path, body, method=body===undefined?'GET':'POST') {
    const response = await fetch('/api/projects' + path, {method, headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),'Content-Type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body)});
    const result = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : result.detail?.message || '保存失败，请核对输入或重新打开页面');
    return result;
  }
  const taskPath = () => `/practice/tasks/${data.kind}/${data.id}`;
  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement('dialog'); dialog.className = 'practice-dialog'; dialog.setAttribute('aria-labelledby','practiceTitle');
    document.body.append(dialog);
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    dialog.addEventListener('input', () => {dirty=true; updateWait();});
    dialog.addEventListener('click', event => {
      const el=event.target.closest('[data-practice]'); if (!el) return;
      const action=el.dataset.practice;
      run(async()=>{
        if (action==='close') close();
        else if (action==='tab') { if (dirty && !confirm('本页有未保存内容，仍要切换？')) return; tab=el.dataset.tab; dirty=false; await load(); }
        else if (action==='task') await openTask(el.dataset.kind,Number(el.dataset.id),el.dataset.tab||'attributes');
        else if (action==='start-small') {
          const rehearsalForm=$('[data-practice-form=rehearsal]');
          if (rehearsalForm) await saveRehearsal(rehearsalForm);
          const ready=await api(`/readiness/${data.kind}/${data.id}`);
          if (!ready.can_start) throw new Error(ready.summary);
          const acknowledge = !ready.reminders.length || confirm(ready.reminders.join('\n')+'\n\n已了解提醒，继续开始短工作片？');
          if (!acknowledge) return;
          await api('/sessions/start',{[data.kind==='task'?'project_task_id':'daily_task_id']:data.id,planned_minutes:5,kind:'work',label:data.title,acknowledge_reminders:true});
          close(); location.href='/static/projects.html?view=execution';
        } else if (action==='add-check') {
          const root=$('[data-checks]'); root.insertAdjacentHTML('beforeend', checkRow({text:'',done:false,group:'delivery'},root.children.length)); dirty=true;
        } else if (action==='check-up'||action==='check-down'||action==='check-remove') {
          const row=el.closest('.practice-check-row');
          if(action==='check-remove') row.remove();
          else if(action==='check-up'&&row.previousElementSibling) row.previousElementSibling.before(row);
          else if(action==='check-down'&&row.nextElementSibling) row.nextElementSibling.after(row);
          dirty=true;
        } else if(action==='save-initial') {
          for(const row of dialog.querySelectorAll('[data-review-row]')) {
            const t=data.tasks[Number(row.dataset.reviewRow)];
            await api(`/practice/tasks/${t.kind}/${t.id}/attributes`,{difficulty:t.difficulty,importance:row.querySelector('select').value||null,goal:$('[name=goal]').value},'PATCH');
          }
          dirty=false; await load(); message('首次标记已保存。现在请根据目标再看一遍全部任务，再次确认。');
        } else if(action==='commit') {
          await api(`/commitments/stages/${commitmentData.current_stage_id}/start`,{}); await load(); changed();
        } else if(action==='resume-adjustment') {
          adjustment=await api(`/commitments/adjustments/${el.dataset.id}`); showImpact();
        } else if(action==='repreview') {
          adjustment=await api(`/commitments/projects/${context.id}/preview`,adjustment.plan); showImpact();
        } else if(action==='new-cycle') { tab='new-cycle'; render(); }
        else if(action==='next-cycle') { context.previousCycleId=Number(el.dataset.id); tab='new-cycle'; render(); }
        else if(action==='review-cycle') {context.cycleId=Number(el.dataset.id);tab='review-cycle';render();}
      });
    });
    dialog.addEventListener('change', event=>{
      if(event.target.name==='support') updateSupport();
      if(event.target.name==='horizon'&&!event.target.form?.querySelector('.fb-plan')) {
        const f=event.target.form, days={week:7,fortnight:14,month:30,quarter:90,year:365}[event.target.value];
        if(f?.elements.start_date?.value&&days){ const d=new Date(f.elements.start_date.value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days-1);f.elements.end_date.value=d.toISOString().slice(0,10);}
      }
    });
    dialog.addEventListener('submit', event=>{
      const f=event.target; if(!f.dataset.practiceForm)return;event.preventDefault();event.stopPropagation();
      if(saving)return;saving=true;
      const submitButton=f.querySelector('button[type=submit]');if(submitButton)submitButton.disabled=true;
      run(async()=>{await submit(f);dirty=false;}).finally(()=>{saving=false;if(submitButton?.isConnected)submitButton.disabled=false;updateWait();});
    });
    document.addEventListener('visibilitychange',()=>{if(adjustment&&dialog.open) beat();});
    window.addEventListener('blur',()=>{if(adjustment&&dialog.open) beat(false);});
    window.addEventListener('focus',()=>{if(adjustment&&dialog.open) beat();});
    window.addEventListener('pagehide',()=>signalHidden());
  }
  function message(text, error=false) {const el=$('[data-message]'); if(el){el.textContent=text;el.classList.toggle('is-error',error);}}
  async function run(fn) {try {await fn();}catch(e){message(e.message,true);}}
  function changed(){window.dispatchEvent(new CustomEvent('shuran-practice-change'));}
  function header(title,tabs) {
    dialog.innerHTML=`<header class="practice-header"><div><p>计划 · 行动 · 反馈</p><h2 id="practiceTitle">${esc(title)}</h2></div>${button('close','关闭','class="practice-close" aria-label="关闭编辑"')}</header><nav class="practice-tabs" aria-label="编辑分区">${tabs.map(([id,name])=>button('tab',name,`data-tab="${id}" aria-current="${tab===id?'page':'false'}"`)).join('')}</nav><p data-message role="status" class="practice-message"></p><div class="practice-content"></div>`;
  }
  function show(){ensureDialog();header('正在读取…',[]);if(!dialog.open)dialog.showModal();dirty=false;}
  function signalHidden(){if(!adjustment)return;fetch(`/api/projects/commitments/adjustments/${adjustment.id}/visible`,{method:'POST',keepalive:true,headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),'Content-Type':'application/json'},body:JSON.stringify({token:lease,visible:false})}).catch(()=>{});}
  function close(){signalHidden();clearInterval(timer);timer=null;adjustment=null;dirty=false;dialog.close();const u=new URL(location.href);if(u.searchParams.has('adjustment')){u.searchParams.delete('adjustment');history.replaceState(null,'',u);}}
  async function openTask(kind,id,section='attributes'){ensureDialog();clearInterval(timer);signalHidden();adjustment=null;context={type:'task',kind,id};tab=section;show();await run(load);}
  async function openDay(day=dayISO(),section='review'){ensureDialog();clearInterval(timer);signalHidden();adjustment=null;context={type:'day',day};tab=section;show();await run(load);}
  async function openProject(id,section='feasibility',targetStageId=null){ensureDialog();clearInterval(timer);signalHidden();adjustment=null;context={type:'project',id,targetStageId};tab=section;show();await run(load);}
  async function openGoal(id,section='feasibility'){ensureDialog();clearInterval(timer);signalHidden();adjustment=null;context={type:'goal',id};tab=section;show();await run(load);}
  async function load(){
    const epoch=++loadEpoch,ctx=context;let fresh,overview,commitment,cycleList;
    if(ctx.type==='task')fresh=await api(`/practice/tasks/${ctx.kind}/${ctx.id}`);
    else if(ctx.type==='day')fresh=await api(`/practice/day/${ctx.day}`);
    else if(ctx.type==='goal')fresh=await api(`/practice/feasibility/goal/${ctx.id}`);
    else [overview,fresh,commitment,cycleList]=await Promise.all([api('/overview'),api(`/practice/feasibility/project/${ctx.id}`),api(`/commitments/projects/${ctx.id}`),api(`/practice/projects/${ctx.id}/cycles`)]);
    if(epoch!==loadEpoch||ctx!==context)return;
    data=fresh;
    if(ctx.type==='goal')projectData={title:data.title};
    if(ctx.type==='project'){
      projectData=overview.projects.find(p=>p.id===ctx.id);if(!projectData)throw new Error('项目不存在');
      commitmentData=commitment;cycles=cycleList;
    }
    render();
  }
  function render(){
    if(context.type==='task')renderTask();else if(context.type==='day')renderDay();else renderProject();
  }
  function renderTask(){
    header(data.title,[['attributes','内容与估时'],['rehearsal','开始前预演'],['feedback','用时反馈'],['progress','困难进展'],['checklist','检查列表'],['history','历史']]);
    const content=$('.practice-content');
    if(tab==='attributes') {
      content.innerHTML=note('判断一项任务是否重要的标准：完成这项任务，是否确实有益于达成目标？')+
        form('attributes',area('goal','当时目标',data.goal)+`<div class="practice-grid"><label>执行难度${select('difficulty',{simple:'简单',difficult:'困难'},data.difficulty)}</label><label>计划重要性${select('importance',{unimportant:'不重要',ordinary:'一般',important:'重要'},data.importance)}</label></div>`+note(`首次判断：${labels[data.initial_importance]||'未标记'}；${data.reviewed_at?'已再次审视':'待再次审视，可在日程的“审视与当天反馈”核对全部任务'}`),'保存标记')+
        `<hr><h3>估计下一次行动</h3>${note(`原估计 ${data.original_estimate??'未记录'} 分钟 · 当前估计 ${data.estimated_minutes??'未填'} 分钟 · 已记录投入 ${data.recorded_minutes} 分钟。${({before_start:'事前估计',retrospective:'执行后补填',legacy_unknown:'历史估计，时点未知'})[data.estimate_origin]||'未记录事前估计'}。原估计不会被修订覆盖。`)}`+
        form('estimate',input('minutes','当前估计分钟',data.estimated_minutes??'','number','min="0" max="100000"')+area('reason','这次估计依据／修订原因','','required')+'<label>参考自己的哪次经验（自己判断是否可比）<select name="experience_id"><option value="">暂不引用</option></select></label>','保存估计与依据');
      api('/practice/experiences').then(r=>{const el=$('[name=experience_id]');if(el)el.innerHTML='<option value="">暂不引用</option>'+r.items.map(e=>`<option value="${e.id}">${esc(e.title)} · 原 ${e.original_estimate??'未知'} / 实 ${e.actual_minutes??'待核对'} 分 · ${esc(e.next_estimate)}</option>`).join('');}).catch(e=>message(e.message,true));
    } else if(tab==='rehearsal') {
      const r=data.rehearsal;
      content.innerHTML=note('只填需要的内容，也可以直接行动。预演不会替代必要启动条件。')+
        (data.legacy_rehearsal?`<details><summary>原来的预演笔记</summary><p>${esc(data.legacy_rehearsal)}</p></details>`:'')+
        form('rehearsal',area('first_step','第一步：现在能做的小行动',r.first_step)+area('sequence','接下来按什么顺序做？',r.sequence)+area('preparation','需要哪些材料、工具或条件？',r.preparation)+area('difficulty','最可能卡在哪里？',r.difficulty)+area('response','如果卡住，怎样应对？',r.response)+`<label>把准备内容明确转换为${select('preparation_action',{none:'只保留预演',checklist:'独立准备检查项',task:'独立筹备任务'},'none',null)}</label>`+area('comparison','事后对照：哪里与预想不同？',r.comparison),'保存预演')+
        `<details class="practice-support"><summary>有点难开始</summary><label>现在的顾虑${select('support',{mistake:'担心做不好',evaluation:'在意外部评价',unclear:'太大或准备不清楚',late:'已经开始晚了',setback:'遇到挫折'},'mistake',null)}</label><p data-support-text></p><p class="practice-note">本项完成标准：${esc(data.criteria||'尚未填写，可先选一个能检查的小结果')}</p>${button('start-small','保存第一步并开始 5 分钟','class="practice-primary"')}<p class="practice-note">也可以关闭提示，直接从执行区开始。</p></details>`;
      updateSupport();
    } else if(tab==='feedback') {
      const f=data.feedback||{};
      content.innerHTML=`<div class="practice-comparison"><div><span>原来预计</span><strong>${data.original_estimate??'未填'} 分</strong></div><div><span>区间已记录</span><strong>${data.recorded_minutes} 分</strong></div><div><span>上次确认总量</span><strong>${f.actual_minutes??'待核对'} 分</strong></div></div>`+
        (f.difference==null?'':note(`比原估计${f.difference>=0?'多':'少'} ${Math.abs(f.difference)} 分钟${f.percent==null?'':`（${f.percent>=0?'+':''}${f.percent}%）`}。${f.result==='completed'?'累计完成口径':'目前已投入，尚未完成'}；${f.comparable?'可比样本':'不作为可比完成样本'}。`))+
        note('确认总用时只有一个。自报总量不会追加工作片，也不会塞进完成当天的时间账。若需更正每日投入，请到“执行 → 投入记录”补齐或更正区间。')+
        form('feedback',`<div class="practice-grid"><label>实际结果${select('result',{completed:'完成',partial:'部分完成',rework:'需要返工'},f.result||(data.completed?'completed':'partial'),null)}</label><label>反馈依据${select('basis',{self_report:'自报总用时（不新增区间）',timer_checked:'核对计时区间',manual_checked:'核对补记区间',pending:'稍后核对'},f.basis||'self_report',null)}</label></div>`+
          input('feedback_date','本次结果日期（区间投入仍按真实发生日期统计）',f.feedback_date||f.date||dayISO(),'date','required')+
          input('actual_minutes','累计实际用时（分钟）',f.actual_minutes??(data.interval_count?data.recorded_minutes:''),'number','min="0" max="1000000" step="0.01"')+
          area('outcome','实际得到什么结果？',f.outcome)+area('reason','偏差原因：漏算步骤、陌生、返工、范围、打断等',f.reason)+
          `<label class="practice-inline"><input type="checkbox" name="scope_changed" ${f.scope_changed?'checked':''}>本次任务范围发生变化，单列处理估时差异</label>`+
          area('next_estimate','下次类似任务怎么估计？补哪些步骤或余量？',f.next_estimate)+
          `<details><summary>完成检查（${data.checklist.filter(c=>!c.done&&!c.not_applicable).length} 项待核对）</summary>${data.checklist.map(c=>`<p>${c.done?'已核对':c.not_applicable?'不适用':'待核对'} · ${esc(c.text)}</p>`).join('')||note('未配置检查项')}<p>验收标准：${esc(data.criteria||'未填写')}</p>${area('checklist_exception','确有例外时说明；也可切到检查列表逐项补查')}</details>`,'保存结果与用时反馈');
    } else if(tab==='progress') {
      const old=data.history.find(e=>e.type==='progress')?.data||{};
      const guidance=note('困难未完成但已有投入与推进，也值得如实记录。先核对漏记和现实原因，再选下一步；系统不会把未完成诊断为逃避。');
      content.innerHTML=(old.reduce_prompts?`<details><summary>需要时查看支持建议</summary>${guidance}</details>`:guidance)+
        form('progress',input('date','反馈日期',dayISO(),'date','required')+`<label>记录状态${select('status',{recorded:'有投入或进展',no_work:'已核对，本日没有投入',missing:'记录不完整，待核对'},old.status||'missing',null)}</label>`+
          area('advanced','推进了哪些内容？',old.advanced)+area('solved','解决了什么问题？',old.solved)+area('blocker','还卡在哪里／哪些条件欠缺？',old.blocker)+area('next_step','一个可执行的下一步',old.next_step)+
          `<label>需要的调整${select('help_choice',{none:'暂不调整',smaller_step:'缩小到一步',conditions:'补充资源与条件',help:'寻求帮助',time:'调整可用时间',goal:'重新评估目标'},old.help_choice||'none',null)}</label><label class="practice-inline"><input type="checkbox" name="reduce_prompts" ${old.reduce_prompts?'checked':''}>减少这项的困难提示</label>`,'保存进展');
    } else if(tab==='checklist') {
      content.innerHTML=note('准备核对与交付核对分组；普通检查项不会暗中变成硬性启动条件。排序只在这里使用明确的上移／下移按钮。')+
        form('checklist',`<div data-checks>${data.checklist.map(checkRow).join('')}</div>${button('add-check','＋ 添加检查项')}`,'保存检查列表');
    } else {
      content.innerHTML=data.history.length?data.history.map(e=>`<details><summary>${esc(({estimate:'估计修订',feedback:'用时反馈',rehearsal:'预演',attributes:'计划标记',importance_review:'再次审视',progress:'困难进展',checklist:'检查列表',experience_link:'引用经验',checklist_exception:'完成例外'})[e.type]||'操作记录')} · ${esc(e.date)}</summary>${historyEvidence(e.data)}</details>`).join(''):note('尚无新的训练记录；旧估计、预演、工作片继续保留。');
    }
  }
  function historyEvidence(d) {
    const fields={title:'当时任务',goal:'当时目标',original_estimate:'原估计分钟',original:'原估计分钟',current_estimate:'当前估计分钟',value:'本次估计分钟',actual_minutes:'确认实际分钟',recorded_minutes:'区间投入分钟',reason:'原因与依据',next_estimate:'下次估计经验',outcome:'实际结果',initial:'首次重要性',before:'调整前',reviewed:'再次判断',difficulty:'难度／难处',importance:'重要性',first_step:'第一步',sequence:'顺序',preparation:'准备',response:'应对',comparison:'事后对照',advanced:'推进内容',solved:'解决问题',blocker:'阻碍',next_step:'下一步',after:'调整后',items:'涉及检查项'};
    const valueText=value=>value==null?'未记录':typeof value==='boolean'?(value?'是':'否'):Array.isArray(value)?value.map(v=>typeof v==='object'?`${v.text||v.title||''} · ${v.done?'已核对':v.not_applicable?'不适用：'+v.not_applicable:'待核对'}`:String(v)).join('；'):typeof value==='object'?Object.entries(value).filter(([k])=>fields[k]).map(([k,v])=>fields[k]+'：'+valueText(v)).join('；'):labels[value]||String(value);
    const rows=Object.entries(d).filter(([k])=>fields[k]).map(([k,v])=>`<p><strong>${fields[k]}</strong>：${esc(valueText(v))}</p>`).join('');
    return rows||note('本次操作已保存；完整本人数据可导出查看。');
  }
  function checkRow(c,i){return `<div class="practice-check-row" data-check-id="${c.id??''}"><label class="practice-inline"><input name="done" type="checkbox" ${c.done?'checked':''}>已核对</label><input name="text" aria-label="检查项内容" maxlength="500" required value="${esc(c.text)}"><label>用途${select('group',{preparation:'开始前准备',delivery:'交付前核对'},c.group||'delivery',null)}</label><input name="not_applicable" aria-label="不适用说明（留空表示适用）" placeholder="不适用时填写说明" value="${esc(c.not_applicable)}"><div>${button('check-up','上移','aria-label="上移检查项"')}${button('check-down','下移','aria-label="下移检查项"')}${button('check-remove','移除')}</div></div>`;}
  function updateSupport(){const value=$('[name=support]')?.value,el=$('[data-support-text]');if(!el)return;el.textContent={mistake:'先做一个可检查的小结果。出错后可以检查和修改，不需要一次做好。',evaluation:'先看完成标准，写下一步。把有助于改进的意见与无建设性的否定分开。',unclear:'先缩小到现在能开始的一步，准备一份材料或做一个探索片，获得事实后再细化。',late:'按真实剩余时间，选本次还能交付的一小部分，然后开始。',setback:'记录具体卡点，再拆一步、补条件或寻求帮助。未完成本身不能说明原因。'}[value];}
  async function saveRehearsal(f){const b=Object.fromEntries(new FormData(f));await api(taskPath()+'/rehearsal',b,'PUT');}
  function renderDay(){
    header(`${context.day} 的安排与反馈`,[['review','审视重要性'],['reflection','当天反馈'],['report','日报']]);
    const content=$('.practice-content');
    if(tab==='review') {
      const leaves=data.tasks.filter(t=>!t.has_children);
      const total=leaves.reduce((sum,t)=>sum+(t.estimated_minutes||0),0),missing=leaves.filter(t=>t.estimated_minutes==null).length;
      const allocations=new Map((data.plan.allocations||[]).map(a=>[a.kind+':'+a.id,a.minutes]));
      const planned=data.plan.planned_minutes;
      content.innerHTML=form('day-plan',area('goal','今天希望推进的目标',data.plan.goal)+input('available_minutes','当天可用分钟（不知道可留空）',data.plan.available_minutes??'','number','min="0" max="1440"')+
        `<details><summary>安排当天投入（跨日任务分别分配）</summary>${leaves.map(t=>input('allocation-'+t.kind+'-'+t.id,t.title+' · 当天计划分钟',allocations.get(t.kind+':'+t.id)??'','number',`min="0" max="1440" data-allocation-kind="${t.kind}" data-allocation-id="${t.id}"`)).join('')}</details>`,'保存目标与当天投入')+
        note(`所列任务累计估计合计 ${total} 分钟，${missing} 项未估时；跨日累计不等于今天需要全部完成。当天明确计划 ${planned==null?'未安排':planned+' 分钟'}，${leaves.filter(t=>!allocations.has(t.kind+':'+t.id)).length} 项当天投入待分配。${data.plan.available_minutes==null?'尚无可用时间依据。':planned!=null&&planned>data.plan.available_minutes?'已超过可用时间，请调整当天负荷。':`当天可用 ${data.plan.available_minutes} 分钟。`}`)+
        note(leaves.some(t=>t.difficulty==='difficult')?'请为重要且困难的部分写下下一步，并安排真实可用时段；先处理简单部分可以为它留出投入。':'目前没有标记困难部分。核对是否只安排了容易部分；未标记不表示都简单。')+
        form('review',area('goal','审视时针对的目标',data.plan.goal||data.tasks.find(t=>t.goal)?.goal||'','required')+
          note('完成这项任务，是否确实有益于达成目标？先保存首次标记，再逐项回看；既检查显得重要的，也检查显得不重要的。')+
          `<div class="practice-review-list">${data.tasks.map((t,i)=>`<div data-review-row="${i}"><div><strong>${esc(t.title)}</strong><small>首次：${labels[t.initial_importance]||'未标记'} · ${t.reviewed_at?'已审视':'待审视'}</small></div>${select('importance'+i,{unimportant:'不重要',ordinary:'一般',important:'重要'},t.importance)}${button('task','估时与难度',`data-kind="${t.kind}" data-id="${t.id}"`)}</div>`).join('')}</div>`+button('save-initial','保存首次标记','class="practice-secondary"'),'再次审视并确认全部任务');
    } else if(tab==='reflection') {
      const f=data.reflection||{};
      content.innerHTML=form('reflection',`<label>今天有没有做过有趣，但无助于当时目标的事？${select('answer',{yes:'有',no:'没有',uncertain:'暂不确定',later:'稍后反馈'},f.answer||'later',null)}</label>`+
        `<fieldset><legend>可引用当天已有实际活动，保留原评价</legend>${data.report.work.map(w=>`<label class="practice-inline"><input type="checkbox" name="session_ids" value="${w.session_id}" ${(f.session_ids||[]).includes(w.session_id)?'checked':''}>${esc(w.title)} · ${(w.seconds/60).toFixed(1)} 分 · 实际重要性 ${labels[w.actual_importance]||'未判断'} · ${w.interesting===true?'有趣':w.interesting===false?'不觉得有趣':'趣味未判断'}</label>`).join('')||note('当天尚无区间活动可引用。')}</fieldset>`+
        area('activity','也可直接记录具体活动',f.activity)+input('minutes','只记得总分钟（单列说明，不重复累计）',f.minutes??'','number','min="0" max="1440"')+area('goal','当时目标',f.goal)+area('reason','原因／当时为什么这样选择？',f.reason)+area('next_step','下次打算／一个下一步',f.next_step)+note('此处引用与注意力浪费、非计划占用可以谈到同一活动，时间不相加。休息、健康、陪伴是否有益由你判断。'),'保存当天反馈');
    } else content.innerHTML=reportHTML(data.report)+`<a href="/static/index.html#long-term">在现有报告入口查看日报／周报</a>`;
  }
  function renderProject(){
    header(projectData.title,context.type==='goal'?[['feasibility','可行性'],['goal-settings','目标与期限']]:[['feasibility','可行性'],['commitment','阶段承诺'],['cycles','计划周期']]);
    const content=$('.practice-content');
    if(tab==='goal-settings') {
      content.innerHTML=note('目标和期限可以依据现实调整，历史判断保留原文。停止目标不会自动取消当前承诺；如需移出未完成工作，请到项目的当前承诺中明确调整。')+
        form('goal-revision',input('title','目标名称',data.title,'text','required maxlength="200"')+input('horizon_end','目标期限',data.horizon_end||'','date')+`<label>目标状态${select('status',{active:'继续推进',stopped:'依据现实停止此目标'},data.status||'active',null)}</label>`+area('reason','为何调整目标、期限或状态？','','required'),'保存目标版本')+
        `<details><summary>之前的版本</summary>${(data.revisions||[]).map(r=>`<p>${esc(localStamp(r.at))} · ${esc(r.data.before?.title)}（${esc(r.data.before?.horizon_end||'未定期限')}） → ${esc(r.data.after?.title)}（${esc(r.data.after?.horizon_end||'未定期限')}） · ${esc(r.data.after?.reason||r.data.source||'未填写原因')}</p>`).join('')}</details>`;
    } else if(tab==='feasibility') {
      const f=data.latest;
      content.innerHTML=`<blockquote>计划成功的前提是目标现实可行。<br>已经有人做到了。<br>我与那个人没有太大的差距。</blockquote>`+
        note('别人做到不保证自己能在当前期限做到；没有案例时，可先做探索步骤再重新评估。两个勾选不会自动宣布可行。')+
        form('feasibility',`<div class="practice-grid"><label>已经有人做到${select('someone_did_it',{yes:'有依据',no:'尚未找到'},f.someone_did_it===true?'yes':f.someone_did_it===false?'no':'','未确认')}</label><label>与对方差距不大${select('small_gap',{yes:'当前判断是',no:'存在较大差距'},f.small_gap===true?'yes':f.small_gap===false?'no':'','未确认')}</label></div>`+
          area('reference','参考谁／什么案例？',f.reference)+area('method','对方的方法',f.method)+area('reference_time','对方用了多久？',f.reference_time)+area('starting_point','自己的起点',f.starting_point)+area('resources','手上资源与实际条件',f.resources)+area('gap','差距在哪里？',f.gap)+area('bridge','如何弥补？',f.bridge)+area('deadline_check','当前期限是否足够？',f.deadline_check)+area('exploration','先做的探索步骤／已得到的事实',f.exploration)+area('reason','本次判断或修订依据',f.reason,'required'),'保存本次可行性判断')+
        `<details><summary>之前的判断（${data.history.length} 次）</summary>${data.history.map(h=>`<p>${esc(localStamp(h.at))} · ${esc(h.data.reason)} · ${esc(h.data.gap)}</p>`).join('')}</details>`;
    } else if(tab==='commitment') {
      const current=projectData.stages.find(s=>s.state==='current');
      const tasks=projectData.tasks.filter(t=>t.stage_id===current?.id&&!['completed','cancelled'].includes(t.state));
      content.innerHTML=`<blockquote>${esc(commitmentData.notice)}</blockquote>`+
        note(commitmentData.commitment?`已正式确认当前范围，保留 ${commitmentData.history.length} 个承诺版本。`:'当前范围尚未正式确认；草稿可编辑。正式开始项目时也会记录承诺。')+
        (!commitmentData.commitment?button('commit','确认当前列表承诺'):'')+
        (commitmentData.pending?button('resume-adjustment','恢复上次调整与等待',`data-id="${commitmentData.pending.id}"`):'')+
        `<h3>调整当前承诺</h3>${note('正常轮转、暂停和休息直接在执行区操作。改变未完成承诺时，先逐项选择去向，再展示具体后果和30秒暂停。先明确暂停或结束正在运行的工作片。')}`+
        form('adjustment-plan',`<label>交接目标${select('target_stage_id',Object.fromEntries(projectData.stages.filter(s=>s.state==='next').map(s=>[s.id,s.title])),context.targetStageId||'','保持当前阶段，只调整范围')}</label>`+
          `<div class="practice-review-list">${tasks.map(t=>`<div data-disposition="${t.id}"><strong>${esc(t.title)}</strong>${select('task-'+t.id,{retain:'保留推进（切换时随交接）',defer:'延期到独立下一阶段',cancel:'明确取消，保留投入'},'retain',null)}</div>`).join('')||note('当前未完成项为零，可正常交接，不强制等待。')}</div>`+
          `<details><summary>修改交付范围或条件</summary><label class="practice-inline"><input name="change_outcome" type="checkbox">本次修改项目交付结果</label>${area('outcome','新的交付结果',projectData.outcome)}${tasks.map(t=>`<label class="practice-inline"><input type="checkbox" name="change_criteria" value="${t.id}">修改《${esc(t.title)}》完成标准</label>${area('criteria-'+t.id,'新的完成标准',t.acceptance_criteria)}`).join('')}<div data-adjustment-conditions></div></details>`,'展示本次后果')+
        `<details><summary>承诺与调整历史</summary>${commitmentData.history.map(c=>`<details><summary>承诺版本 ${c.id} · ${esc(localStamp(c.at))}</summary><p>当时交付：${esc(c.snapshot.outcome||'未填写')}</p>${c.snapshot.tasks.map(t=>`<p>${esc(t.title)} · 预计 ${t.estimate??'未填'} 分 · 验收：${esc(t.criteria||'未填')}</p>`).join('')}</details>`).join('')}${commitmentData.adjustments.filter(a=>a.confirmed).map(a=>`<details><summary>调整 #${a.id} · ${esc(a.reason)}</summary><p>${a.impact.requires_wait?'前台累计等待 '+a.elapsed_ms/1000+' 秒':'草稿或正常交接，无强制等待'}</p>${a.impact.unfinished.map(t=>`<p>${esc(t.title)}：${({retain:'保留推进',defer:'延期',cancel:'取消而未完成'})[t.action]} · 已投入 ${t.recorded_minutes} 分</p>`).join('')}</details>`).join('')||note('尚无已确认调整')}</details>`;
      loadAdjustableConditions(tasks).catch(e=>message(e.message,true));
    } else if(tab==='cycles') {
      content.innerHTML=note('建议先尝试一周，再按事实选择两周、一个月、季度或年度。可以维持、缩短或延长，无需打卡解锁。简单事项和陌生事项的探索行动仍可直接开始。')+button('new-cycle','制定一轮计划')+
        (cycles.items.map(c=>`<article class="practice-cycle"><h3>${esc(c.expected_result)}</h3><p>${c.start_date} — ${c.end_date}</p><p>计划 ${c.evidence.planned_task_count} 项 / ${c.evidence.planned_minutes} 分 · 已记录区间 ${c.evidence.interval_count?c.evidence.actual_interval_minutes+' 分':'未记录'} · ${c.evidence.missing_estimates} 项未估时</p>${note(c.suggestions.join(' '))}${c.review?`<p>实际结果：${esc(c.review.actual_result)}</p><p>下一轮：${esc(c.review.next_changes)} · 理由：${esc(c.review.reason)}</p>${c.review.horizon_decision==='stop'?note('本轮选择停止；保留依据与结果。'):button('next-cycle','根据复盘制定下一轮',`data-id="${c.id}"`)}`:button('review-cycle','对照结果并复盘',`data-id="${c.id}"`)}</article>`).join('')||note('还没有计划周期'));
      content.querySelectorAll('.practice-cycle').forEach((card,i)=>{
        const c=cycles.items[i],rule=c.plan.feedback;
        if(c.plan.scope==='project')card.querySelectorAll('p')[1].textContent='本轮直接推进整个项目；已记录投入 '+(c.evidence.interval_count?c.evidence.actual_interval_minutes+' 分':'待核对');
        if(c.feedback_nodes?.length)card.insertAdjacentHTML('beforeend',`<section class="fb-daily"><p>每次交付：${esc(rule.deliverable)} · ${esc(rule.deadline)} 截止</p><details><summary>${c.feedback_nodes.length} 个具体反馈日期 · 打开提交入口</summary><div class="fb-node-chips">${c.feedback_nodes.map(n=>`<a class="fb-node-chip" href="/static/index.html?feedback=${n.id}&record=${n.date}#long-term">${n.date}${n.skipped_reason?' · 已跳过':''}</a>`).join('')}</div></details></section>`);
      });
    } else if(tab==='new-cycle') {
      const previous=cycles.items.find(c=>c.id===context.previousCycleId);
      content.innerHTML=(previous?note(`依据上一轮：${previous.review.next_changes}；跨度决定：${decisionLabel(previous.review.horizon_decision)}。`):'')+
        form('cycle',ShuranFeedback.plan.html(projectData,previous?.review.next_changes||''),'保存本轮计划');
      ShuranFeedback.plan.mount(content.querySelector('form'),projectData);
    } else {
      const c=cycles.items.find(c=>c.id===context.cycleId);
      content.innerHTML=note(`预期：${c.expected_result}；原计划 ${c.evidence.planned_minutes} 分／${c.evidence.planned_task_count} 项；已记录投入 ${c.evidence.interval_count?c.evidence.actual_interval_minutes+' 分':'未记录'}。未记录不视为没做，任务自报累计总量不冒充本周期区间。`)+
        note(c.suggestions.join(' '))+form('cycle-review',area('actual_result','实际得到了什么结果？','','required')+area('unforeseen','未预见的困难、依赖和变化')+area('conditions','哪些条件判断不成立？')+area('goal_help','哪些工作推进目标，哪些只是忙碌？')+area('next_changes','下一轮内容、方法和负荷怎样调整？','','required')+
          `<label>下一轮跨度决定${select('horizon_decision',{keep:'维持',shorten:'缩短',extend:'延长',stop:'理性停止此目标'},'keep',null)}</label>`+area('reason','选择依据（不能只看完成率）','','required'),'保存复盘与下一轮决定');
    }
  }
  async function loadAdjustableConditions(tasks){
    const readings=await Promise.all([api(`/readiness/project/${context.id}`),...tasks.map(t=>api(`/readiness/task/${t.id}`))]);
    const map=new Map();readings.flatMap(r=>r.conditions).filter(c=>c.strength==='required').forEach(c=>map.set(c.id,c));
    const el=$('[data-adjustment-conditions]');if(!el)return;
    el.innerHTML='<p>明确移除必要条件（仍保留原因与历史）</p>'+[...map.values()].map(c=>`<label class="practice-inline"><input type="checkbox" name="remove_condition" value="${c.id}">${esc(c.title)}</label>`).join('')+
      '<p>原有任务依赖可在完成当前阶段后调整；若需本轮移除，请选择：</p>'+tasks.flatMap(t=>(t.dependencies||[]).map(d=>`<label class="practice-inline"><input type="checkbox" name="remove_dependency" value="${d.id}">${esc(t.title)} 等待任务 #${d.prerequisite_id}</label>`)).join('');
  }
  async function submit(f){
    const b=Object.fromEntries(new FormData(f)),name=f.dataset.practiceForm;
    if(name==='attributes')await api(taskPath()+'/attributes',{...b,difficulty:b.difficulty||null,importance:b.importance||null},'PATCH');
    else if(name==='estimate')await api(taskPath()+'/estimate',{...b,minutes:b.minutes===''?null:Number(b.minutes),experience_id:b.experience_id?Number(b.experience_id):null});
    else if(name==='rehearsal')await saveRehearsal(f);
    else if(name==='feedback')await api(taskPath()+'/feedback',{...b,actual_minutes:b.actual_minutes===''?null:Number(b.actual_minutes),scope_changed:f.elements.scope_changed.checked});
    else if(name==='progress')await api(taskPath()+'/progress',{...b,reduce_prompts:f.elements.reduce_prompts.checked});
    else if(name==='checklist')await api(taskPath()+'/checklist',{items:[...f.querySelectorAll('.practice-check-row')].map(r=>({id:r.dataset.checkId===''?null:Number(r.dataset.checkId),text:r.querySelector('[name=text]').value,done:r.querySelector('[name=done]').checked,group:r.querySelector('[name=group]').value,not_applicable:r.querySelector('[name=not_applicable]').value||null}))},'PUT');
    else if(name==='day-plan')await api(`/practice/day/${context.day}/plan`,{goal:b.goal,available_minutes:b.available_minutes===''?null:Number(b.available_minutes),allocations:[...f.querySelectorAll('[data-allocation-id]')].filter(el=>el.value!=='').map(el=>({kind:el.dataset.allocationKind,id:Number(el.dataset.allocationId),minutes:Number(el.value)}))});
    else if(name==='review') {
      await api('/practice/review',{goal:b.goal,task_date:context.day,items:[...f.querySelectorAll('[data-review-row]')].map(row=>{const t=data.tasks[Number(row.dataset.reviewRow)];return {kind:t.kind,id:t.id,importance:row.querySelector('select').value||null};})});
    } else if(name==='reflection')await api(`/practice/day/${context.day}/reflection`,{...b,minutes:b.minutes===''?null:Number(b.minutes),session_ids:[...f.querySelectorAll('[name=session_ids]:checked')].map(el=>Number(el.value))});
    else if(name==='feasibility')await api(`/practice/feasibility/${context.type==='goal'?'goal':'project'}/${context.id}`,{...b,someone_did_it:b.someone_did_it===''?null:b.someone_did_it==='yes',small_gap:b.small_gap===''?null:b.small_gap==='yes'});
    else if(name==='goal-revision')await api(`/practice/goals/${context.id}/revise`,{...b,horizon_end:b.horizon_end||null});
    else if(name==='cycle')await api(`/practice/projects/${context.id}/cycles`,{...ShuranFeedback.plan.read(f),previous_cycle_id:context.previousCycleId||null});
    else if(name==='cycle-review')await api(`/practice/cycles/${context.cycleId}/review`,b);
    else if(name==='adjustment-plan') {
      const dispositions=[...f.querySelectorAll('[data-disposition]')].map(row=>({task_id:Number(row.dataset.disposition),action:row.querySelector('select').value}));
      const changes=[];
      if(f.elements.change_outcome?.checked)changes.push({kind:'project_outcome',value:b.outcome});
      f.querySelectorAll('[name=change_criteria]:checked').forEach(el=>changes.push({kind:'task_criteria',id:Number(el.value),value:b['criteria-'+el.value]}));
      f.querySelectorAll('[name=remove_condition]:checked').forEach(el=>changes.push({kind:'condition_remove',id:Number(el.value)}));
      f.querySelectorAll('[name=remove_dependency]:checked').forEach(el=>changes.push({kind:'dependency_remove',id:Number(el.value)}));
      if(!dispositions.length&&b.target_stage_id&&!changes.length){await api(`/stages/${b.target_stage_id}/activate`,{decision:'close',reason:'当前列表全部完成后的正常交接'});changed();await load();message('已完成正常交接，无需30秒等待');return;}
      adjustment=await api(`/commitments/projects/${context.id}/preview`,{target_stage_id:b.target_stage_id?Number(b.target_stage_id):null,dispositions,changes});showImpact();return;
    } else if(name==='confirm-adjustment') {
      await api(`/commitments/adjustments/${adjustment.id}/confirm`,b);clearInterval(timer);adjustment=null;const u=new URL(location.href);u.searchParams.delete('adjustment');history.replaceState(null,'',u);await load();changed();message('调整已确认；旧任务、投入和承诺历史均保留');return;
    }
    changed();if(name==='cycle'||name==='cycle-review')tab='cycles';await load();message('已保存');
  }
  function showImpact(){
    clearInterval(timer);dirty=false;const a=adjustment,i=a.impact;
    header('调整前的具体后果',[]);
    const keep=$('[data-practice=close]');keep.textContent='继续当前列表';keep.classList.add('practice-primary');keep.setAttribute('aria-label','继续当前列表，保留任务与当前阶段');
    $('.practice-header h2').insertAdjacentHTML('afterend','<p data-wait role="status" class="practice-wait-status"></p>');
    $('.practice-content').innerHTML=`<section class="practice-impact"><blockquote>${esc(i.notice)}</blockquote><p><strong>${esc(i.question)}</strong></p><h3>未完成事项与去向</h3>${i.unfinished.map(t=>`<article><strong>${esc(t.title)}</strong><p>${({retain:'保留推进',defer:'延期至下一阶段',cancel:'取消，仍未完成'})[t.action]} · 已投入 ${t.recorded_minutes} 分 · 原预计 ${t.estimate??'未填'} 分</p><p>验收：${esc(t.criteria||'未填写')}</p><p>已安排日期：${esc((t.scheduled_dates||[]).join('、')||'尚未安排')}</p></article>`).join('')||note('没有未完成项')}<h3>依赖影响</h3>${i.affected.map(t=>`<p>${esc(t.title)}：${esc(t.reason)}</p>`).join('')||note('没有登记受影响的其他依赖；未配置的现实影响仍需你核对。')}<h3>交付与时间预算</h3><p>${esc(i.delivery||'未填写交付结果')}</p><p>${esc(i.delivery_impact)}</p><p>既定目标期限：${esc(i.goal_deadline||'未记录')}</p><p>${esc(i.budget)}</p>${Object.entries(i.day_plans||{}).map(([day,record])=>`<p>${esc(day)} 当天安排 ${record.data.planned_minutes==null?'未明确':record.data.planned_minutes+' 分'} / 可用 ${record.data.available_minutes==null?'未知':record.data.available_minutes+' 分'}，调整后请重新分配。</p>`).join('')}<p>${esc(i.history)}</p>${i.changes.length?`<h3>本次范围与条件变更</h3>${i.changes.map(c=>`<p>${esc(({project_outcome:'项目交付结果',task_criteria:'任务完成标准',condition_remove:'移除必要条件',dependency_remove:'移除前置任务'})[c.kind])}${c.id?' #'+c.id:''}：${esc(c.value||'按本次方案处理')}</p>`).join('')}`:''}</section>`+
      `<div class="practice-wait">${form('confirm-adjustment',area('reason','调整原因（等待时可以填写）','','required'),'确认调整')}<small>只有后果面板在可见前台时累计。刷新可恢复；可见信号不证明注意力。等待不会计入工作实耗。</small>${button('repreview','方案或依赖变化后重新预览','class="practice-secondary"')}</div>`;
    const u=new URL(location.href);u.searchParams.set('adjustment',String(a.id));history.replaceState(null,'',u);updateWait();
    if(a.confirmed){message('此调整已经确认，重复提交不会再次切换');return;}
    timer=setInterval(()=>beat(),1000);beat();
  }
  function updateWait(){if(!adjustment)return;const text=$('[data-wait]'),confirmBtn=$('[data-practice-form=confirm-adjustment] button[type=submit]');if(text)text.textContent=adjustment.impact.requires_wait===false?'尚未开始的草稿无需强制等待；核对方案与原因后可以确认。':adjustment.remaining_seconds>0?`暂停思考：还需 ${adjustment.remaining_seconds} 秒`:'30秒已满，请核对原因后主动确认；也可以继续当前列表';if(confirmBtn)confirmBtn.disabled=adjustment.remaining_seconds>0||!$('[name=reason]')?.value.trim();}
  async function beat(force){
    if(!adjustment||!dialog.open||beating)return;
    const panel=$('.practice-impact'),rect=panel?.getBoundingClientRect();
    const visible=force===false?false:document.visibilityState==='visible'&&document.hasFocus()&&!!rect&&rect.bottom>0&&rect.top<innerHeight;
    beating=true;
    try{adjustment=await api(`/commitments/adjustments/${adjustment.id}/visible`,{token:lease,visible});updateWait();}
    catch(e){message(e.message,true);clearInterval(timer);timer=null;}
    finally{beating=false;}
  }
  function reportHTML(r){
    if(!r)return '';
    const feedback=r.feedback||[], work=r.work||[];
    return `<section class="practice-report"><h3>计划、执行与反馈</h3>${note(r.note)}<div class="practice-comparison"><div><span>真实区间投入</span><strong>${r.interval_count?(r.recorded_seconds/60).toFixed(1)+' 分':'未记录'}</strong></div><div><span>当时标记困难的投入</span><strong>${(r.difficult_seconds/60).toFixed(1)} 分</strong></div><div><span>有效估时样本</span><strong>${r.sample_count} 项</strong></div></div><details><summary>当天安排与可用时间</summary>${Object.entries(r.day_plans||{}).map(([day,p])=>`<p>${esc(day)} · 目标 ${esc(p.goal||'未填')} · 当天计划 ${p.planned_minutes==null?'未明确':p.planned_minutes+' 分'} / 可用 ${p.available_minutes==null?'未知':p.available_minutes+' 分'}；${(p.allocations||[]).map(a=>esc(a.title)+' '+a.minutes+' 分').join('；')}</p>`).join('')||note('未保存当天投入安排，不把任务跨日累计估计当作当天计划。')}</details><details open><summary>用时反馈（累计任务口径）</summary>${feedback.map(f=>`<article><strong>${esc(f.title)}</strong><p>原估计 ${f.original_estimate??'未知'} / 确认 ${f.actual_minutes??'待核对'} 分 · ${f.result==='completed'?'完成':f.result==='partial'?'部分完成':'返工'} · ${f.difference==null?'无法计算偏差':`比原估计${f.difference>=0?'多':'少'} ${Math.abs(f.difference)} 分`}</p><p>依据：${esc(({self_report:'自报总量',timer_checked:'计时区间核对',manual_checked:'补记区间核对',pending:'待核对'})[f.basis])}；未分配差额 ${f.unallocated_difference??'待核对'} 分，未追加本日时间账。</p><p>${esc(f.reason)} · 下次：${esc(f.next_estimate||'待反馈')}</p>${f.scope_changed?note('范围变化单列，不判作估时能力差'):''}</article>`).join('')||note('尚无本期完成反馈；不代表没有做。')}${(r.awaiting_feedback||[]).length?note('待反馈：'+r.awaiting_feedback.map(t=>t.title).join('、')):''}<p>缺估计 ${r.missing_estimate_count} 项；非已知事前估计 ${r.retrospective_count} 项；范围变化 ${r.scope_change_count} 项。${r.sample_count?`可比样本平均差额 ${r.mean_difference_minutes} 分；样本量仅供核对，不判断稳定能力。`:''}</p></details><details open><summary>困难部分与下一步</summary>${note(`有 ${(r.unknown_difficulty_seconds/60).toFixed(1)} 分钟的历史区间没有难度判断，未自动视为简单。`)}${(r.progress||[]).map(p=>`<article><strong>${esc(p.title)} · ${esc(p.date)}</strong><p>${({recorded:'已记录进展',no_work:'已核对，本日无投入',missing:'记录不完整'})[p.status]} · ${labels[p.difficulty]||'未标难度'}</p><p>推进：${esc(p.advanced||'待反馈')}；解决：${esc(p.solved||'待反馈')}</p><p>卡点：${esc(p.blocker||'待反馈')}；下一步：${esc(p.next_step||'待选择')}</p></article>`).join('')||note('困难进展待反馈；先核对漏记、实际条件，再决定缩小步骤、补资源、求助或调整目标。')}</details><details><summary>计划与实际重要性</summary>${(r.planning_reviews||[]).map(p=>`<p>${esc(p.date)} · ${esc(p.title)} · 初次 ${labels[p.initial]||'未标记'} / 本次审视前 ${labels[p.before]||'未标记'} / 再次 ${labels[p.reviewed]||'未标记'} · 当时目标 ${esc(p.goal)}</p>`).join('')}${work.map(w=>`<p>${esc(w.title)} · ${(w.seconds/60).toFixed(1)} 分 · 计划 ${labels[w.planned_importance]||'未标记'} / 实际 ${labels[w.actual_importance]||'未判断'} · ${w.interesting==null?'有趣与否未判断':w.interesting?'有趣':'不觉得有趣'} · 计划目标 ${esc(w.planned_goal||'未填')} / 实际评价目标 ${esc(w.goal||'未填')}</p>`).join('')||note('尚无实际活动评价。')}</details><details open><summary>有趣但无助于目标的活动</summary>${Object.entries(r.reflections||{}).map(([day,f])=>`<p>${day}：${({yes:'有',no:'没有',uncertain:'暂不确定',later:'稍后反馈'})[f.answer]} · ${esc(f.activity)}${f.minutes==null?'':`（自述 ${f.minutes} 分）`} · 引用 ${(f.session_ids||[]).length} 条原活动。下一步：${esc(f.next_step||'未填')}</p>`).join('')||note('未答，不能当作没有。')}<p class="practice-note">与注意力浪费和非计划占用有关联的活动只引用，不把时间再次相加。</p></details><details><summary>承诺调整与周期复盘</summary>${(r.adjustments||[]).map(a=>`<p>调整 #${a.id}：${esc(a.reason)}；任务去向与旧范围已留痕。</p>`).join('')}${(r.cycles||[]).map(c=>`<p>${esc(c.expected_result)} → ${esc(c.review.actual_result)}；下一轮：${esc(c.review.next_changes)}</p>`).join('')||''}</details></section>`;
  }
  globalThis.ShuranPractice={openTask,openDay,openProject,openGoal,reportHTML};
  document.addEventListener('DOMContentLoaded',()=>{
    const id=new URLSearchParams(location.search).get('adjustment');
    if(id)show();
    if(id)run(async()=>{adjustment=await api(`/commitments/adjustments/${Number(id)}`);const a=adjustment;await openProject(a.project_id,'commitment');adjustment=a;showImpact();});
  });
})();
