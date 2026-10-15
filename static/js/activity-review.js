/** Review confirmed activity intervals in the "记" area. */
(() => {
    const root = document.getElementById('activityReviewList');
    if (!root) return;
    const summary = document.getElementById('activityReviewSummary');
    const range = document.getElementById('activityReviewRange');
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    function dayOffset(key, days) {
        const date = new Date(key + 'T00:00:00Z');
        date.setUTCDate(date.getUTCDate() + days);
        return date.toISOString().slice(0, 10);
    }
    const dayStart = (key) => new Date(key + 'T00:00:00+08:00').getTime();
    async function get(path, token) {
        const response = await fetch(path, {headers:{Authorization:'Bearer ' + token}});
        if (!response.ok) throw new Error('加载实际活动失败');
        return response.json();
    }
    window.loadActivityReview = async function loadActivityReview() {
        const token = localStorage.getItem('authToken');
        if (!token) { summary.textContent = '登录后可回看已记录的实际活动。'; root.innerHTML = ''; return; }
        const endDay = today(), startDay = dayOffset(endDay, range.value === 'week' ? -6 : 0);
        try {
            const [sessions, overview] = await Promise.all([
                get('/api/projects/sessions?start_date=' + dayOffset(startDay, -1) + '&end_date=' + endDay, token),
                get('/api/projects/overview', token),
            ]);
            const start = dayStart(startDay), end = dayStart(dayOffset(endDay, 1));
            const names = new Map(overview.projects.flatMap(p => p.tasks.map(t => [t.id, t.title])));
            const items = sessions.items.filter(s => s.ended_at && Date.parse(s.started_at) < end && Date.parse(s.ended_at) > start);
            const counted = items.reduce((n, s) => n + Math.min(Date.parse(s.ended_at), end) - Math.max(Date.parse(s.started_at), start), 0);
            const marked = items.filter(s => s.assessment?.importance).length;
            summary.textContent = `已记录 ${Math.round(counted / 6000) / 10} 分钟 · 已判断 ${marked} 段 · 未标记 ${items.length - marked} 段。未记录的时间不计入。`;
            root.innerHTML = items.length ? items.map(s => {
                const a = s.assessment || {};
                const options = '<option value="">暂不关联</option>' + overview.goals.map(g => `<option value="${g.id}" ${g.id === a.goal_id ? 'selected' : ''}>${esc(g.title)}</option>`).join('');
                return `<article class="activity-review-card"><strong>${esc(s.kind === 'break' ? '休息' : names.get(s.project_task_id) || s.label || '实际活动')}</strong>
                    <p>${esc(new Date(s.started_at).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}))} → ${esc(new Date(s.ended_at).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}))} · ${s.duration_minutes} 分</p>
                    ${a.goal_title_snapshot ? `<p>评价时目标：${esc(a.goal_title_snapshot)}</p>` : ''}
                    <form data-session="${s.id}"><label>当时目标 <select name="goal_id">${options}</select></label>
                      <label>对目标的帮助 <select name="importance"><option value="">未标记</option><option value="unimportant" ${a.importance === 'unimportant' ? 'selected' : ''}>不重要</option><option value="ordinary" ${a.importance === 'ordinary' ? 'selected' : ''}>一般</option><option value="important" ${a.importance === 'important' ? 'selected' : ''}>重要</option></select></label>
                      <label>觉得有趣 <input name="interesting" type="checkbox" ${a.interesting ? 'checked' : ''}></label>
                      <label>说明 <input name="note" maxlength="2000" value="${esc(a.note)}"></label><button type="submit">保存评价</button></form></article>`;
            }).join('') : '<p>这个范围还没有确认的实际活动片段。可在「项目 → 现在做」计时或事后补记。</p>';
        } catch (error) { summary.textContent = error.message; root.innerHTML = ''; }
    };
    range.addEventListener('change', () => window.loadActivityReview());
    root.addEventListener('submit', async (event) => {
        const form = event.target.closest('form[data-session]');
        if (!form) return;
        event.preventDefault();
        const token = localStorage.getItem('authToken');
        const data = new FormData(form);
        const response = await fetch('/api/projects/sessions/' + form.dataset.session + '/assessment', {
            method:'PUT', headers:{Authorization:'Bearer ' + token,'Content-Type':'application/json'},
            body:JSON.stringify({goal_id:data.get('goal_id') ? Number(data.get('goal_id')) : null,
                importance:data.get('importance') || null, interesting:data.has('interesting'), note:data.get('note') || null}),
        }).catch(() => null);
        if (!response?.ok) { summary.textContent = '保存评价失败，请稍后重试。'; return; }
        await window.loadActivityReview();
    });
})();
