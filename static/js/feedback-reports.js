/* Data-shaped report views: distributions, calendars, milestones and small multiples. */
(() => {
  'use strict';
  const {esc}=ShuranFeedback;
  const labels={reading:'读书',fitness:'运动',friends:'帮朋友',family:'陪家人',investment:'定投',writing:'写作',work:'工作',relaxation:'放松'};
  const colors=['#56758b','#7c9374','#b58f68','#ab786b','#9b9369','#8285a2','#37566d','#9daa91'];
  const periods={day:'日报',week:'周报',month:'月报',quarter:'季度报',year:'年报'};
  const states={pending:'待提交',overdue:'已到期',submitted:'已提交',accepted:'检查通过',needs_changes:'待补充',skipped:'已跳过'};
  const time=s=>{const m=Math.round(s/60);return m>=60?Math.floor(m/60)+' 时 '+m%60+' 分':m+' 分';};
  function chart(points,color,title,currency=false) {
    const values=points.map(p=>p.value),known=values.filter(v=>v!==null),max=Math.max(1,...known),w=300,h=84,scale=currency?100:60;
    let segments=[],segment=[];
    points.forEach((p,i)=>{
      if(p.value===null){if(segment.length)segments.push(segment);segment=[];}
      else segment.push([16+i*268/Math.max(1,points.length-1),68-p.value/max*54,p]);
    });if(segment.length)segments.push(segment);
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(title)}，缺记处断开，最高已记录 ${Math.round(max/scale)} ${currency?'元':'分钟'}"><path d="M16 68H284" stroke="#d8dcd9" fill="none"/>${segments.map(s=>`<polyline points="${s.map(p=>p[0]+','+p[1]).join(' ')}" stroke="${color}" stroke-width="2.5" fill="none"/>${s.map(([x,y,p])=>`<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"><title>${esc(p.label)}：${currency?'¥ '+(p.value/100).toFixed(2):time(p.value)}</title></circle>`).join('')}`).join('')}${known.length?'':`<text x="150" y="43" text-anchor="middle" fill="#747e80" font-size="12">等待记录</text>`}</svg>`;
  }
  function evolution(r) {
    const e=r.evolution;if(!e)return '<section class="fb-report-section"><h3>变化与跨期趋势</h3><p class="fb-hint">深度趋势与跨期对比沿用现有月卡、学期卡权益。</p><button type="button" class="fb-text" data-upgrade>查看账户与套餐</button></section>';
    const comparisons=Object.entries(labels).map(([key,name],i)=>{
      const money=key==='investment',cur=money?e.current.investment_cents:e.current.total_seconds[key],prev=money?e.previous.investment_cents:e.previous.total_seconds[key];
      const known=x=>x.counts?.[key]||x.category_confirmed_days?.[key];
      const format=v=>money?'¥ '+(v/100).toFixed(2):time(v),max=Math.max(cur,prev,1);
      const series=rows=>rows.map(t=>({label:t.label,value:known(t)?(money?t.investment_cents:t.total_seconds[key]):null}));
      return `<article class="fb-trend-card" style="--fb-series:${colors[i]}"><div class="fb-heading"><h4>${name}</h4><strong>${known(e.current)?format(cur):'尚未记录'}</strong></div><div class="fb-compare-row"><span>本期</span><i style="width:${cur/max*100}%"></i><span>${known(e.current)?format(cur):'—'}</span></div><div class="fb-compare-row previous"><span>上期</span><i style="width:${prev/max*100}%"></i><span>${known(e.previous)?format(prev):'—'}</span></div><div data-trend-scope="inside">${chart(series(e.trend),colors[i],name+'本周期变化',money)}</div><div data-trend-scope="history" hidden>${chart(series(e.history||[]),colors[i],name+'跨周期变化',money)}</div></article>`;
    }).join('');
    return `<section class="fb-report-section"><div class="fb-heading"><h3>投入与变化</h3><div class="fb-segment" role="group" aria-label="趋势范围"><button type="button" data-trend="inside" aria-pressed="true">本周期</button><button type="button" data-trend="history" aria-pressed="false">最近六期</button></div></div><p class="fb-hint">对比相同的 ${e.comparison.days} 天：${e.comparison.start} — ${e.comparison.end||'尚未开始'} ／ ${e.comparison.previous_start} — ${e.comparison.previous_end||'—'}。已记录值可能尚未核对，缺记不画成零，时间与金额分开。</p><div class="fb-trends">${comparisons}</div><p class="fb-trend-axis" data-axis-inside>${e.trend[0]?.label||'—'} → ${e.trend.at(-1)?.label||'—'}</p><p class="fb-trend-axis" data-axis-history hidden>${e.history?.[0]?.label||'—'} → ${e.history?.at(-1)?.label||'—'}；各期展示已发生部分，完整度不同，需结合覆盖率查看。</p><details><summary>查看各期数据与完整度</summary><div class="fb-table-wrap"><table><thead><tr><th>周期开始</th><th>有记录／已过天数</th><th>已核对天数</th><th>已记录时间</th><th>定投</th></tr></thead><tbody>${(e.history||[]).map(p=>`<tr><td>${p.label}</td><td>${p.recorded_days}／${p.elapsed_days}</td><td>${p.day_confirmed_days}</td><td>${p.recorded_days?time(Object.values(p.total_seconds).reduce((a,b)=>a+b,0)):'未记录'}</td><td>${p.recorded_days?'¥ '+(p.investment_cents/100).toFixed(2):'未记录'}</td></tr>`).join('')}</tbody></table></div></details></section>`;
  }
  function books(r) {
    const items=[...(r.books||[])].sort((a,b)=>b.seconds-a.seconds),max=Math.max(1,...items.map(b=>b.seconds));
    return `<section class="fb-report-section"><h3>每本书的阅读投入</h3>${items.map(b=>`<details class="fb-book"><summary><span>${esc(b.title)}<small>${esc(b.source?.label||'手动补记')} · ${b.dates.length} 天</small></span><span class="fb-book-track"><i style="width:${b.seconds/max*100}%"></i></span><strong>${time(b.seconds)}</strong></summary><p class="fb-hint">${b.source?'来源：'+esc(b.source.instance_id)+' · 书籍 '+esc(b.source.book_id):'手动补记按书名汇总；同名书的同步来源保持独立。'}</p><div class="fb-date-links">${b.dates.map(d=>`<button type="button" data-day="${d}">${d}</button>`).join('')}</div></details>`).join('')||'<p class="fb-empty">本周期尚无逐书阅读记录。可手动填写书名，或关联知间接收逐日明细。</p>'}</section>`;
  }
  function projects(r) {
    const nodes=(r.projects||[]).flatMap(p=>p.occurrences),due=nodes.filter(n=>n.status!=='skipped'),submitted=due.filter(n=>n.latest),accepted=due.filter(n=>n.status==='accepted');
    const title=r.period==='year'?'全年项目成果目录':r.period==='quarter'?'阶段推进与里程碑':'项目推进';
    const nodeHTML=n=>`<a class="fb-node-chip ${n.status}" href="/static/index.html?feedback=${n.id}&record=${n.due_date}#long-term" title="${esc(n.project_title+'：'+n.requirement.deliverable)}"><span>${n.due_date.slice(5)}</span>${states[n.status]}${n.late?' · 迟交':''}</a>`;
    return `<section class="fb-report-section"><div class="fb-heading"><h3>${title}</h3><span>到期 ${due.length} · 已提交 ${submitted.length} · 检查通过 ${accepted.length} · 迟交 ${nodes.filter(n=>n.late).length}</span></div>${(r.projects||[]).map(p=>`<article class="fb-project-report"><div class="fb-heading"><a href="/static/projects.html?project=${p.id}"><strong>${esc(p.title)}</strong> ↗</a><span>${time(p.actual_seconds)} · ${p.intervals.length} 个投入区间</span></div><p class="fb-hint">${p.current_stages.length?'当前阶段：'+esc(p.current_stages.join('、')):'按整个项目推进'} · 本期完成任务 ${p.completed_tasks.length} 项</p>${p.completed_tasks.map(t=>`<p>✓ ${esc(t.title)}${t.result?'：'+esc(t.result):''}</p>`).join('')}${p.milestones.length?`<ol class="fb-milestones">${p.milestones.map(m=>`<li><time>${m.date.slice(0,10)}</time><strong>${esc(m.title)}</strong><p>${esc(m.reason||'阶段已结束')}</p></li>`).join('')}</ol>`:''}<div class="fb-node-chips">${p.occurrences.map(nodeHTML).join('')}</div>${r.period==='year'?`<details><summary>查看已检查成果与来源</summary>${p.occurrences.filter(n=>n.status==='accepted').map(n=>`<p><a href="/static/index.html?feedback=${n.id}&record=${n.due_date}#long-term">${n.due_date} · ${esc(n.requirement.deliverable)}</a><small>${esc(n.latest.review_note||'检查通过')}</small></p>`).join('')||'<p>尚无本期检查通过的成果。</p>'}</details>`:''}<details><summary>原始投入区间</summary>${p.intervals.map(s=>`<p><button type="button" class="fb-text" data-day="${s.date}">${s.date}</button> · ${esc(s.title)} · ${time(s.seconds)}</p>`).join('')||'<p>尚无已记录区间，不视为没有投入。</p>'}</details></article>`).join('')||'<p class="fb-empty">本期尚无项目投入、到期节点或完成记录。</p>'}<p class="fb-hint">项目区间与长期方向活动可能引用同一段时间，分别呈现，不相加为总投入。</p></section>`;
  }
  function coverage(r) {
    const days=r.days||[],first=days.length?(new Date(days[0].date+'T12:00:00Z').getUTCDay()+6)%7:0;
    return `<section class="fb-report-section"><div class="fb-heading"><h3>${r.period==='week'?'这一周的记录足迹':'记录完整度'}</h3><span>活动核对 ${r.day_confirmed_days}／${r.elapsed_days} 天</span></div><div class="fb-coverage-grid"><div class="fb-week-head">${['一','二','三','四','五','六','日'].map(d=>`<span>${d}</span>`).join('')}</div><div class="fb-coverage-days">${Array.from({length:first},()=>'<span></span>').join('')}${days.map(d=>`<button type="button" data-day="${d.date}" class="${d.day_confirmed?'confirmed':d.recorded?'partial':'missing'}" title="${d.date} · ${d.day_confirmed?'活动已核对':d.recorded?'有记录，待核对':'缺记'}"><span>${r.period==='month'?Number(d.date.slice(8)):d.date.slice(5).replace('-','/')}</span><small>${d.day_confirmed?'已核对':d.recorded?'待核对':'缺记'}</small></button>`).join('')}</div></div><p class="fb-hint">深蓝：活动已核对；浅蓝：有记录待核对；灰色：缺记。点击日期可补充，未来日期不计入完整度。</p></section>`;
  }
  function render(r,root) {
    root.querySelector('[data-feedback-report]')?.remove();
    const section=document.createElement('div');section.dataset.feedbackReport='';section.className='fb-report';
    section.innerHTML=`<div class="fb-report-intro"><p class="fb-eyebrow">回看投入，也看发生的变化</p><h2>${periods[r.period]} · ${r.start} — ${r.effective_end||r.end}</h2><p>当前版本 ${r.snapshot?.revision||1} · 补记后自动更新，历史版本保留。</p><button type="button" class="fb-text" data-report-versions>查看报告版本</button><div data-report-history></div></div>${projects(r)}${r.period==='day'?books(r)+evolution(r):r.period==='month'?coverage(r)+evolution(r)+books(r):r.period==='week'?evolution(r)+coverage(r)+books(r):evolution(r)+books(r)+coverage(r)}`;
    section.querySelectorAll('.fb-project-report').forEach((node,i)=>{
      const p=r.projects[i],names={preparation:'筹备',started:'开始／重新开始',delivered:'项目交付',accepted:'项目验收通过'};
      if(p.transitions?.length)node.insertAdjacentHTML('beforeend',`<ol class="fb-milestones">${p.transitions.map(t=>`<li><time>${new Date(t.date).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'})}</time><strong>${names[t.state]||esc(t.state)}</strong><p>${esc(t.reason)}</p></li>`).join('')}</ol>`);
      if(p.updates?.length)node.insertAdjacentHTML('beforeend',`<details open><summary>推进、卡点与下一步</summary>${p.updates.map(u=>`<p><button type="button" class="fb-text" data-day="${u.date}">${u.date}</button> · ${esc(u.title)}<br>推进：${esc(u.advanced||'待反馈')}<br>卡点：${esc(u.blocker||'未填写')}<br>下一步：${esc(u.next_step||'未填写')}</p>`).join('')}</details>`);
    });
    section.querySelectorAll('.fb-trend-card').forEach((node,i)=>{const key=Object.keys(labels)[i];node.insertAdjacentHTML('beforeend',`<small class="fb-hint">本期核对 ${r.evolution.current.category_confirmed_days?.[key]||0} 天 · 上期 ${r.evolution.previous.category_confirmed_days?.[key]||0} 天</small>`);});
    root.prepend(section);
    section.addEventListener('click',async e=>{
      const b=e.target.closest('button');if(!b)return;
      if(b.dataset.trend){section.querySelectorAll('[data-trend-scope]').forEach(el=>el.hidden=el.dataset.trendScope!==b.dataset.trend);section.querySelectorAll('[data-trend]').forEach(el=>el.setAttribute('aria-pressed',String(el===b)));section.querySelector('[data-axis-inside]').hidden=b.dataset.trend!=='inside';section.querySelector('[data-axis-history]').hidden=b.dataset.trend!=='history';}
      if(b.hasAttribute('data-report-versions')){
        const list=section.querySelector('[data-report-history]');b.disabled=true;
        try {const data=await ShuranFeedbackDaily.request(`/feedback/reports?period=${r.period}&anchor=${r.start}`);list.innerHTML=data.items.map(v=>`<button type="button" class="fb-text" data-report-version="${v.id}">版本 ${v.revision} · ${new Date(v.generated_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</button>`).join('');}
        catch(err){list.textContent=err.message;}finally{b.disabled=false;}
      }
      if(b.dataset.reportVersion){
        const list=section.querySelector('[data-report-history]');
        try {const data=await ShuranFeedbackDaily.request('/feedback/reports/'+b.dataset.reportVersion);const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=`书然-${periods[r.period]}-${r.start}-版本${data.revision}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
        catch(err){list.textContent=err.message;}
      }
    });
    if(r.period==='day')section.querySelector('[data-trend=history]')?.click();
  }
  window.ShuranFeedbackReports={render};
})();
