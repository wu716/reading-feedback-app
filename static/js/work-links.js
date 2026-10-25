/* Work sessions, moments and goals share a source; forms never infer a time gap. */
(function () {
    'use strict';
    const base = '/api/long-term/details/work-links';
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const request = (path, options) => apiRequest(base + path, options);
    const categories = {work:'工作',reading:'读书',writing:'写作',fitness:'运动',friends:'帮朋友',family:'陪家人',relaxation:'放松'};
    const local = value => {
        // Legacy moment timestamps without offsets are Beijing wall-clock values.
        if(typeof value==='string' && !/(Z|[+-]\d\d:\d\d)$/i.test(value))return value.slice(0,19);
        const date = new Date(value);
        if (!Number.isFinite(date.getTime())) return '';
        return new Date(date.getTime() + 8 * 3600000).toISOString().slice(0,19);
    };
    const utc = value => new Date(value + '+08:00').toISOString();
    const field = (label,name,value,type='text') => `<label class="lt-field"><span>${label}</span><input name="${name}" type="${type}" value="${esc(value)}" ${type==='datetime-local'?'step="1"':''} required></label>`;
    const error = e => { if (typeof showMessage === 'function') showMessage(e.message || '操作失败，请重试','error'); };
    function form(title, body, submit) {
        document.getElementById('workLinkDialog')?.remove();
        const previous = document.activeElement;
        const dialog = document.createElement('dialog');
        dialog.id = 'workLinkDialog';
        dialog.setAttribute('aria-labelledby','workLinkTitle');
        dialog.innerHTML = `<form><h2 id="workLinkTitle">${title}</h2><div class="lt-form-grid">${body}</div><p role="alert" class="work-link-error"></p><div class="lt-entry-actions"><button type="submit" class="flow-solid-btn">保存</button><button type="button" class="flow-ghost-btn" data-close>取消</button></div></form>`;
        const close = () => { dialog.close(); dialog.remove(); previous?.focus(); };
        dialog.querySelector('[data-close]').onclick = close;
        dialog.addEventListener('cancel', e => {e.preventDefault();close();});
        dialog.querySelector('form').onsubmit = async e => {
            e.preventDefault();
            const button = dialog.querySelector('[type=submit]'); button.disabled = true;
            try { await submit(new FormData(e.target)); close(); }
            catch (e) { dialog.querySelector('[role=alert]').textContent = e.message || '保存失败，输入内容已保留。'; }
            finally { button.disabled = false; }
        };
        document.body.appendChild(dialog); dialog.showModal();
    }
    async function correct(id, after) {
        try {
            const data = await request('/'+id);
            if (!data.ended_at) throw new Error('请先暂停或结束工作片，再更正区间。');
            form('更正原工作片', field('开始时间（北京时间）','start',local(data.started_at),'datetime-local') +
                field('结束时间（北京时间）','end',local(data.ended_at),'datetime-local') +
                field('更正原因','reason',data.correction_note) +
                '<p class="lt-note lt-full">这会同步更正时刻和任务实耗；长期目标已手动调整的时长保留，并提示核对。</p>', async f => {
                await request('/'+id+'/interval',{method:'PATCH',body:JSON.stringify({started_at:utc(f.get('start')),ended_at:utc(f.get('end')),correction_note:f.get('reason')})});
                await after?.();
            });
        } catch(e) {error(e);}
    }
    function note(row, after) {
        if(!row) return;
        form('补充时刻记录', '<label class="lt-field lt-full"><span>感受与补充说明</span><textarea name="note" rows="4" maxlength="3000">'+esc(row.work_source.note)+'</textarea></label><p class="lt-note">补充文字不改变工作时长。</p>', async f=>{
            await request('/'+row.work_session_id+'/note',{method:'PUT',body:JSON.stringify({note:f.get('note')})}); await after?.();
        });
    }
    async function confirmMoment(node, day, tasks, linkOnly, after) {
        if(!node) return;
        try {
            const sources = await request('?day='+day);
            const all = [...sources.items,...sources.history];
            if(linkOnly && !all.length) throw new Error('当天还没有工作片，可先确认实际活动区间。');
            const body = linkOnly ? '<label class="lt-field lt-full"><span>关联已有工作片（不追加时长）</span><select name="session_id">'+all.map(r=>`<option value="${r.work_session_id}">${esc(r.title)} · ${Math.round(r.seconds/60)}分钟</option>`).join('')+'</select></label>' :
                field('实际开始时间（北京时间）','start',local(node.logged_at),'datetime-local') +
                field('实际结束时间（请核对）','end','','datetime-local') +
                '<label class="lt-field"><span>计入方向</span><select name="category">'+Object.entries(categories).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')+'</select></label>' +
                '<label class="lt-field"><span>关联当天任务（选填）</span><select name="task"><option value="">不关联任务</option>'+tasks.map(t=>`<option value="${t.id}">${esc(t.text||t.title)}</option>`).join('')+'</select></label>';
            form(linkOnly?'将时刻关联到已有工作片':'确认实际活动区间',body+'<p class="lt-note lt-full">只统计你明确确认的实际区间。已关联的时刻不再累计其原相邻间隔；重叠区间会提示调整。</p>',async f=>{
                const payload = linkOnly ? {node_id:node.id,session_id:Number(f.get('session_id'))} : {node_id:node.id,started_at:utc(f.get('start')),ended_at:utc(f.get('end')),category:f.get('category'),daily_task_id:f.get('task')?Number(f.get('task')):null};
                await request('/confirm',{method:'POST',body:JSON.stringify(payload)}); await after?.();
            });
        } catch(e) {error(e);}
    }
    async function history(day, after) {
        const parent = document.getElementById('ltManual'); if(!parent) return;
        let region = document.getElementById('workLinkHistory');
        if(!region){region=document.createElement('details');region.id='workLinkHistory';region.className='lt-activity';parent.after(region);}
        const token=localStorage.getItem('authToken');
        try {
            const data=await request('?day='+day);
            if(token!==localStorage.getItem('authToken')||document.getElementById('ltDate')?.value!==day)return;
            region.innerHTML='<summary>历史工作片核对与导入（'+data.history.length+'）</summary><p class="lt-note">导入前请与已有手动记录核对。导入后，可将重复的手动记录标为同一段活动，时长只计一次。</p>'+data.history.filter(r=>!r.work_source.running).map(r=>`<div class="lt-entry-body"><strong>${esc(r.title)}</strong> · ${Math.round(r.seconds/60)}分钟<button type="button" class="lt-text-button" data-import-work="${r.work_session_id}">已核对，导入工作片</button></div>`).join('');
            region.onclick=async e=>{const button=e.target.closest('[data-import-work]');if(!button)return;if(document.getElementById('ltStatus')?.classList.contains('is-dirty')){error(new Error('请先保存当前修改，再核对导入历史工作片。'));return;}button.disabled=true;try{await request('/'+button.dataset.importWork+'/import',{method:'POST'});await after?.();}catch(err){error(err);button.disabled=false;}};
        }catch(e){region.innerHTML='<summary>历史工作片核对</summary><p class="lt-note">读取失败，请重新读取当天记录后重试。</p>';}
    }
    async function refreshCapture() {
        const capture=document.getElementById('capture');
        if(!capture?.classList.contains('active'))return;
        const card=capture.querySelector('.capture-entry-grid > .card');
        if(!card)return;
        let preview=document.getElementById('workCapturePreview');
        if(!preview){preview=document.createElement('div');preview.id='workCapturePreview';card.appendChild(preview);}
        const token=localStorage.getItem('authToken');
        if(!token){preview.replaceChildren();return;}
        const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
        try {
            const data=await request('?day='+today);
            if(token!==localStorage.getItem('authToken'))return;
            preview.innerHTML=data.items.slice(-3).map(r=>`<div class="work-capture-entry"><strong>${esc(r.title)}</strong><p>${local(r.work_source.started_at).slice(11,16)}—${r.work_source.running?'计时中':local(r.work_source.ended_at).slice(11,16)} · ${r.work_source.running?'结束后结算':Math.round(r.seconds/60)+'分钟'}</p><span class="lt-note">工作片关联</span><button type="button" class="flow-mini-btn" data-preview-note="${r.work_session_id}">补充记录</button></div>`).join('');
            preview.onclick=e=>{const id=Number(e.target.dataset.previewNote);if(id)note(data.items.find(r=>r.work_session_id===id),refreshCapture);};
        }catch(e){preview.textContent='关联工作片暂未读取成功，请稍后回看时刻。';}
    }
    function observeCapture(){
        const capture=document.getElementById('capture');
        if(capture)new MutationObserver(refreshCapture).observe(capture,{attributes:true,attributeFilter:['class']});
        refreshCapture();
        setInterval(()=>{
            if(document.hidden)return;
            refreshCapture();
            if(document.getElementById('time-log')?.classList.contains('active')&&!document.getElementById('timeLogSheet')&&!document.getElementById('workLinkDialog'))window.loadTimeLog?.();
        },30000);
    }
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',observeCapture,{once:true});else observeCapture();
    window.ShuranWorkLinks = {correct,note,confirm:confirmMoment,history};
})();
