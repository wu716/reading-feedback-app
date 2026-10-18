(function () {
    'use strict';
    const labels = {reading:'读书',fitness:'健身',friends:'帮朋友',family:'陪家人',investment:'定投',writing:'写作',work:'工作',relaxation:'放松'};
    const keys = Object.keys(labels);
    const colors = ['#56758b','#7c9374','#b58f68','#ab786b','#9b9369','#8285a2','#37566d','#9daa91'];
    const el = id => document.getElementById(id);
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const yuan = cents => (cents / 100).toFixed(2);
    const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai'}).format(new Date());
    const api = (path, options) => apiRequest(`/api/long-term${path}`, options || {});
    const drafts = new Map();
    let current = null, currentDate = '', period = 'day', view = 'daily';
    let dayRequest = 0, reportRequest = 0, mutating = false, dirty = false, noAttention = false;
    let sessionToken = localStorage.getItem('authToken');

    function time(seconds) {
        const minutes = Math.round(seconds / 60);
        return minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)} 小时${minutes % 60 ? ` ${minutes % 60} 分` : ''}`;
    }
    function status(message, state = '') {
        el('ltStatus').textContent = message;
        el('ltStatus').className = `lt-status ${state}`;
    }
    function captureDraft() {
        if (!current) return null;
        return {
            manual: Object.fromEntries(keys.map(key => [key, el(`ltMinutes-${key}`).value])),
            attention: [...el('ltAttention').querySelectorAll('.lt-attention-row')].map(row => ({name:row.querySelector('.lt-att-name').value, minutes:row.querySelector('.lt-att-min').value})),
            money:el('ltMoney').value, investment:el('ltInvestment').value, noAttention, dirty,
            open:[...el('ltManual').querySelectorAll('details[open]')].map(item => item.dataset.activity)
        };
    }
    function rememberDraft(changed = false) {
        if (!current) return;
        if (changed) dirty = true;
        drafts.set(currentDate, captureDraft());
        if (!mutating) status(dirty ? '有未保存的修改' : current.recorded ? '已记录' : '待记录', dirty ? 'is-dirty' : current.recorded ? 'is-saved' : '');
        if (changed) el('ltSaveHint').textContent = '确认两类开销后，保存这一天。';
    }
    function setBusy(busy) {
        mutating = busy;
        el('ltDayFields').disabled = busy || !current;
        ['ltDate','ltPrevDay','ltNextDay'].forEach(id => { el(id).disabled = busy; });
        el('ltSave').disabled = busy;
    }
    function refreshTotals() {
        if (!current) return;
        const totals = keys.map(key => (current.automatic_seconds[key] || 0) + Math.max(0, Number(el(`ltMinutes-${key}`).value) || 0) * 60);
        const total = totals.reduce((sum, value) => sum + value, 0), max = Math.max(1, ...totals);
        keys.forEach((key, index) => {
            el('ltManual').querySelector(`[data-total="${key}"]`).textContent = totals[index] || current.recorded ? time(totals[index]) : '待记录';
            el('ltManual').querySelector(`[data-bar="${key}"]`).style.width = `${totals[index] / max * 100}%`;
            el('ltManual').querySelector(`[data-auto="${key}"]`).textContent = `时间日志已计入 ${time(current.automatic_seconds[key] || 0)}，只需补录其余时间。`;
        });
        el('ltTotalTime').textContent = total || current.recorded ? time(total) : '—';
        el('ltDistribution').innerHTML = totals.map((value, index) => `<span style="width:${total ? value / total * 100 : 0}%;background:${colors[index]}"></span>`).join('');
        el('ltOverviewHint').textContent = total ? `${totals.filter(Boolean).length} 个方向已有投入 · 日志与补录合计` : '把时间留给在意的事，从今天的一笔开始。';
    }
    function attentionRow(name = '', minutes = '') {
        const row = document.createElement('div'); row.className = 'lt-attention-row';
        row.innerHTML = `<input class="lt-att-name" aria-label="注意力开销项目" maxlength="60" placeholder="如：刷手机" value="${esc(name)}"><div class="lt-minute-input"><input class="lt-att-min" aria-label="注意力开销分钟" type="number" min="0" max="1440" step="1" inputmode="numeric" placeholder="0" value="${esc(minutes)}"><span>分</span></div><button type="button" aria-label="移除注意力项目">×</button>`;
        row.querySelector('button').onclick = () => { row.remove(); rememberDraft(true); };
        el('ltAttention').appendChild(row);
    }
    function renderAttention(items) {
        el('ltAttention').innerHTML = noAttention ? '<p class="lt-zero-confirmation">✓ 今天没有注意力开销</p>' : '';
        el('ltNoAttention').hidden = noAttention;
        if (!noAttention) (items.length ? items : [{name:'', minutes:''}]).forEach(item => attentionRow(item.name, item.minutes));
    }
    function renderNodes() {
        el('ltNodeCount').textContent = `${current.nodes.length} 条`;
        el('ltNodes').innerHTML = current.nodes.length ? current.nodes.map(node => `<div class="lt-node"><div>${esc(node.label)}<small>${time(node.seconds)} · 上一节点至此</small></div><select data-node="${node.id}" aria-label="${esc(node.label)}的时间归类"><option value="">不计入</option>${keys.map(key => `<option value="${key}" ${node.category === key ? 'selected' : ''}>${labels[key]}</option>`).join('')}</select></div>`).join('') : '<p class="lt-note">当天还没有时间日志，可直接在上方补录。</p>';
        el('ltNodes').querySelectorAll('select').forEach(select => select.onchange = async () => {
            const oldValue = current.nodes.find(node => String(node.id) === select.dataset.node).category || '';
            rememberDraft(); setBusy(true); status('正在归类…');
            try {
                current = await api(`/nodes/${select.dataset.node}/category`, {method:'PUT', body:JSON.stringify({category:select.value || null})});
                refreshTotals();
            } catch (error) {
                select.value = oldValue;
                el('ltSaveHint').textContent = error.message || '归类失败，请重试。';
            } finally { setBusy(false); rememberDraft(); }
        });
    }
    function renderDay(day, draft) {
        current = day; dirty = Boolean(draft?.dirty);
        noAttention = draft ? draft.noAttention : day.attention_items.length === 1 && day.attention_items[0].name === '无' && day.attention_items[0].minutes === 0;
        el('ltManual').innerHTML = keys.map((key, index) => `<details class="lt-activity" data-activity="${key}" ${draft?.open.includes(key) ? 'open' : ''} style="--activity-color:${colors[index]}"><summary><span class="lt-activity-number">${String(index + 1).padStart(2, '0')}</span><span class="lt-activity-name">${labels[key]}</span><span class="lt-activity-track"><span data-bar="${key}"></span></span><output data-total="${key}"></output><span class="lt-activity-action">${draft?.open.includes(key) ? '收起' : '记录'}</span></summary><div class="lt-activity-editor"><label for="ltMinutes-${key}">手动补录</label><div class="lt-editor-controls"><div class="lt-minute-input"><input id="ltMinutes-${key}" data-category="${key}" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${esc(draft ? draft.manual[key] : day.manual_minutes[key] || 0)}"><span>分钟</span></div>${[15,30,60].map(value => `<button type="button" data-add="${value}" data-key="${key}">+${value}</button>`).join('')}</div><p class="lt-note" data-auto="${key}"></p></div></details>`).join('');
        el('ltManual').querySelectorAll('details').forEach(item => item.addEventListener('toggle', () => {
            item.querySelector('.lt-activity-action').textContent = item.open ? '收起' : '记录'; rememberDraft();
        }));
        el('ltManual').querySelectorAll('[data-add]').forEach(button => button.onclick = () => {
            const input = el(`ltMinutes-${button.dataset.key}`);
            input.value = Math.min(1440, (Number(input.value) || 0) + Number(button.dataset.add));
            rememberDraft(true); refreshTotals();
        });
        renderAttention(draft ? draft.attention : day.attention_items);
        el('ltMoney').value = draft ? draft.money : day.money_cents == null ? '' : yuan(day.money_cents);
        el('ltInvestment').value = draft ? draft.investment : day.investment_cents == null ? '0' : yuan(day.investment_cents);
        renderNodes(); refreshTotals(); rememberDraft();
        el('ltSaveHint').textContent = draft?.dirty ? '已恢复本次会话中的草稿，记得保存。' : day.recorded ? '这一天已保存，可继续修改。' : '确认两类开销后，保存这一天。';
    }
    async function loadDay() {
        if (mutating || !el('ltDate').value) return;
        rememberDraft();
        const date = el('ltDate').value, request = ++dayRequest;
        currentDate = date; current = null; el('ltDayFields').disabled = true;
        el('ltTotalTime').textContent = '—'; status('正在读取…');
        try {
            const day = await api(`/day?day=${date}`);
            if (request !== dayRequest) return;
            renderDay(day, drafts.get(date)); el('ltDayFields').disabled = false;
        } catch (error) {
            if (request === dayRequest) status(error.message || '读取失败，请重新选择日期', 'is-error');
        }
        if (view === 'report') loadReport();
    }
    function invalid(input, message) {
        const details = input?.closest('details'); if (details) details.open = true;
        if (input) input.focus();
        throw new Error(message);
    }
    function integer(input, label) {
        const value = input.value.trim();
        if (!/^\d+$/.test(value) || Number(value) > 1440) invalid(input, `${label}请填写 0～1440 的整数分钟。`);
        return Number(value);
    }
    function money(input, label) {
        if (!/^\d+(\.\d{1,2})?$/.test(input.value.trim())) invalid(input, `${label}必须填写非负金额，最多两位小数；没有则填 0。`);
        return input.value.trim();
    }
    async function saveDay() {
        if (!current || mutating) return;
        if (sessionToken !== localStorage.getItem('authToken')) { window.loadLongTerm(); return; }
        let body;
        try {
            const manual = Object.fromEntries(keys.map(key => [key, integer(el(`ltMinutes-${key}`), labels[key])]));
            const manualTotal = Object.values(manual).reduce((a,b) => a+b, 0);
            const nextTotal = manualTotal * 60 + Object.values(current.automatic_seconds).reduce((a,b) => a+b, 0);
            if (manualTotal > 1440 || (nextTotal > 86400 && nextTotal > Object.values(current.total_seconds).reduce((a,b) => a+b, 0))) invalid(null, '日志与补录合计超过 24 小时，请检查重复记录。');
            const attention = noAttention ? [{name:'无', minutes:0}] : [...el('ltAttention').querySelectorAll('.lt-attention-row')].map(row => {
                const name = row.querySelector('.lt-att-name');
                if (!name.value.trim()) invalid(name, '请填写注意力开销项目，或选择“今天无开销”。');
                return {name:name.value.trim(), minutes:integer(row.querySelector('.lt-att-min'), '注意力开销')};
            });
            if (!attention.length || attention.length > 30) invalid(null, '请记录 1～30 个注意力开销项目，或选择“今天无开销”。');
            if (new Set(attention.map(item => item.name)).size !== attention.length) invalid(null, '注意力开销项目名称不能重复，请合并相同项目。');
            if (attention.reduce((sum,item) => sum+item.minutes, 0) > 1440) invalid(null, '注意力开销合计不能超过 1440 分钟。');
            body = {manual_minutes:manual, attention_items:attention, money_yuan:money(el('ltMoney'), '金钱开销'), investment_yuan:money(el('ltInvestment'), '定投金额')};
        } catch (error) { el('ltSaveHint').textContent = error.message; status('请补全记录', 'is-error'); return; }
        const date = currentDate, open = captureDraft().open;
        setBusy(true); status('正在保存…'); el('ltSaveHint').textContent = '正在保存这一天…';
        try {
            const day = await api(`/day?day=${date}`, {method:'PUT', body:JSON.stringify(body)});
            drafts.delete(date); renderDay(day);
            open.forEach(key => { el('ltManual').querySelector(`[data-activity="${key}"]`).open = true; });
            status('已记录', 'is-saved'); el('ltSaveHint').textContent = '已保存，统计报告已同步。';
            if (view === 'report') loadReport();
        } catch (error) {
            el('ltSaveHint').textContent = error.message || '保存失败，内容已保留，请重试。'; status('保存失败', 'is-error');
        } finally { setBusy(false); }
    }
    function calendar(report) {
        const saved = new Map(report.days.map(day => [day.date, day]));
        const start = new Date(`${report.start}T12:00:00`), end = new Date(`${report.end}T12:00:00`), cells = [];
        while (start <= end) {
            const date = `${start.getFullYear()}-${String(start.getMonth()+1).padStart(2,'0')}-${String(start.getDate()).padStart(2,'0')}`;
            const state = saved.has(date) ? '已记录' : date > today() ? '未到日期' : '未记录';
            cells.push(`<span class="${saved.has(date) ? 'is-recorded' : date > today() ? 'is-future' : ''}" title="${date} ${state}">${start.getMonth()+1}/${start.getDate()}</span>`);
            start.setDate(start.getDate()+1);
        }
        return cells.join('');
    }
    async function loadReport() {
        const date = el('ltDate').value, selected = period, request = ++reportRequest;
        el('ltReport').innerHTML = '<p class="lt-note">正在汇总…</p>';
        try {
            const report = await api(`/report?period=${selected}&anchor=${date}`);
            if (request !== reportRequest || view !== 'report' || date !== el('ltDate').value || selected !== period) return;
            const totals = keys.map(key => report.total_seconds[key] || 0), max = Math.max(1, ...totals);
            const attention = Object.entries(report.attention_by_name).filter(([name,minutes]) => name !== '无' || minutes > 0).sort((a,b) => b[1]-a[1]);
            el('ltReport').innerHTML = `<p class="lt-report-range">${report.start} — ${report.end}<span>已记录 ${report.recorded_days} / ${report.total_days} 天</span></p><div class="lt-report-metrics"><div><span>时间投入</span><strong>${time(totals.reduce((a,b) => a+b,0))}</strong></div><div><span>注意力开销</span><strong>${report.recorded_days ? time(report.attention_minutes*60) : '—'}</strong></div><div><span>金钱开销</span><strong>${report.recorded_days ? `¥ ${yuan(report.money_cents)}` : '—'}</strong></div><div><span>定投 · 单独统计</span><strong>${report.recorded_days ? `¥ ${yuan(report.investment_cents)}` : '—'}</strong></div></div><div class="lt-report-body"><section><h3>八个方向的投入</h3><div class="lt-report-bars">${keys.map((key,index) => `<div><span>${labels[key]}</span><span class="lt-report-track"><i style="width:${totals[index]/max*100}%;background:${colors[index]}"></i></span><strong>${time(totals[index])}</strong></div>`).join('')}</div></section><section><h3>注意力花在哪里</h3>${attention.length ? attention.map(([name,minutes]) => `<div class="lt-attention-summary"><span>${esc(name)}</span><strong>${time(minutes*60)}</strong></div>`).join('') : `<p class="lt-note">${report.recorded_days ? '已记录的日期没有注意力开销。' : '记录每日开销后，这里会按项目汇总。'}</p>`}<h3 class="lt-calendar-title">记录足迹</h3><div class="lt-report-calendar">${calendar(report)}</div><p class="lt-note">深色为已记录，浅色为未记录，淡色为未来日期。</p></section></div><p class="lt-report-footnote">开销只汇总已保存日期，未记录的日期不按 0 计算。手动补录保存后计入报告；定投不计入金钱开销。</p>`;
        } catch (error) { if (request === reportRequest) el('ltReport').innerHTML = `<p class="lt-note">${esc(error.message || '报告读取失败，请重新选择报告周期。')}</p>`; }
    }
    function switchView(next) {
        view = next;
        el('ltDailyPanel').hidden = view !== 'daily'; el('ltReportPanel').hidden = view !== 'report';
        document.querySelectorAll('[data-lt-view]').forEach(button => { const active = button.dataset.ltView === view; button.classList.toggle('active', active); button.setAttribute('aria-pressed', active); });
        if (view === 'report') loadReport();
    }
    window.loadLongTerm = function () {
        if (!el('ltDate') || mutating) return;
        const token = localStorage.getItem('authToken');
        if (token !== sessionToken) { drafts.clear(); current = null; dirty = false; sessionToken = token; }
        el('ltDate').value ||= today(); loadDay();
    };
    document.addEventListener('DOMContentLoaded', () => {
        el('ltDate').onchange = loadDay;
        ['ltPrevDay','ltNextDay'].forEach((id,index) => el(id).onclick = () => {
            const date = new Date(`${el('ltDate').value}T12:00:00`); date.setDate(date.getDate() + (index ? 1 : -1));
            el('ltDate').value = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`; loadDay();
        });
        el('ltDayFields').addEventListener('input', () => { rememberDraft(true); refreshTotals(); });
        el('ltAddAttention').onclick = () => {
            if (noAttention) { noAttention = false; el('ltAttention').innerHTML = ''; el('ltNoAttention').hidden = false; }
            attentionRow(); rememberDraft(true); el('ltAttention').lastElementChild.querySelector('input').focus();
        };
        el('ltNoAttention').onclick = () => { noAttention = true; renderAttention([]); rememberDraft(true); };
        el('ltSave').onclick = saveDay;
        document.querySelectorAll('[data-lt-view]').forEach(button => button.onclick = () => switchView(button.dataset.ltView));
        document.querySelectorAll('#ltReportPanel [data-period]').forEach(button => button.onclick = () => {
            period = button.dataset.period;
            document.querySelectorAll('#ltReportPanel [data-period]').forEach(item => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', active); }); loadReport();
        });
        window.addEventListener('beforeunload', event => {
            if (dirty || [...drafts.values()].some(draft => draft.dirty)) { event.preventDefault(); event.returnValue = ''; }
        });
    });
})();
