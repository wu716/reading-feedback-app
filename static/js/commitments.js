/* The current-stage writing surface. Drafts stay on the server; versions stay immutable. */
(() => {
  'use strict';
  const drafts = new Map();
  const expandedStages = new Set();
  let mountNumber=0;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const stamp = value => value ? new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value+'Z').toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}) : '未记录';
  async function api(path, body, method='GET') {
    const response = await fetch('/api/projects/commitments'+path, {method,
      headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),'Content-Type':'application/json'},
      body:body===undefined?undefined:JSON.stringify(body)});
    const result = await response.json().catch(()=>({}));
    if (!response.ok) { const error=new Error(typeof result.detail==='string'?result.detail:result.detail?.message||'读取承诺失败，请稍后重试'); error.status=response.status; throw error; }
    return result;
  }
  function taskList(tasks) {
    return tasks.map(task=>`<p><strong>${esc(task.title)}</strong><span>预计 ${task.estimate??'未填'} 分钟 · 怎样算完成：${esc(task.criteria||'未填写')}</span></p>`).join('') || '<p>本阶段未拆分任务，仍可围绕项目预期结果填写承诺。</p>';
  }
  function history(data) {
    return `<details class="commitment-history"><summary>承诺与调整历史（${data.history.length} 个版本）</summary>${data.history.map(version=>{
      const adjustment=data.adjustments.find(item=>item.confirmed&&item.result.commitment_id===version.id);
      return `<details><summary>承诺版本 ${version.version} · ${esc(stamp(version.at))}${version.stage_deleted?` · 原阶段已删除（${esc(version.stage_title||'阶段')}）`:''}</summary><p class="commitment-statement">${esc(version.snapshot.statement||'未填写承诺文字（历史版本）')}</p><p>当时交付：${esc(version.snapshot.outcome||'未填写')}</p><div class="commitment-scope">${taskList(version.snapshot.tasks)}</div>${adjustment?`<p>调整原因：${esc(adjustment.reason)}</p>${adjustment.impact.unfinished.map(task=>`<p>${esc(task.title)}：${({retain:'保留推进',defer:'延期到下一阶段',cancel:'取消，仍未完成'})[task.action]}</p>`).join('')}`:''}</details>`;
    }).join('')||'<p>确认后，在这里保留当时的文字与任务范围。</p>'}${data.adjustments.filter(item=>item.invalidated).map(item=>`<p>未确认的调整方案已失效 · 原阶段：${esc(item.stage_title||'已删除阶段')} · 原因：阶段已删除。原方案记录仍保留。</p>`).join('')}</details>`;
  }
  async function mount(root, projectId, options={}) {
    if (!root) return;
    const bodyId=`commitment-body-${++mountNumber}`;
    let data, editor, busy=false, conflict=false;
    const message=(text,error=false)=>{const node=root.querySelector('[data-commitment-message]');if(node){node.textContent=text;node.classList.toggle('is-error',error);}};
    function render() {
      if (!data.current_stage_id) {root.innerHTML='<p class="practice-note">项目暂时没有当前阶段。</p>';return;}
      const confirmed=data.commitment?.snapshot.statement;
      const expanded=expandedStages.has(data.current_stage_id);
      const summary=confirmed || editor.text || '还没有写下承诺；可随时在这里填写';
      const entry=confirmed?'查看 / 调整':editor.text?'继续填写':'写下承诺';
      const scope=confirmed?data.commitment.snapshot:data.scope;
      const minutes=scope.tasks.reduce((sum,task)=>sum+(task.estimate||0),0), missing=scope.tasks.filter(task=>task.estimate==null).length;
      root.innerHTML=`<section class="commitment-panel ${expanded?'is-expanded':'is-collapsed'}" aria-label="本轮承诺"><div class="commitment-heading"><div><h3>本轮承诺 <span class="commitment-state">${confirmed?'已确认 · 版本 '+data.commitment.version:data.draft?'草稿已保存':editor.dirty?'未保存的输入':'待填写'}</span></h3><p class="commitment-summary">${esc(summary)}</p></div><button type="button" data-commitment-toggle aria-expanded="${expanded}" aria-controls="${bodyId}">${expanded?'收起':entry}</button></div><div id="${bodyId}" class="commitment-body" ${expanded?'':'hidden'}><p class="commitment-hint">先完成这一轮确定的工作，后续想法放入下一阶段。</p>`+
        (confirmed?`<p class="commitment-statement">${esc(confirmed)}</p><p class="commitment-hint">承诺文字、任务范围与完成标准已随版本保留。</p><button type="button" data-commitment-adjust>调整当前承诺</button>`:
          `<form data-commitment-form><label>写下你对这一轮的承诺<textarea name="statement" rows="4" maxlength="2000" placeholder="例如：这一轮先整理5篇文献并完成提纲，新想到的主题先放入下一阶段。">${esc(editor.text)}</textarea></label>${data.commitment?'<p class="commitment-hint">原任务范围版本保留；确认本次文字会另存新版本，不改写历史。</p>':''}<p class="commitment-hint">${data.draft?'草稿保存于 '+esc(stamp(data.draft.updated_at)):'草稿尚未保存；保存草稿不会正式确认。'}</p><div class="commitment-actions"><button type="submit" name="decision" value="draft" class="secondary">保存草稿</button><button type="submit" name="decision" value="confirm" class="commitment-primary">确认本轮承诺</button></div></form>`)+
        `<p class="commitment-message" data-commitment-message role="status" aria-live="polite"></p>${conflict?'<button type="button" data-commitment-reload>读取服务器草稿</button>':''}<details class="commitment-scope"><summary>本轮任务范围 · ${scope.tasks.length} 项 · 已填预计 ${minutes} 分钟${missing?' · '+missing+' 项未估时':''}</summary><p>预期结果：${esc(scope.outcome||'未填写')}</p>${taskList(scope.tasks)}</details><p class="commitment-hint">正常切换任务、暂停和休息不需要调整承诺。</p></div></section>`+
        (options.history===false?'':history(data));
      root.querySelector('[data-commitment-toggle]')?.addEventListener('click',()=>{expanded?expandedStages.delete(data.current_stage_id):expandedStages.add(data.current_stage_id);render();if(!expanded)root.querySelector('[name=statement]')?.focus();});
      root.querySelector('[name=statement]')?.addEventListener('input',event=>{editor.text=event.target.value;editor.dirty=true;});
      root.querySelector('[data-commitment-adjust]')?.addEventListener('click',()=>options.onAdjust?options.onAdjust():globalThis.ShuranPractice?.openProject(projectId,'commitment'));
      root.querySelector('[data-commitment-reload]')?.addEventListener('click',async()=>{drafts.delete(data.current_stage_id);conflict=false;await load();});
      root.querySelector('[data-commitment-form]')?.addEventListener('submit',async event=>{
        event.preventDefault();if(busy)return;
        const statement=event.target.elements.statement.value;
        const confirming=event.submitter?.value==='confirm';
        if(confirming&&!statement.trim()){message('请先写下这一轮的承诺，再确认。',true);event.target.elements.statement.focus();return;}
        busy=true;root.querySelectorAll('button,textarea').forEach(node=>node.disabled=true);
        try {
          if(confirming)await api(`/stages/${data.current_stage_id}/start`,{statement,draft_revision:editor.revision,base_commitment_id:data.commitment?.id??null},'POST');
          else await api(`/stages/${data.current_stage_id}/draft`,{statement,revision:editor.revision},'PUT');
          drafts.delete(data.current_stage_id);await load();
          message(confirming?'本轮承诺已确认，文字与任务范围已保留。':'草稿已保存，尚未正式确认。');
          if(options.onChanged)await options.onChanged();
        } catch(error) {
          conflict=error.status===409;render();message(error.message+(conflict?'。你的输入仍保留，可先复制；需要采用服务器草稿时再点击读取。':''),true);
        } finally {busy=false;root.querySelectorAll('button,textarea').forEach(node=>node.disabled=false);}
      });
    }
    async function load() {
      try {
        data=await api(`/projects/${projectId}`);
        if(root.isConnected===false)return;
        editor=drafts.get(data.current_stage_id);
        if(!editor||!editor.dirty){editor={text:data.draft?.statement||'',revision:data.draft?.revision||0,dirty:false};drafts.set(data.current_stage_id,editor);}
        render();
      } catch(error) {root.innerHTML='<p class="commitment-message is-error" role="alert"></p>';root.firstElementChild.textContent=error.message;}
    }
    root.innerHTML='<p class="practice-note">正在读取本轮承诺…</p>';
    await load();
  }
  globalThis.ShuranCommitments={mount};
})();
