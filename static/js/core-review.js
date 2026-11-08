(() => {
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const root=()=>document.getElementById('dailyCoreReview');
  let serial=0;
  async function request(path,method='GET',body){const response=await fetch(path,{method,headers:{Authorization:'Bearer '+localStorage.getItem('authToken'),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'保存失败');return value;}
  async function load(day) {
    if(!root()||!document.getElementById('daily-feedback')?.classList.contains('active'))return;
    const epoch=++serial;root().hidden=false;const items=document.getElementById('dailyCoreReviewItems');items.textContent='正在读取核心任务…';
    try{const data=await request(`/api/schedule?task_date=${encodeURIComponent(day)}`);if(epoch!==serial)return;
      const all=rows=>rows.flatMap(row=>[row,...all(row.children||[])]),tasks=all(data.tasks),core=tasks.filter(t=>t.core_selected);
      items.innerHTML=core.length?core.map(task=>`<article class="core-review-item" data-core-review="${task.id}"><h3>${esc(task.text)}</h3><label>今天是否完成？<select name="completed"><option value="" ${task.core_review_completed==null?'selected':''}>待核对</option><option value="yes" ${task.core_review_completed===true?'selected':''}>已完成</option><option value="no" ${task.core_review_completed===false?'selected':''}>未完成</option></select></label><label>相关原因 <small>选填</small><textarea name="reason" maxlength="4000" rows="2" placeholder="需要时再填写">${esc(task.core_review_reason||'')}</textarea></label><button type="button" data-save-core>保存这项回看</button><p role="status"></p></article>`).join(''):'<p>今天尚未选择核心任务。可回到日程，在写完任务后选择。</p>';
      document.getElementById('dailyExecutionFeedbackItems').innerHTML=tasks.length?tasks.map(task=>{const url=new URL('/static/content-editor.html',location.origin),back=new URL(location.href);back.searchParams.set('record',day);back.hash='daily-feedback';url.searchParams.set('type','feedback');url.searchParams.set('kind','daily');url.searchParams.set('id',task.id);url.searchParams.set('day',day);url.searchParams.set('return',back.href);return `<p><a href="${esc(url.href)}">${esc(task.text)} · 填写实际结果、进展与原因 →</a></p>`;}).join(''):'<p>这一天没有日程任务。</p>';
    }catch(error){if(epoch===serial)items.textContent=error.message;}
  }
  document.addEventListener('click',async event=>{const button=event.target.closest('[data-save-core]');if(!button)return;const row=button.closest('[data-core-review]'),state=row.querySelector('[role=status]'),value=row.querySelector('[name=completed]').value;button.disabled=true;try{await request(`/api/schedule/tasks/${row.dataset.coreReview}`,'PATCH',{core_review_completed:value===''?null:value==='yes',core_review_reason:row.querySelector('[name=reason]').value});state.textContent='已保存';}catch(error){state.textContent=error.message;}finally{button.disabled=false;}});
  window.ShuranCoreReview={load};
})();
