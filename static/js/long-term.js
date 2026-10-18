(function () {
    'use strict';
    const labels = {reading:'读书',fitness:'健身',friends:'帮朋友',family:'陪家人',investment:'定投',writing:'写作',work:'工作',relaxation:'放松'};
    const categories = Object.keys(labels);
    let current = null;
    const el = id => document.getElementById(id);
    const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const yuan = cents => (cents / 100).toFixed(2);
    const time = seconds => `${Math.floor(seconds / 3600)}小时${Math.round(seconds % 3600 / 60)}分`;
    const today = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`; };
    const api = (path, options) => apiRequest(`/api/long-term${path}`, options || {});
    function notice(message, error) { if (typeof showMessage === 'function') showMessage(message, error ? 'error' : 'success'); else el('ltStatus').textContent = message; }
    function attentionRow(name = '', minutes = '') {
        const row = document.createElement('div'); row.className = 'lt-attention-row';
        row.innerHTML = `<label>项目<input class="lt-att-name" maxlength="60" placeholder="如：刷手机" value="${esc(name)}"></label><label>分钟<input class="lt-att-min" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${esc(minutes)}"></label><button type="button" class="lt-ghost" aria-label="移除项目">移除</button>`;
        row.querySelector('button').onclick = () => row.remove();
        el('ltAttention').appendChild(row);
    }
    function renderDay(day) {
        current = day;
        el('ltStatus').textContent = day.recorded ? '这一天已保存，可继续修改。' : '这一天尚未完成记录；空白不会算作 0。';
        el('ltManual').innerHTML = categories.map(key => `<label>${labels[key]} · 分钟<input data-category="${key}" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${day.manual_minutes[key] ?? 0}"></label>`).join('');
        el('ltAttention').innerHTML = '';
        (day.attention_items.length ? day.attention_items : [{name:'', minutes:''}]).forEach(item => attentionRow(item.name, item.minutes));
        el('ltMoney').value = day.money_cents == null ? '' : yuan(day.money_cents);
        el('ltInvestment').value = day.investment_cents == null ? '0' : yuan(day.investment_cents);
        el('ltNodes').innerHTML = day.nodes.length ? day.nodes.map(node => `<div class="lt-node"><div>${esc(node.label)}<small>上一节点至此：${time(node.seconds)}${node.seconds === 0 ? ' · 无可计入时长' : ''}</small></div><select data-node="${node.id}" aria-label="为日志归类"><option value="">不计入</option>${categories.map(key => `<option value="${key}" ${node.category === key ? 'selected' : ''}>${labels[key]}</option>`).join('')}</select></div>`).join('') : '<p class="lt-hint">当天还没有时间日志。你仍可手动补录用时。</p>';
        el('ltNodes').querySelectorAll('select[data-node]').forEach(select => select.onchange = async () => {
            select.disabled = true;
            try { current = await api(`/nodes/${select.dataset.node}/category`, {method:'PUT', body:JSON.stringify({category:select.value || null})}); select.disabled = false; await loadReport(); }
            catch (error) { notice(error.message || '归类失败', true); await loadDay(); }
        });
    }
    async function loadDay() {
        try { renderDay(await api(`/day?day=${encodeURIComponent(el('ltDate').value)}`)); }
        catch (error) { el('ltStatus').textContent = error.message || '加载失败'; }
    }
    async function saveDay() {
        try {
            const manual_minutes = {};
            el('ltManual').querySelectorAll('input').forEach(input => { if (!/^\d+$/.test(input.value)) throw new Error('八类活动都要填写非负整数分钟'); manual_minutes[input.dataset.category] = Number(input.value); });
            const attention_items = [...el('ltAttention').querySelectorAll('.lt-attention-row')].map(row => {
                const name = row.querySelector('.lt-att-name').value.trim(); const raw = row.querySelector('.lt-att-min').value;
                if (!name || !/^\d+$/.test(raw)) throw new Error('每个注意力项目都要填写名称和非负整数分钟');
                return {name, minutes:Number(raw)};
            });
            if (!attention_items.length) throw new Error('请至少记录一项注意力开销；没有时填“无，0 分钟”');
            const money_yuan = el('ltMoney').value;
            const investment_yuan = el('ltInvestment').value;
            if (!/^\d+(\.\d{1,2})?$/.test(money_yuan) || !/^\d+(\.\d{1,2})?$/.test(investment_yuan)) throw new Error('金钱开销和定投金额都要填写，最多两位小数');
            renderDay(await api(`/day?day=${encodeURIComponent(el('ltDate').value)}`, {method:'PUT', body:JSON.stringify({manual_minutes,attention_items,money_yuan,investment_yuan})}));
            notice('日报已保存'); await loadReport();
        } catch (error) { notice(error.message || '保存失败', true); }
    }
    async function loadReport() {
        const target = el('ltReport'); target.textContent = '正在生成报告…';
        try {
            const report = await api(`/report?period=${el('ltPeriod').value}&anchor=${encodeURIComponent(el('ltDate').value)}`);
            const max = Math.max(1, ...categories.map(key => report.total_seconds[key]));
            const total = categories.reduce((sum, key) => sum + report.total_seconds[key], 0);
            const days = []; const start = new Date(`${report.start}T12:00:00`); const end = new Date(`${report.end}T12:00:00`);
            const recorded = new Set(report.days.map(day => day.date));
            for (let cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate()+1)) { const day = `${cursor.getFullYear()}-${String(cursor.getMonth()+1).padStart(2,'0')}-${String(cursor.getDate()).padStart(2,'0')}`; days.push(`<span class="lt-day ${recorded.has(day) ? '' : 'missing'}">${day.slice(5)} ${recorded.has(day) ? '已记' : '未记'}</span>`); }
            target.innerHTML = `<p class="lt-hint">${report.start} 至 ${report.end} · 已记录 ${report.recorded_days}/${report.total_days} 天。未记录日不作零值推断。</p><div class="lt-summary"><span class="lt-pill">活动合计 ${time(total)}</span><span class="lt-pill">注意力开销 ${report.attention_minutes} 分钟</span><span class="lt-pill">金钱开销 ¥${yuan(report.money_cents)}</span><span class="lt-pill">定投 ¥${yuan(report.investment_cents)}</span></div>${categories.map(key => `<div class="lt-bar-row"><span>${labels[key]}</span><div class="lt-bar"><span style="width:${Math.round(report.total_seconds[key] / max * 100)}%"></span></div><span>${time(report.total_seconds[key])}</span></div>`).join('')}<h3>注意力开销项目</h3><div class="lt-summary">${Object.entries(report.attention_by_name).map(([name, minutes]) => `<span class="lt-pill">${esc(name)} ${minutes} 分钟</span>`).join('') || '<span class="lt-hint">尚无记录</span>'}</div><h3>记录日期</h3><div class="lt-days">${days.join('')}</div>`;
        } catch (error) { target.textContent = error.message || '报告生成失败'; }
    }
    window.loadLongTerm = async function () {
        if (!el('ltDate').value) el('ltDate').value = today();
        await Promise.all([loadDay(), loadReport()]);
    };
    document.addEventListener('DOMContentLoaded', () => {
        if (!el('ltDate')) return;
        el('ltDate').value = today();
        el('ltDate').onchange = window.loadLongTerm;
        el('ltPeriod').onchange = loadReport;
        el('ltAddAttention').onclick = () => attentionRow();
        el('ltSave').onclick = saveDay;
    });
})();
