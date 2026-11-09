(() => {
  'use strict';
  const q = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const params = new URLSearchParams(location.search), project = Number(params.get('project')), cycleId = Number(params.get('cycle'));
  const fallback = `/static/projects.html?project=${project}`;
  const back = params.get('return') || fallback;
  const returnUrl = (() => { try { const url=new URL(back,location.origin); return url.origin===location.origin?url.href:fallback; } catch { return fallback; } })();
  q('#back').href=q('#cancel').href=returnUrl;
  let cycle, editable;
  function selections() {
    return editable.map(node => {const row=q(`[data-node="${node.id}"]`), moved=row.querySelector('[value="move"]').checked, field=row.querySelector('[type=date]');field.disabled=!moved;return {id:node.id,original_date:node.date,date:moved?field.value:node.date};});
  }
  function update() {
    const start=q('[name=start_date]').value,end=q('[name=end_date]').value,selected=selections(),notes=[];
    if(!start||!end||end<start)notes.push('请选择先后正确的周期日期。');
    const fixed=cycle.feedback_nodes.filter(n=>!editable.includes(n));
    const dates=[...selected.map(n=>n.date),...fixed.map(n=>n.date)];
    if(dates.some(d=>!d))notes.push('请为改期节点选择日期。');
    if(new Set(dates).size!==dates.length)notes.push('同一周期的两个反馈节点不能安排在同一天。');
    selected.forEach(n=>{if(n.date&&(n.date<start||n.date>end))notes.push(`${n.date} 的未完成反馈节点在新周期范围外，仍按此日期提醒和提交。`);});
    q('#summary').innerHTML=selected.map((n,i)=>`<p><strong>节点 ${i+1}</strong>　${esc(n.original_date)} → <strong>${esc(n.date||'待选择')}</strong>　${n.date===n.original_date?'保留原日期':'指定新日期'}</p>`).join('')+fixed.map(n=>`<p>${esc(n.date)} · ${n.submitted?'已提交':'已跳过'} → 日期保留</p>`).join('');
    q('#impact').textContent=notes.join(' ')||'节点日期均在新周期内，可以保存。';q('#impact').classList.toggle('ok',!notes.length);
    return notes.filter(n=>!n.includes('范围外'));
  }
  async function load() {
    if(!Number.isInteger(project)||project<=0||!Number.isInteger(cycleId)||cycleId<=0)throw Error('缺少项目或周期编号，请从项目页重新打开。');
    const response=await fetch(`/api/projects/practice/projects/${project}/cycles`,{headers:{Authorization:'Bearer '+localStorage.getItem('authToken')}});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'计划读取失败');
    cycle=data.items.find(c=>c.id===cycleId);if(!cycle)throw Error('周期不存在，请从项目页重新打开。');
    editable=cycle.feedback_nodes.filter(n=>!n.submitted&&!n.skipped_reason);
    q('#intro').textContent=`${cycle.expected_result} · 原周期 ${cycle.start_date} — ${cycle.end_date}`;
    q('[name=start_date]').value=cycle.start_date;q('[name=end_date]').value=cycle.end_date;
    const deliverable=cycle.plan.feedback?.deliverable||'未填写交付内容';
    q('#editable').innerHTML=editable.map((n,i)=>`<article class="node" data-node="${n.id}"><strong>反馈节点 ${i+1} · 原定 ${esc(n.date)}</strong><p>交付：${esc(deliverable)} · 尚未提交</p><p class="muted">${esc(cycle.plan.feedback?.deadline||'21:00')} 截止${cycle.plan.feedback?.reminders?' · 已开启提醒':''}</p><div class="choices"><label><input type="radio" name="node-${n.id}" value="keep" checked>保留原日期 · ${esc(n.date)}</label><label><input type="radio" name="node-${n.id}" value="move">指定新日期</label><input type="date" value="${esc(n.date)}" aria-label="节点 ${i+1} 的新日期" disabled></div></article>`).join('')||'<p>没有可改期的未完成反馈节点。</p>';
    q('#fixed').innerHTML=cycle.feedback_nodes.filter(n=>!editable.includes(n)).map(n=>`<p class="fixed"><strong>${esc(n.date)}</strong> · ${n.submitted?'已提交':'已跳过'} · 日期保留</p>`).join('')||'<p class="muted">没有已提交或已跳过的节点。</p>';
    q('#editor').hidden=false;update();
  }
  q('#editor').addEventListener('change',update);
  q('#editor').addEventListener('submit',async event=>{
    event.preventDefault();if(update().length)return;
    const button=q('button[type=submit]');button.disabled=true;q('#status').textContent='正在保存…';
    try {const response=await fetch(`/api/projects/practice/cycles/${cycleId}/dates`,{method:'PUT',headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),'Content-Type':'application/json'},body:JSON.stringify({original_start:cycle.start_date,original_end:cycle.end_date,start_date:q('[name=start_date]').value,end_date:q('[name=end_date]').value,nodes:selections()})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'保存失败，请重新核对');q('#status').textContent='已保存，正在返回计划周期。';location.href=returnUrl;}
    catch(e){q('#status').textContent=e.message;button.disabled=false;}
  });
  load().catch(e=>{q('#error').hidden=false;q('#error').textContent=e.message;});
})();
