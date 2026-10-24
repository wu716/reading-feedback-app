/* Shared visible task entry and dated feedback planning. No native date popover. */
(() => {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
  const date = s => new Date(s+'T12:00:00Z');
  const iso = d => d.toISOString().slice(0,10);
  const add = (s,n) => {const d=date(s);d.setUTCDate(d.getUTCDate()+n);return iso(d);};
  const select = (field,label,values) => `<label>${label}<select data-draft="${field}"><option value="">未填写</option>${Object.entries(values).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label>`;
  function draftRow(stages=[]) {
    return `<article class="fb-task-draft"><label class="fb-full">具体任务<input data-draft="title" maxlength="500" placeholder="写下一项要推进的工作；不拆分也可以直接保存"></label><div class="fb-fields">${stages.length?`<label>已有阶段<select data-draft="stage_id"><option value="">不分阶段</option>${stages.filter(s=>s.state!=='closed').map(s=>`<option value="${s.id}">${esc(s.title)}</option>`).join('')}</select></label>`:''}<label>${stages.length?'或新阶段（选填）':'阶段名称（选填）'}<input data-draft="stage_title" maxlength="200" placeholder="例如：探索与试做"></label>${select('familiarity','熟悉度',{familiar:'熟悉',unfamiliar:'陌生'})}${select('difficulty','难度',{simple:'简单',difficult:'困难'})}${select('importance','重要性',{unimportant:'不重要',ordinary:'一般',important:'重要'})}<label>预计分钟（选填）<input data-draft="estimated_minutes" type="number" min="0" max="100000"></label></div><label>完成依据（选填）<input data-draft="acceptance_criteria" maxlength="4000" placeholder="怎样判断这项工作已完成"></label><button type="button" class="fb-text" data-remove-draft>移除此项</button></article>`;
  }
  function composerHTML() {
    return `<section class="fb-composer"><div class="fb-heading"><h3>阶段与具体任务</h3><span>可选 · 各入口共用同一份任务</span></div><div data-drafts></div><button type="button" class="fb-secondary" data-add-draft>＋ 再写一项任务</button></section>`;
  }
  function mountComposer(root, stages=[]) {
    const list=root.querySelector('[data-drafts]');
    list.innerHTML=draftRow(stages);
    root.addEventListener('click', e=>{
      if(e.target.closest('[data-add-draft]')) {list.insertAdjacentHTML('beforeend',draftRow(stages));list.lastElementChild.querySelector('input').focus();root.dispatchEvent(new Event('input',{bubbles:true}));}
      if(e.target.closest('[data-remove-draft]')) {e.target.closest('.fb-task-draft').remove();if(!list.children.length)list.innerHTML=draftRow(stages);root.dispatchEvent(new Event('input',{bubbles:true}));}
    });
  }
  function drafts(root) {
    return [...root.querySelectorAll('.fb-task-draft')].flatMap(row=>{
      const d=Object.fromEntries([...row.querySelectorAll('[data-draft]')].map(el=>[el.dataset.draft,el.value.trim()]));
      if(!d.title) {
        if(Object.entries(d).some(([k,v])=>k!=='title'&&v))throw new Error('任务属性已填写，请补上具体任务名称');
        return [];
      }
      if(d.stage_id&&d.stage_title)throw new Error('请选择已有阶段，或填写新阶段名称');
      return [{...d,stage_id:d.stage_id?Number(d.stage_id):null,familiarity:d.familiarity||null,difficulty:d.difficulty||null,
        importance:d.importance||null,estimated_minutes:d.estimated_minutes===''?null:Number(d.estimated_minutes)}];
    });
  }
  function planHTML(project, expected='') {
    return `<div class="fb-plan"><label>本轮跨度<select name="horizon"><option value="week">一周</option><option value="fortnight">两周</option><option value="month">一个月</option><option value="quarter">一个季度</option><option value="year">一年</option><option value="custom">自定日期</option></select></label><div class="fb-range"><label>开始日期<button type="button" data-range="start_date"></button><input type="hidden" name="start_date" value="${today()}"></label><span>至</span><label>结束日期<button type="button" data-range="end_date"></button><input type="hidden" name="end_date" value="${add(today(),6)}"></label></div><label>本轮预期结果（选填）<textarea name="expected_result" maxlength="4000" placeholder="可以写探索问题、想得到的认识或具体成果">${esc(expected)}</textarea></label><label>本轮可用分钟（未知留空）<input name="available_minutes" type="number" min="0" max="1000000"></label><fieldset class="fb-scope"><legend>本轮推进范围</legend><p>不选择任务时，直接推进整个项目。</p>${project.tasks.filter(t=>!['completed','cancelled'].includes(t.state)).map(t=>`<label class="fb-check"><input type="checkbox" name="task_ids" value="${t.id}">${esc(t.title)}</label>`).join('')}${composerHTML()}</fieldset><section class="fb-rule"><h3>反馈节点与每次交付</h3><label>安排方式<select data-freq><option value="none">暂不设置反馈节点</option><option value="daily">每天</option><option value="weekly">每周指定星期</option><option value="dates">选定具体日期</option></select></label><div class="fb-weekdays" aria-label="选择反馈星期">${['一','二','三','四','五','六','日'].map((d,i)=>`<label><input type="checkbox" data-weekday="${i}"><span>周${d}</span></label>`).join('')}</div><p class="fb-hint" data-calendar-hint>选择开始或结束日期按钮，可在日历中调整本轮范围。</p><div class="fb-calendar"><div class="fb-calendar-head"><button type="button" data-month="-1" aria-label="上个月">‹</button><strong data-month-label></strong><button type="button" data-month="1" aria-label="下个月">›</button></div><div class="fb-week-head">${['一','二','三','四','五','六','日'].map(s=>`<span>${s}</span>`).join('')}</div><div class="fb-calendar-grid" data-calendar></div></div><details class="fb-dates"><summary data-dates-label></summary><div data-dates-list></div></details><div data-rule-fields hidden><label>每次交付什么<textarea data-deliverable maxlength="4000" placeholder="例如：一份自学研究报告，或一次练习的照片及说明"></textarea></label><fieldset><legend>成果形式（可多选，也可不限）</legend><div class="fb-formats">${Object.entries({text:'文字',link:'链接',image:'图片',document:'文档',audio:'音频',video:'视频',other:'其他／实践说明'}).map(([k,v])=>`<label class="fb-check"><input type="checkbox" data-format="${k}">${v}</label>`).join('')}</div></fieldset><label>检查标准（选填）<textarea data-criteria maxlength="4000" placeholder="写下适合这个成果的检查依据"></textarea></label><details><summary>文字成果的可选标准</summary><label>最低字数（不适用留空）<input data-min-words type="number" min="1" max="1000000"></label><p class="fb-hint">链接、图片和文件可先提交，无法自动核对的标准会标为待人工检查。</p></details><div class="fb-fields"><label>当日截止<input data-deadline type="time" value="21:00" required></label><label>当日提醒<input data-remind-at type="time" value="20:00" required></label></div><label class="fb-check"><input data-reminders type="checkbox">到点提醒提交（应用内、系统通知与邮件遵循账号设置）</label></div></section></div>`;
  }
  function mountPlan(form, project) {
    mountComposer(form.querySelector('.fb-composer'),project.stages);
    const q=s=>form.querySelector(s), state={month:today().slice(0,7)+'-01',mode:null,dates:new Set(),adds:new Set(),skips:new Set()};
    form._feedbackState=state;
    function selected() {
      const start=form.elements.start_date.value,end=form.elements.end_date.value,freq=q('[data-freq]').value;
      const weekdays=new Set([...form.querySelectorAll('[data-weekday]:checked')].map(e=>Number(e.dataset.weekday)));
      const out=[];
      if(freq==='none'||end<start)return out;
      for(let d=start,n=0;d<=end&&n<733;d=add(d,1),n++) {
        const base=freq==='daily'||freq==='dates'&&state.dates.has(d)||freq==='weekly'&&weekdays.has((date(d).getUTCDay()+6)%7);
        if((base||state.adds.has(d))&&!state.skips.has(d))out.push(d);
      }
      return out;
    }
    state.selected=selected;
    function render() {
      const start=form.elements.start_date.value,end=form.elements.end_date.value,freq=q('[data-freq]').value,days=new Set(selected());
      form.querySelectorAll('[data-range]').forEach(b=>{b.textContent=form.elements[b.dataset.range].value.replaceAll('-',' / ');b.setAttribute('aria-pressed',String(state.mode===b.dataset.range));});
      q('[data-month-label]').textContent=state.month.slice(0,4)+' 年 '+Number(state.month.slice(5,7))+' 月';
      q('.fb-weekdays').hidden=freq!=='weekly';q('[data-rule-fields]').hidden=freq==='none';
      form.querySelectorAll('[data-rule-fields] input,[data-rule-fields] textarea').forEach(el=>el.disabled=freq==='none');
      q('[data-deliverable]').required=freq!=='none';
      q('[data-calendar-hint]').textContent=state.mode?`正在选择${state.mode==='start_date'?'开始':'结束'}日期`:(freq==='none'?'点击上方日期按钮调整范围。':'深蓝日期为实际反馈日，点击可以增补或跳过；切换月份可继续选择。');
      const first=date(state.month), offset=(first.getUTCDay()+6)%7;
      q('[data-calendar]').innerHTML=Array.from({length:42},(_,i)=>{const d=add(state.month,i-offset),inside=d>=start&&d<=end,current=d.slice(0,7)===state.month.slice(0,7),active=days.has(d);
        return `<button type="button" data-calendar-date="${d}" class="${active?'is-selected ':''}${inside?'in-range ':''}${current?'':'other-month'}" aria-label="${d}${active?'，反馈日':''}" aria-pressed="${active}" ${!state.mode&&(!inside||freq==='none')?'disabled':''}>${Number(d.slice(8))}${d===today()?'<i></i>':''}</button>`;}).join('');
      q('[data-dates-label]').textContent=`共 ${days.size} 个反馈节点 · 查看具体日期`;
      q('[data-dates-list]').textContent=[...days].join('、')||'尚未设置反馈节点';
    }
    form.addEventListener('click',e=>{
      const b=e.target.closest('[data-range],[data-month],[data-calendar-date]');if(!b)return;
      e.preventDefault();
      if(b.dataset.range){state.mode=state.mode===b.dataset.range?null:b.dataset.range;state.month=form.elements[b.dataset.range].value.slice(0,7)+'-01';}
      else if(b.dataset.month){const d=date(state.month);d.setUTCMonth(d.getUTCMonth()+Number(b.dataset.month));state.month=iso(d);}
      else {const d=b.dataset.calendarDate;
        if(state.mode){form.elements[state.mode].value=d;form.elements.horizon.value='custom';state.mode=null;}
        else if(q('[data-freq]').value==='dates'){state.dates.has(d)?state.dates.delete(d):state.dates.add(d);}
        else if(selected().includes(d)){state.adds.delete(d);state.skips.add(d);}
        else{state.skips.delete(d);state.adds.add(d);}
        form.dispatchEvent(new Event('input',{bubbles:true}));
      }
      render();
    });
    form.addEventListener('change',e=>{
      if(e.target.name==='horizon'){
        const start=form.elements.start_date.value,d=date(start),h=e.target.value;
        if(h==='week'||h==='fortnight')d.setUTCDate(d.getUTCDate()+(h==='week'?7:14));
        else if(h==='month'||h==='quarter'){const day=d.getUTCDate();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+(h==='month'?1:3));const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();d.setUTCDate(Math.min(day,last));}
        else if(h==='year'){const month=d.getUTCMonth();d.setUTCFullYear(d.getUTCFullYear()+1);if(d.getUTCMonth()!==month)d.setUTCDate(0);}
        if(h!=='custom')form.elements.end_date.value=add(iso(d),-1);
      }
      if(e.target.matches('[data-freq]')){state.adds.clear();state.skips.clear();}
      render();
    });render();
  }
  function serializePlan(f) {
    const q=s=>f.querySelector(s),start=f.elements.start_date.value,end=f.elements.end_date.value,state=f._feedbackState;
    if(end<start||date(end)-date(start)>731*86400000)throw new Error('请选择先后正确、两年以内的日期范围');
    const freq=q('[data-freq]').value;
    if(freq!=='none'&&!state.selected().length)throw new Error('请在日历中选择实际反馈日期');
    const within=set=>[...set].filter(d=>d>=start&&d<=end);
    const payload = {start_date:start,end_date:end,horizon:f.elements.horizon.value,expected_result:f.elements.expected_result.value,
      available_minutes:f.elements.available_minutes.value===''?null:Number(f.elements.available_minutes.value),
      task_ids:[...f.querySelectorAll('[name=task_ids]:checked')].map(el=>Number(el.value)),new_tasks:drafts(f),
      feedback:{frequency:freq,weekdays:[...f.querySelectorAll('[data-weekday]:checked')].map(el=>Number(el.dataset.weekday)),
        dates:within(state.dates),add_dates:within(state.adds),skip_dates:within(state.skips),deadline:q('[data-deadline]').value,
        remind_at:q('[data-remind-at]').value,reminders:q('[data-reminders]').checked,deliverable:q('[data-deliverable]').value,
        formats:[...f.querySelectorAll('[data-format]:checked')].map(el=>el.dataset.format),criteria:q('[data-criteria]').value,
        min_words:q('[data-min-words]').value?Number(q('[data-min-words]').value):null}};
    if(freq==='none')payload.feedback={frequency:'none'};
    return payload;
  }
  window.ShuranFeedback={esc,today,add,composer:{html:composerHTML,mount:mountComposer,read:drafts,reset:root=>root.querySelector('[data-drafts]').innerHTML=draftRow()},plan:{html:planHTML,mount:mountPlan,read:serializePlan}};
  document.addEventListener('DOMContentLoaded',()=>{const f=document.getElementById('projectForm');if(f){const root=f.querySelector('[data-project-tasks]');root.innerHTML=composerHTML();mountComposer(root);}});
})();
