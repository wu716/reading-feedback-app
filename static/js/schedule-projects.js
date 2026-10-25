/** A stage is edited in a daily draft; saving never rewrites its original tasks. */
(() => {
    'use strict';
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const key = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const state = {day:null, token:null, projects:[], projectId:null, stageId:null, draft:null, drafts:new Map(), generation:0, open:false, busy:false};
    let panel;
    const $ = selector => panel?.querySelector(selector);
    const api = (path, options) => apiRequest('/api/schedule/project-stages' + path, options || {});
    const sameContext = (generation, token, day) => generation === state.generation && token === localStorage.getItem('authToken') && day === state.day;
    const draftKey = () => `${state.day}:${state.stageId}`;
    const stageName = stage => ({current:'当前阶段', next:'下一阶段', closed:'已结束'})[stage.state] || '阶段';

    function status(text, error = false) {
        const node = $('#stageScheduleStatus');
        if (node) { node.textContent = text; node.setAttribute('role', error ? 'alert' : 'status'); }
    }
    function mount() {
        if (panel) return;
        const composer = document.getElementById('scheduleAddRow');
        if (!composer) return;
        panel = document.createElement('section'); panel.id = 'scheduleStagePanel'; panel.className = 'schedule-stage-panel'; panel.hidden = true;
        panel.setAttribute('aria-label', '从项目阶段安排日程');
        panel.innerHTML = `<div class="schedule-stage-head"><h2>把阶段安排到这一天</h2><button type="button" data-stage-act="cancel">取消本次安排</button></div>
            <div class="schedule-stage-pickers"><label>项目<select id="stageScheduleProject" aria-label="选择项目"></select></label><label>阶段<select id="stageScheduleStage" aria-label="选择项目阶段"></select></label></div>
            <div id="stageScheduleContext" class="schedule-stage-context"></div><div id="stageScheduleDraft"></div>
            <p id="stageScheduleStatus" role="status" aria-live="polite"></p>
            <div class="schedule-stage-save"><div><span id="stageScheduleTotal"></span><small>当天内容、用时和完成单独保存；保留项目关联</small></div><button type="button" class="schedule-stage-primary" data-stage-act="save">保存到这一天</button></div>`;
        composer.after(panel);
        panel.addEventListener('click', onClick);
        panel.addEventListener('input', onInput);
        $('#stageScheduleProject').addEventListener('change', event => {
            state.projectId = Number(event.target.value); state.stageId = null; selectProject().catch(fail);
        });
        $('#stageScheduleStage').addEventListener('change', event => {
            state.stageId = Number(event.target.value); loadStage().catch(fail);
        });
    }
    function setOpen(open) {
        state.open = open; if (panel) panel.hidden = !open;
        document.getElementById('scheduleProjectEntry')?.setAttribute('aria-expanded', String(open));
    }
    function fail(error) { status(error.message || '加载失败，请重试', true); }
    function reset() {
        state.generation++; state.projects = []; state.projectId = null; state.stageId = null;
        state.draft = null; state.drafts.clear(); state.busy = false; setOpen(false);
        if (panel) { $('#stageScheduleDraft').replaceChildren(); $('#stageScheduleContext').replaceChildren(); $('#stageScheduleProject').replaceChildren(); $('#stageScheduleStage').replaceChildren(); status(''); }
    }
    function sync(day, tasks, mode) {
        mount();
        const token = localStorage.getItem('authToken');
        if (state.token !== token || state.day !== day) { reset(); state.token = token; state.day = day; }
        if (mode === 'sort') setOpen(false);
        if (state.draft) {
            const ids = new Set();
            const visit = rows => (rows || []).forEach(task => { if (task.project_task_id) ids.add(task.project_task_id); visit(task.children); });
            visit(tasks); state.draft.items.forEach(item => { item.scheduled = ids.has(item.project_task_id); });
            if (state.open) renderDraft();
        }
    }
    async function toggle() {
        mount(); if (!panel) return;
        if (state.open) { setOpen(false); return; }
        if (!localStorage.getItem('authToken')) { if (typeof showMessage === 'function') showMessage('请先登录', 'error'); return; }
        setOpen(true); status('正在读取项目阶段…');
        const generation = ++state.generation, token = state.token, day = state.day;
        try {
            const result = await api('');
            if (!sameContext(generation, token, day) || !state.open) return;
            state.projects = result.projects;
            if (!state.projects.length) {
                $('#stageScheduleProject').innerHTML = '<option value="">暂无可安排项目</option>';
                $('#stageScheduleStage').innerHTML = '<option value="">暂无阶段</option>';
                state.draft = null; renderDraft(); status('可以先到“项目”创建项目与阶段，再从这里安排。'); return;
            }
            if (!state.projects.some(p => p.id === state.projectId)) state.projectId = state.projects[0].id;
            $('#stageScheduleProject').innerHTML = state.projects.map(p => `<option value="${p.id}" ${p.id === state.projectId ? 'selected' : ''}>${escape(p.title)}</option>`).join('');
            await selectProject(); $('#stageScheduleProject').focus();
        } catch (error) { if (sameContext(generation, token, day)) fail(error); }
    }
    async function selectProject() {
        const project = state.projects.find(p => p.id === state.projectId);
        if (!project) return;
        if (!project.stages.some(s => s.id === state.stageId)) state.stageId = (project.stages.find(s => s.state === 'current') || project.stages[0])?.id;
        $('#stageScheduleStage').innerHTML = project.stages.map(s => `<option value="${s.id}" ${s.id === state.stageId ? 'selected' : ''}>${escape(s.title)} · ${stageName(s)}</option>`).join('');
        await loadStage();
    }
    function freshItem() {
        return {item_key:key(), project_task_id:null, title:'新增阶段任务', text:'', estimated_minutes:null,
            familiarity:null, difficulty:null, importance:null, active:true, scheduled:false, readiness:null};
    }
    async function loadStage() {
        const generation = ++state.generation, token = state.token, day = state.day, stageId = state.stageId;
        state.draft = null; renderDraft(); status('正在调入阶段草稿…');
        const cached = state.drafts.get(draftKey());
        if (cached) { state.draft = cached; renderDraft(); status(''); return; }
        try {
            const preview = await api(`/${stageId}?task_date=${encodeURIComponent(day)}`);
            if (!sameContext(generation, token, day) || stageId !== state.stageId) return;
            state.draft = {...preview, request_key:key(), items:preview.tasks.map(task => ({
                item_key:key(), project_task_id:task.id, title:task.title, text:task.title,
                estimated_minutes:task.estimated_minutes, source_estimate:task.estimated_minutes,
                familiarity:task.familiarity, difficulty:task.practice?.difficulty || null, importance:task.practice?.importance || null,
                active:task.readiness?.can_start !== false, scheduled:!!task.scheduled_daily_id, readiness:task.readiness,
                previous_progress:task.previous_progress,
            }))};
            if (!preview.has_tasks) state.draft.items.push(freshItem());
            state.drafts.set(draftKey(), state.draft); renderDraft(); status('');
        } catch (error) { if (sameContext(generation, token, day)) { state.draft = null; renderDraft(); fail(error); } }
    }
    function attrs(item) {
        const options = [['familiarity','熟悉度',[['familiar','熟悉'],['unfamiliar','陌生']]],['difficulty','难度',[['simple','简单'],['difficult','困难']]],['importance','重要性',[['unimportant','不重要'],['ordinary','一般'],['important','重要']]]];
        return options.map(([field,label,choices]) => `<div class="flow-attribute-group" role="group" aria-label="${label}"><span class="flow-attribute-label">${label}</span><div class="flow-attribute-options">${choices.map(([value,text]) => `<button type="button" class="flow-chip" data-stage-act="attr" data-field="${field}" data-value="${value}" aria-pressed="${item[field] === value}">${text}</button>`).join('')}</div></div>`).join('') +
            `<label class="flow-attribute-group"><span class="flow-attribute-label">预计用时（分钟）</span><input type="number" min="0" max="1440" step="1" data-field="estimated_minutes" aria-label="当天预计用时（分钟）" placeholder="可留空" value="${item.estimated_minutes ?? ''}"></label>`;
    }
    function renderDraft() {
        const draft = state.draft;
        $('#stageScheduleContext').textContent = draft ? `${draft.project.title} · ${draft.stage.title} · ${stageName(draft.stage)}${draft.completed_count ? ' · 已完成 ' + draft.completed_count + ' 项未调入' : ''}${draft.project.outcome ? '\n项目预期结果：' + draft.project.outcome : ''}${draft.stage.state === 'next' ? '\n可以预先安排，开始执行前仍须核对阶段交接条件。' : ''}` : '';
        $('#stageScheduleDraft').innerHTML = draft ? draft.items.map(item => {
            const source = item.project_task_id ? `原项目任务：${escape(item.title)} · 整项预计 ${item.source_estimate ?? '未填'} 分钟` : '新增阶段任务 · 保存时同时建立并关联';
            if (item.scheduled || !item.active) return `<div class="schedule-stage-omitted" data-stage-item="${item.item_key}"><div>${escape(item.title)}<small>${item.scheduled ? '已在这一天，无需重复添加' : escape(item.readiness?.summary || '本次暂不安排')}</small></div>${item.scheduled ? '' : `<button type="button" data-stage-act="restore">${item.readiness?.can_start === false ? '安排为待条件' : '恢复安排'}</button>`}</div>`;
            const previous = item.previous_progress;
            return `<article class="schedule-stage-item" data-stage-item="${item.item_key}"><div class="schedule-stage-head"><small>${source}</small><button type="button" data-stage-act="omit">今天暂不安排</button></div>
                <label class="schedule-stage-text"><span class="flow-attribute-label">今天做到什么</span><input type="text" maxlength="500" data-field="text" value="${escape(item.text)}" placeholder="写下今天准备推进到哪里" aria-label="今天做到什么"></label>
                <div class="flow-task-attributes">${attrs(item)}</div>
                ${item.readiness?.can_start === false ? `<p class="schedule-stage-waiting">${escape(item.readiness.summary)}；可以预先安排，开始时仍需核对条件。</p>` : ''}
                ${previous ? `<p class="schedule-stage-previous">上次 ${escape(previous.date)}：${escape(previous.note || previous.text)}${previous.completed ? '（当天已完成）' : ''}</p>` : ''}</article>`;
        }).join('') + '<button type="button" class="schedule-stage-new" data-stage-act="new">在本阶段写一项当天行动</button>' : '';
        totals();
    }
    function totals() {
        const selected = state.draft?.items.filter(item => item.active && !item.scheduled) || [];
        const unknown = selected.filter(item => item.estimated_minutes == null || item.estimated_minutes === '').length;
        const minutes = selected.reduce((sum, item) => sum + (Number(item.estimated_minutes) || 0), 0);
        $('#stageScheduleTotal').textContent = `本次新增 ${selected.length} 项 · 已填预计 ${minutes} 分钟${unknown ? ' · ' + unknown + ' 项未估时' : ''}`;
        const save = $('[data-stage-act="save"]'); save.disabled = state.busy || !selected.length;
        save.textContent = state.busy ? '正在保存…' : `保存到 ${state.day || '这一天'}${selected.length ? ' · ' + selected.length + ' 项' : ''}`;
        panel.querySelectorAll('select').forEach(select => { select.disabled = state.busy; });
    }
    function onInput(event) {
        const row = event.target.closest('[data-stage-item]'), field = event.target.dataset.field;
        if (!row || !field || !state.draft) return;
        const item = state.draft.items.find(item => item.item_key === row.dataset.stageItem);
        if (!item) return;
        item[field] = field === 'estimated_minutes' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value;
        totals();
    }
    async function onClick(event) {
        const button = event.target.closest('[data-stage-act]'); if (!button || state.busy) return;
        const action = button.dataset.stageAct;
        if (action === 'cancel') { state.drafts.delete(draftKey()); state.draft = null; setOpen(false); document.getElementById('scheduleProjectEntry')?.focus(); return; }
        const row = button.closest('[data-stage-item]'), item = state.draft?.items.find(item => item.item_key === row?.dataset.stageItem);
        if (action === 'omit' || action === 'restore') { item.active = action === 'restore'; renderDraft(); return; }
        if (action === 'attr') {
            const field = button.dataset.field; item[field] = item[field] === button.dataset.value ? null : button.dataset.value;
            button.closest('.flow-attribute-options').querySelectorAll('button').forEach(option => option.setAttribute('aria-pressed', String(item[field] === option.dataset.value))); return;
        }
        if (action === 'new') { const item = freshItem(); state.draft.items.push(item); renderDraft(); $(`[data-stage-item="${item.item_key}"] [data-field="text"]`)?.focus(); return; }
        if (action !== 'save' || !state.draft) return;
        const items = state.draft.items.filter(item => item.active && !item.scheduled);
        if (items.some(item => !item.text.trim())) { status('请填写每项“今天做到什么”，或将它暂不安排。', true); return; }
        if (items.some(item => item.estimated_minutes != null && (!Number.isInteger(item.estimated_minutes) || item.estimated_minutes < 0 || item.estimated_minutes > 1440))) { status('预计用时请填写 0 至 1440 的整数分钟，也可以留空。', true); return; }
        const day = state.day, stageId = state.stageId, token = state.token, generation = state.generation;
        const body = {task_date:day, request_key:state.draft.request_key, items:items.map(item => Object.fromEntries(['item_key','project_task_id','text','estimated_minutes','familiarity','difficulty','importance'].map(field => [field,item[field]])))};
        state.busy = true; totals(); status('正在保存当天安排…');
        try {
            await api(`/${stageId}`, {method:'POST',body:JSON.stringify(body)});
            if (token !== localStorage.getItem('authToken')) return;
            state.drafts.delete(`${day}:${stageId}`);
            if (sameContext(generation, token, day)) { state.draft = null; setOpen(false); }
            await window.loadDailySchedule?.();
            if (typeof showMessage === 'function') showMessage(`已保存到 ${day}；项目原任务保留`, 'success');
        } catch (error) { if (sameContext(generation, token, day)) fail(error); }
        finally { if (sameContext(generation, token, day)) { state.busy = false; totals(); } }
    }
    window.ShuranScheduleProjects = {sync,toggle};
    window.addEventListener('shuran-auth-change', () => { reset(); state.token = localStorage.getItem('authToken'); });
    window.addEventListener('storage', event => { if (event.key === 'authToken') { reset(); state.token = localStorage.getItem('authToken'); } });
})();
