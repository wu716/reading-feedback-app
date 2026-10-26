/* Project submissions sit beside the existing detailed long-term ledger. */
(() => {
  'use strict';
  const {esc,today,add}=ShuranFeedback;
  const states={pending:'待提交',overdue:'已到期 · 待提交',submitted:'已提交 · 待检查',accepted:'检查通过',needs_changes:'待补充',skipped:'本次已跳过'};
  const drafts=new Map(),progressDrafts=new Map(),pairings=new Map();let currentDate,epoch=0,token,bindings=[],backlogLoaded=0;
  const root=()=>document.getElementById('feedbackDaily');
  const request=async(path,options={})=>{
    const r=await fetch('/api'+path,{...options,headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}});
    const body=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:body.detail?.[0]?.msg||'操作失败，请重试');return body;
  };
  const post=(path,data)=>request(path,{method:'POST',body:JSON.stringify(data)});
  const key=()=>crypto.randomUUID?.()||'submission_'+Date.now()+Math.random().toString(36).slice(2);
  const time=s=>Math.round(s/60)+' 分钟';
  const stamp=s=>new Date(s.endsWith('Z')?s:s+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  function clear(){epoch++;drafts.clear();progressDrafts.clear();pairings.clear();bindings=[];token=localStorage.getItem('authToken');if(root())root().innerHTML='';}
  function progressForms(projects) {
    return '<section class="df-progress"><h3>当天项目与任务进展</h3><p class="fb-hint">推进、卡点与下一步按任务保存。没有投入可明确核对；提交成果与检查通过仍分别记录。</p>'+projects.map(p=>`<details class="df-project"><summary><strong>${esc(p.title)}</strong><span>${time(p.actual_seconds)} · 完成 ${p.completed_tasks.length} 项</span></summary>${(p.tasks||[]).map(t=>{
      const d=progressDrafts.get(currentDate+':'+t.id)||t.progress||{};
      return `<form class="df-task" data-progress-task="${t.id}" data-progress-date="${currentDate}"><h4>${esc(t.title)}</h4><label>记录状态<select name="status">${Object.entries({missing:'待核对',recorded:'有投入或进展',no_work:'已核对，今天没有投入'}).map(([v,n])=>`<option value="${v}" ${v===(d.status||'missing')?'selected':''}>${n}</option>`).join('')}</select></label>${Object.entries({advanced:'推进了什么',solved:'解决了什么问题',blocker:'卡点或欠缺条件',next_step:'下一步'}).map(([key,label])=>`<label>${label}<textarea name="${key}" maxlength="4000" rows="2">${esc(d[key]||'')}</textarea></label>`).join('')}<button type="submit" class="fb-primary">保存这项反馈</button><p role="status" class="fb-hint">${t.progress?'这一天已有保存记录，可继续修改。':''}</p></form>`;
    }).join('')||'<p class="fb-hint">本项目没有可填写的任务；成果节点见下方。</p>'}</details>`).join('')+'</section>';
  }
  function draft(id){if(!drafts.has(id))drafts.set(id,{client_id:key(),text:'',links:'',note:'',attachment_ids:[],attachments:[],files:[]});return drafts.get(id);}
  function versions(items) {
    return items.map(s=>`<article class="fb-version"><strong>第 ${s.version} 版 · ${states[s.status]}</strong><small>${esc(stamp(s.submitted_at))}</small>${s.content.text?`<p class="fb-content">${esc(s.content.text)}</p>`:''}${s.content.links.map(l=>`<a href="${esc(l)}" target="_blank" rel="noopener noreferrer">${esc(l)}</a>`).join('')}${(s.content.attachments||[]).map(f=>`<button type="button" class="fb-text" data-download="${f.id}" data-filename="${esc(f.filename)}">附件：${esc(f.filename)}</button>`).join('')}${s.content.note?`<p>${esc(s.content.note)}</p>`:''}${s.content.criteria_check==='needs_manual_check'?'<p class="fb-hint">字数标准待人工核对；链接与附件未自动计数。</p>':''}${s.review_note?`<p>检查记录：${esc(s.review_note)}</p>`:''}</article>`).join('');
  }
  function eventHistory(events){return events?.length?'<h4>节点与检查记录</h4>'+events.map(e=>`<p class="fb-hint">${esc(stamp(e.at))} · ${e.action==='delivery_review'?`${states[e.detail.before]||'待检查'} → ${states[e.detail.after]||'待核对'}：${esc(e.detail.note)}`:esc(({skip_node:'跳过本次',restore_node:'恢复本次'})[e.action]||e.action)+'：'+esc(e.detail.reason||'')}</p>`).join(''):'';}
  function card(n,open=false) {
    const d=draft(n.id),latest=n.latest;
    return `<details class="fb-node" data-node="${n.id}" ${open?'open':''}><summary><span><strong>${esc(n.project_title)}</strong><small>${n.due_date} · ${n.deadline} 截止</small></span><span class="fb-badge ${n.status}">${states[n.status]}${n.late?' · 迟交':''}</span></summary><div class="fb-node-body"><p class="fb-deliverable">${esc(n.requirement.deliverable)}</p>${n.requirement.criteria?`<p>检查依据：${esc(n.requirement.criteria)}</p>`:''}${n.requirement.min_words?`<p class="fb-hint">本节点的文字标准：${n.requirement.min_words} 字；附件和外部内容可人工检查。</p>`:''}${n.skipped_reason?`<p>跳过原因：${esc(n.skipped_reason)}</p><button type="button" class="fb-secondary" data-restore="${n.id}">恢复这个节点</button>`:`<form data-feedback-submission="${n.id}"><label>成果或实践说明<textarea data-value="text" rows="4" maxlength="100000" placeholder="可以直接写内容，也可以只提交下方链接或附件">${esc(d.text)}</textarea></label><label>成果链接（每行一个）<textarea data-value="links" rows="2" placeholder="https://…">${esc(d.links)}</textarea></label><label>图片、文档、音频或视频<input data-files type="file" multiple accept="image/*,audio/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.epub,.zip"></label><p class="fb-hint">每个文件最多 25 MB，每版最多 8 个附件。已提交后可继续补交新版本。</p><div data-file-list>${d.attachments.map(f=>`<span>${esc(f.filename)}</span>`).join('')}</div><label>补充说明（选填）<textarea data-value="note" maxlength="4000">${esc(d.note)}</textarea></label><button class="fb-primary" type="submit">${latest?'提交补充版本':'提交本次成果'}</button><p class="fb-status" role="status"></p></form>`}${latest?`<section class="fb-review"><h4>检查这次成果</h4><p class="fb-hint">提交与检查分别记录，请根据实际成果确认。</p><label>检查依据或需要补充的内容<textarea data-review-note maxlength="4000">${esc(latest.review_note||'')}</textarea></label><div class="fb-actions"><button type="button" class="fb-secondary" data-review="accepted" data-submission="${latest.id}">检查通过</button><button type="button" class="fb-secondary" data-review="needs_changes" data-submission="${latest.id}">需要补充</button></div></section><details class="fb-history"><summary>提交与检查历史 · ${latest.version} 版</summary><div data-versions>${versions([latest])}</div><button type="button" class="fb-text" data-history="${n.id}">读取全部版本</button></details>`:''}${!latest&&!n.skipped_reason?`<details class="fb-skip"><summary>本次不需要交付</summary><label>跳过原因<textarea data-skip-reason maxlength="4000"></textarea></label><button type="button" class="fb-secondary" data-skip="${n.id}">记录原因并跳过</button></details>`:''}<p class="fb-card-status" role="status"></p></div></details>`;
  }
  function render(items,projects) {
    const present=items.filter(n=>n.due_date===currentDate),pending=items.filter(n=>n.due_date<currentDate&&['pending','overdue','needs_changes'].includes(n.status));
    const upcoming=items.filter(n=>n.due_date>currentDate);
    const chosen=Number(new URL(location.href).searchParams.get('feedback'));
    root().innerHTML=`<section class="fb-daily-projects"><div class="fb-heading"><h2>项目推进与成果反馈</h2><a href="/static/projects.html">打开项目与计划 ↗</a></div><p class="fb-hint">按节点提交成果；项目投入引用原任务区间，与下方活动时间分别呈现。</p>${projects.map(p=>`<p class="fb-project-effort"><strong>${esc(p.title)}</strong><span>${p.intervals.length?'已记录投入 '+time(p.actual_seconds):'当天尚无投入区间'} · 完成任务 ${p.completed_tasks.length} 项</span></p>`).join('')}<div data-today-nodes>${present.map(n=>card(n,n.id===chosen)).join('')||'<p class="fb-empty">这一天没有预设反馈节点。可以在项目的“计划周期”中设置；下方长期方向仍可直接填写。</p>'}</div>${pending.length?`<details class="fb-past" ${pending.some(n=>n.id===chosen)?'open':''}><summary>此前待补交 · ${pending.length} 项</summary>${pending.map(n=>card(n,n.id===chosen)).join('')}</details>`:''}${upcoming.length?`<details class="fb-upcoming"><summary>接下来 7 天 · ${upcoming.length} 个节点</summary>${upcoming.map(n=>card(n,n.id===chosen)).join('')}</details>`:''}</section><details id="readerConnection" class="fb-reader fb-reader-compact"><summary><span class="fb-reader-dot" aria-hidden="true"></span><strong>知间阅读联动</strong><span class="fb-reader-summary" data-reader-summary>正在读取状态…</span></summary><div class="fb-reader-body"><div class="fb-reader-toolbar"><button type="button" class="fb-text" data-reader-refresh>刷新状态</button></div><div data-reader-status>正在读取关联状态…</div><p class="fb-hint">同步到每一天、每一本书的阅读时长；纸书等补记保留。累计历史只作为基线，核对日期后才记作当天完整。</p><div data-pairing role="status"></div></div></details>`;
    root().insertAdjacentHTML('beforeend','<details class="fb-reader"><summary>提醒与邮件发送记录</summary><p class="fb-hint">应用内提醒会保留在铃铛中；系统通知需要设备授权，邮件按账号设置发送。</p><button type="button" class="fb-text" data-deliveries>查看最近发送情况</button><div data-deliveries-list></div></details>');
    root().querySelector('.fb-heading').insertAdjacentHTML('afterend',progressForms(projects));
    root().querySelectorAll('.fb-project-effort').forEach(el=>el.remove());
    if(chosen)root().querySelector(`[data-node="${chosen}"]`)?.scrollIntoView({block:'center'});
  }
  async function load(day) {
    if(!root())return;
    const auth=localStorage.getItem('authToken');
    if(token!==auth){drafts.clear();progressDrafts.clear();pairings.clear();token=auth;bindings=[];root().innerHTML='';}
    const requestEpoch=++epoch;currentDate=day;
    try {
      const [nodes,projects,backlog]=await Promise.all([request(`/feedback/occurrences?start=${day}&end=${add(day,7)}`),request(`/feedback/progress?day=${day}`),request(`/feedback/backlog?before=${day}`)]);
      if(requestEpoch!==epoch||auth!==localStorage.getItem('authToken'))return;
      backlogLoaded=backlog.items.length;render([...nodes.items,...backlog.items],projects.items);
      const past=root().querySelector('.fb-past');
      if(past&&backlog.total>backlogLoaded){past.querySelector('summary').textContent='此前待补交 · '+backlog.total+' 项';past.insertAdjacentHTML('beforeend','<button type="button" class="fb-text" data-more-backlog>继续读取更早的待交节点</button>');}
      await readerStatus();
    }catch(e){if(requestEpoch===epoch)root().innerHTML=`<p class="fb-error">${esc(e.message)}</p><button type="button" class="fb-secondary" data-retry-feedback>重新读取项目反馈</button>`;}
  }
  async function readerStatus() {
    const auth=localStorage.getItem('authToken'),r=await request('/integrations/reader/status');
    if(auth!==localStorage.getItem('authToken'))return;
    const panel=root()?.querySelector('[data-reader-status]');if(!panel)return;
    bindings=r.items;
    const summary=root()?.querySelector('[data-reader-summary]');
    if(summary){const active=r.items.filter(b=>b.active),problem=active.some(b=>['retry','needs_relink','resync_required'].includes(b.sync_status));summary.textContent=active.length?(problem?'已连接 · 需要核对':'已连接 · 同步正常'):r.configured?'尚未关联':'未配置';summary.closest('.fb-reader-compact')?.classList.toggle('is-connected',active.length>0);summary.closest('.fb-reader-compact')?.classList.toggle('has-sync-issue',problem);}
    panel.innerHTML=r.items.map(b=>`<article><strong>${esc(b.source_label)}</strong> · ${b.active?'已授权同步':'已解除，历史保留'}<p>${b.last_sync_at?'最近接收：'+esc(stamp(b.last_sync_at)):'尚未收到逐日逐书数据'}${b.detail_started_on?' · 明细始于 '+b.detail_started_on:''}</p>${b.historical_baseline.length?`<details><summary>历史累计基线（未分配到具体日期）</summary>${b.historical_baseline.map(book=>`<p>${esc(book.title)} · ${time(book.active_seconds)}</p>`).join('')}</details>`:''}${b.active?`<button type="button" class="fb-text" data-reader-revoke="${b.id}">解除关联</button>`:''}</article>`).join('')+(!r.items.some(b=>b.active)?`<p>${r.configured?'登录知间后，用一次性关联码确认两边账号。':'知间联动尚未配置；当前可手动记录。'}</p><button type="button" class="fb-secondary" data-reader-pair ${r.configured?'':'disabled'}>生成 10 分钟关联码</button>`:'');
    panel.querySelectorAll('article').forEach((article,i)=>{const binding=r.items[i],names={pending:'等待首次同步',synced:'同步完成',catching_up:'正在追赶历史',retry:'稍后重试',needs_relink:'授权或来源数据待核对',resync_required:'正在恢复完整读取',stopped:'已停止'};article.insertAdjacentHTML('beforeend',`<p>${names[binding.sync_status]||'待核对同步状态'}${binding.sync_error?'：'+esc(binding.sync_error):''}</p>${binding.active&&r.configured?`<button type="button" class="fb-secondary" data-reader-sync="${binding.id}">立即同步</button>`:''}`);});
  }
  function replaceNode(data) {
    const node=root().querySelector(`[data-node="${data.id}"]`);if(node)node.outerHTML=card(data,true);
    window.reminderNotificationService?.checkPendingReminders();
  }
  async function download(id,name) {
    const r=await fetch('/api/feedback/attachments/'+id,{headers:{Authorization:'Bearer '+localStorage.getItem('authToken')}});
    if(!r.ok)throw new Error('附件下载失败，请重新登录或稍后重试');
    const u=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    if(!root())return;
    root().addEventListener('input',e=>{const f=e.target.closest('[data-progress-task]');if(f)progressDrafts.set(f.dataset.progressDate+':'+f.dataset.progressTask,Object.fromEntries(new FormData(f)));});
    root().addEventListener('change',e=>{const f=e.target.closest('[data-progress-task]');if(f)progressDrafts.set(f.dataset.progressDate+':'+f.dataset.progressTask,Object.fromEntries(new FormData(f)));});
    root().addEventListener('submit',async e=>{
      const f=e.target.closest('[data-progress-task]');if(!f)return;e.preventDefault();
      if(f.dataset.busy)return;f.dataset.busy='1';const button=f.querySelector('button'),status=f.querySelector('[role=status]'),auth=localStorage.getItem('authToken');button.disabled=true;
      try{await post(`/projects/practice/tasks/task/${f.dataset.progressTask}/progress`,{...Object.fromEntries(new FormData(f)),date:f.dataset.progressDate});if(auth!==localStorage.getItem('authToken'))return;progressDrafts.delete(f.dataset.progressDate+':'+f.dataset.progressTask);status.textContent='已保存到服务器，可在日报查看。';}
      catch(err){status.textContent=err.message+'；填写内容保留，请重试。';}finally{button.disabled=false;delete f.dataset.busy;}
    });
    root().addEventListener('input',e=>{const f=e.target.closest('[data-feedback-submission]');if(f&&e.target.dataset.value)draft(Number(f.dataset.feedbackSubmission))[e.target.dataset.value]=e.target.value;});
    root().addEventListener('change',e=>{if(e.target.matches('[data-files]')){const f=e.target.closest('form'),d=draft(Number(f.dataset.feedbackSubmission));d.files=[...e.target.files];f.querySelector('[data-file-list]').textContent=[...d.attachments.map(x=>x.filename),...d.files.map(x=>x.name)].join('、');}});
    root().addEventListener('submit',async e=>{
      const f=e.target.closest('[data-feedback-submission]');if(!f)return;e.preventDefault();
      const id=Number(f.dataset.feedbackSubmission),d=draft(id),status=f.querySelector('[role=status]'),auth=localStorage.getItem('authToken');
      if(f.dataset.busy)return;f.dataset.busy='1';f.querySelector('button[type=submit]').disabled=true;
      try {
        if(d.attachment_ids.length+d.files.length>8)throw new Error('每版最多 8 个附件，请减少后再提交');
        for(const file of [...d.files]){
          status.textContent='上传 '+file.name+'…';const form=new FormData();form.append('file',file);
          const uploaded=await request('/feedback/attachments',{method:'POST',body:form});
          if(auth!==localStorage.getItem('authToken'))return;
          d.attachment_ids.push(uploaded.id);d.attachments.push(uploaded);d.files.shift();
        }
        status.textContent='保存成果…';
        const result=await post(`/feedback/occurrences/${id}/submissions`,{client_id:d.client_id,text:d.text,links:d.links.split('\n').map(x=>x.trim()).filter(Boolean),attachment_ids:d.attachment_ids,note:d.note});
        if(auth!==localStorage.getItem('authToken'))return;
        drafts.delete(id);replaceNode(result);root().querySelector(`[data-node="${id}"] .fb-card-status`).textContent='成果已保存；可在检查区域记录检查结果。';
      }catch(err){status.textContent=err.message+'；当前草稿保留。';status.classList.add('fb-error');}
      finally {delete f.dataset.busy;f.querySelector('button[type=submit]').disabled=false;}
    });
    root().addEventListener('click',async e=>{
      const b=e.target.closest('button');if(!b)return;const node=b.closest('[data-node]'),status=node?.querySelector('.fb-card-status')||root().querySelector('[data-pairing]');
      if(!b.matches('[data-review],[data-history],[data-skip],[data-restore],[data-download],[data-reader-pair],[data-reader-revoke],[data-reader-refresh],[data-retry-feedback],[data-deliveries],[data-more-backlog],[data-reader-check-pair],[data-reader-confirm-pair],[data-reader-sync]'))return;
      b.disabled=true;
      try {
        if(b.dataset.review){const note=node.querySelector('[data-review-note]').value.trim();if(!note)throw new Error('请先填写检查依据或需要补充的内容');replaceNode(await post(`/feedback/submissions/${b.dataset.submission}/review`,{status:b.dataset.review,note}));}
        else if(b.dataset.history){const data=await request('/feedback/occurrences/'+b.dataset.history);node.querySelector('[data-versions]').innerHTML=versions(data.versions)+eventHistory(data.events);b.remove();}
        else if(b.dataset.skip){const reason=node.querySelector('[data-skip-reason]').value.trim();if(!reason)throw new Error('请填写跳过原因');replaceNode(await post(`/feedback/occurrences/${b.dataset.skip}/skip`,{reason}));}
        else if(b.dataset.restore)replaceNode(await post(`/feedback/occurrences/${b.dataset.restore}/skip?restore=true`,{reason:'恢复本次交付节点'}));
        else if(b.dataset.download)await download(b.dataset.download,b.dataset.filename);
        else if(b.hasAttribute('data-reader-pair')){const data=await post('/integrations/reader/pairing',{});pairings.set(data.pairing_id,data);status.innerHTML=`<p>在已登录的知间账号里输入关联码，并核对书然账号：</p><strong class="fb-pair-code">${esc(data.code)}</strong><p>有效至 ${esc(stamp(data.expires_at))}。${esc(data.scope)}</p><button type="button" class="fb-secondary" data-reader-check-pair="${data.pairing_id}">已在知间确认，读取账号信息</button>`;}
        else if(b.dataset.readerCheckPair){const data=await request('/integrations/reader/pairings/'+b.dataset.readerCheckPair);if(!data.source_confirmed)throw new Error('知间账号尚未确认，请先在知间完成授权后再读取');pairings.set(data.pairing_id,data);status.innerHTML=`<p>书然账号：<strong>${esc(data.receiver_account_label)}</strong><br>知间账号：<strong>${esc(data.source_account_label)}</strong><br>授权起始日：${esc(data.authorized_from)} · ${data.private_titles?'使用私密书名':'使用授权展示名'}</p><p class="fb-hint">请确认这两个账号都是你想关联的账号。</p><button type="button" class="fb-primary" data-reader-confirm-pair="${data.pairing_id}">确认关联这两个账号</button>`;}
        else if(b.dataset.readerConfirmPair){const data=pairings.get(Number(b.dataset.readerConfirmPair));const linked=await post(`/integrations/reader/pairings/${data.pairing_id}/confirm`,{expected_source_instance_id:data.source_instance_id,expected_source_account_id:data.source_account_id});status.textContent='两个账号已关联，服务器将每 5 分钟自动同步。正在首次读取…';await post(`/integrations/reader/bindings/${linked.binding_id}/sync`,{});await readerStatus();status.textContent='首次同步已完成。重新读取当天记录后可核对逐书明细；未保存草稿会继续保留。';}
        else if(b.dataset.readerSync){status.textContent='正在从知间读取…';const result=await post(`/integrations/reader/bindings/${b.dataset.readerSync}/sync`,{});await readerStatus();status.textContent=result.complete?'同步完成。重新读取当天记录，可核对最新逐书明细。':'本批已保存，服务器会继续追赶历史；现有记录保留。';}
        else if(b.dataset.readerRevoke){if(confirm('在书然停止同步并清除读取凭证，已同步明细继续保留。知间中的授权也可以在其关联页面撤销。确认解除？')){await request('/integrations/reader/bindings/'+b.dataset.readerRevoke,{method:'DELETE'});await readerStatus();}}
        else if(b.hasAttribute('data-reader-refresh'))await readerStatus();
        else if(b.hasAttribute('data-deliveries')){const data=await request('/feedback/deliveries'),names={pending:'待发送',retry:'等待重试',sent:'已发送',failed:'发送失败',disabled:'未开启邮件',cancelled:'已停止'};root().querySelector('[data-deliveries-list]').innerHTML=data.items.map(d=>`<p><strong>${esc(d.title)}</strong> · ${names[d.email_status]||esc(d.email_status)} · 尝试 ${d.attempts} 次${d.last_error?'<br>'+esc(d.last_error):''}</p>`).join('')||'<p class="fb-hint">暂无发送记录。</p>';}
        else if(b.hasAttribute('data-more-backlog')){const data=await request(`/feedback/backlog?before=${currentDate}&offset=${backlogLoaded}`);b.insertAdjacentHTML('beforebegin',data.items.map(n=>card(n)).join(''));backlogLoaded+=data.items.length;if(backlogLoaded>=data.total)b.remove();}
        else await load(currentDate);
      }catch(err){if(status){status.textContent=err.message;if(b.dataset.readerCheckPair)status.insertAdjacentHTML('beforeend',`<button type="button" class="fb-secondary" data-reader-check-pair="${b.dataset.readerCheckPair}">重新读取账号信息</button>`);}if(b.dataset.readerConfirmPair||b.dataset.readerSync)await readerStatus().catch(()=>{});}
      finally {b.disabled=false;}
    });
  });
  window.addEventListener('auth-check-settled',()=>{if(token!==localStorage.getItem('authToken'))clear();});
  window.addEventListener('storage',e=>{if(e.key==='authToken')clear();});
  window.addEventListener('beforeunload',e=>{if(progressDrafts.size||[...drafts.values()].some(d=>d.text||d.links||d.note||d.files.length)){e.preventDefault();e.returnValue='';}});
  window.ShuranFeedbackDaily={load,request,clear};
})();
