(function () {
    'use strict';
    const labels = {reading:'读书',fitness:'运动',friends:'帮朋友',family:'陪家人',investment:'定投',writing:'写作',work:'工作',relaxation:'放松'};
    const keys = Object.keys(labels), periods = {day:'日',week:'周',month:'月',quarter:'季',year:'年'};
    const colors = ['#56758b','#7c9374','#b58f68','#ab786b','#9b9369','#8285a2','#37566d','#9daa91'];
    const kinds = {nonfiction:'非虚构',fiction:'虚构',unclassified:'未分类'};
    const el = id => document.getElementById(id);
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const yuan = n => (Number(n || 0) / 100).toFixed(2);
    const time = n => { const m = Math.round((n || 0) / 60); return m < 60 ? m + ' 分钟' : Math.floor(m / 60) + ' 小时' + (m % 60 ? ' ' + m % 60 + ' 分' : ''); };
    const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai'}).format(new Date());
    const clone = x => JSON.parse(JSON.stringify(x));
    const uid = () => globalThis.crypto?.randomUUID?.() || 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2);
    const api = (path, options = {}) => apiRequest('/api/long-term/details' + path, options);
    const options = (rows, selected, empty) => (empty == null ? '' : '<option value="">' + esc(empty) + '</option>') + Object.entries(rows).map(([v,n]) => '<option value="' + esc(v) + '"' + (v === selected ? ' selected' : '') + '>' + esc(n) + '</option>').join('');
    let day = null, preferences = null, settingsDraft = null, recent = [], displayedReport = null, period = 'day', view = 'daily';
    let busy = false, settingsBusy = false, dirty = false, settingsDirty = false, dayRequest = 0, reportRequest = 0, splitId = null;
    let sessionToken = localStorage.getItem('authToken'), sessionEpoch = 0;
    const drafts = new Map(), openPanels = new Set(), openEntries = new Set();
    function sameSession(epoch) { return epoch === sessionEpoch && sessionToken === localStorage.getItem('authToken'); }
    function status(message, kind = '') { el('ltStatus').textContent = message; el('ltStatus').className = 'lt-status ' + kind; }
    function touch() {
        dirty = true;
        if (day) drafts.set(day.date, clone(day));
        status('有未保存的修改', 'is-dirty');
        el('ltSaveHint').textContent = '活动、注意力和消费一起保存。报告只统计已保存的记录。';
        updateTotals();
    }
    function setBusy(value) {
        busy = value;
        el('ltDayFields').disabled = value || !day;
        ['ltDate','ltPrevDay','ltNextDay','ltSave','ltReload'].forEach(id => el(id).disabled = value);
    }
    function moneyCents(value) {
        const raw = String(value).trim();
        if (!/^\d+(\.\d{1,2})?$/.test(raw)) throw new Error('金额请填写正数，最多两位小数。');
        const [whole, fraction = ''] = raw.split('.');
        const n = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
        if (!Number.isSafeInteger(n) || n > 100000000000) throw new Error('金额超出允许范围。');
        return n;
    }
    function expenseNames(includeArchived = true, selected = '') {
        return Object.fromEntries(preferences.expense_categories.filter(c => includeArchived || !c.archived || c.id === selected).map(c => [c.id,c.name + (c.archived ? '（已停用）' : '')]));
    }
    function field(label, control, extra = '') { return '<label class="lt-field ' + extra + '"><span>' + label + '</span>' + control + '</label>'; }
    function input(a, key, type = 'text', more = '') {
        const value = key === 'minutes' ? (a._minutes ?? a.seconds / 60) : key === 'amount' ? (a._amount ?? yuan(a.amount_cents)) : a[key] ?? '';
        return '<input data-a="' + esc(a.id) + '" data-field="' + key + '" type="' + type + '" value="' + esc(value) + '" ' + more + '>';
    }
    function activityCaption(a) {
        if(a.work_excluded)return '未计入 · 原工作片保留';
        if(a.work_duplicate_of)return '已核对为同一段活动 · 不重复计时';
        if(a.work_session_id)return time(a.seconds)+' · 工作片同步'+(a.work_override_seconds!=null?' · 已调整':'');
        if(a.reader_duplicate_of)return '已核对为同一段阅读 · 不重复计时';
        return a.category === 'investment' ? '¥ ' + yuan(a.amount_cents) : time(a.seconds) + (a.category === 'writing' && a.words != null ? ' · ' + a.words + ' 字' : '');
    }
    function activityEditor(a) {
        const name = {reading:'书名（选填）',fitness:'运动项目',friends:'帮朋友做了什么',family:'陪家人做了什么',investment:'投资标的',writing:'写作主题／正在修改什么',work:'工作内容',relaxation:'放松活动'}[a.category];

        let basic = field(name, input(a,'title','text','maxlength="200" ' + (a.reader_book_key ? 'readonly ' : '') + (a.category === 'reading' ? '' : 'required ') + 'list="ltRecent-' + a.category + '"'));
        if(a.work_session_id) basic += field('计入方向','<select data-a="'+a.id+'" data-field="category">'+options(Object.fromEntries(Object.entries(labels).filter(([k])=>k!=='investment')),a.category)+'</select>');
        if (a.category === 'reading') {
            basic += field('阅读类型', '<select data-a="' + a.id + '" data-field="reading_kind" required>' + options(kinds,a.reading_kind,'请选择') + '</select>');
            basic += field('主主题 · 用于时长统计', '<select data-a="' + a.id + '" data-field="primary_topic" required>' + options(preferences.topics,a.primary_topic,'请选择') + '</select>');
        }
        basic += a.category === 'investment'
            ? field('投入金额（元）', input(a,'amount','number','min="0.01" max="1000000000" step="0.01" inputmode="decimal" required'))
            : field('时长（分钟）', input(a,'minutes','number',a.source_node_id || a.reader_book_key ? 'disabled step="any"' : 'min="0" max="1440" step="any" inputmode="decimal" required'));
        if (a.category === 'writing') basic += field('新增字数（选填，构思／修改可填 0）',input(a,'words','number','min="0" max="10000000" step="1" inputmode="numeric"'));
        if(a.category==='reading'&&!a.reader_book_key) {
            const sources=Object.fromEntries(day.activities.filter(x=>x.reader_book_key).map(x=>[x.reader_book_key,x.title+' · '+time(x.seconds)]));
            if(Object.keys(sources).length)basic+=field('与知间记录核对','<select data-a="'+a.id+'" data-field="reader_duplicate_of">'+options(sources,a.reader_duplicate_of,'独立补记，另外计时')+'</select>');
        }
        if(!a.work_session_id && !a.reader_book_key) {
            const works=Object.fromEntries(day.activities.filter(x=>x.work_session_id).map(x=>[x.work_session_id,x.title+' · '+time(x.seconds)]));
            if(Object.keys(works).length) basic+=field('与工作片核对','<select data-a="'+a.id+'" data-field="work_duplicate_of">'+options(works,a.work_duplicate_of,'独立记录，另外计时')+'</select>');
        }
        let extra = field(a.category === 'fitness' ? '运动感受（选填）' : a.category === 'reading' ? '想法／收获（选填）' : '感受／补充记录（选填）',
            '<textarea data-a="' + a.id + '" data-field="note" rows="2" maxlength="3000">' + esc(a.note) + '</textarea>', 'lt-full');
        if (a.category === 'reading') {
            extra += '<div class="lt-full"><p class="lt-note">补充主题（最多 5 个，只统计涉及次数，不重复计算阅读时长）</p><div class="lt-topic-options">' +
                Object.entries(preferences.topics).filter(([k]) => k !== 'unclassified' && k !== a.primary_topic).map(([k,n]) =>
                    '<label class="lt-check"><input type="checkbox" data-a="' + a.id + '" data-topic="' + k + '"' + (a.topics.includes(k) ? ' checked' : '') + '>' + esc(n) + '</label>').join('') + '</div></div>';
        }
        if (a.category !== 'investment') extra += '<label class="lt-check lt-full"><input type="checkbox" data-a="' + a.id + '" data-field="unplanned"' + (a.unplanned ? ' checked' : '') + '>这段活动属于非计划占用（时长仍只计算一次）</label>';
        return '<details class="lt-entry" data-entry="' + a.id + '"' + (openEntries.has(a.id) ? ' open' : '') + '><summary><span data-title="' + a.id + '">' + esc(a.title || '填写一条' + labels[a.category] + '记录') + '</span><small data-caption="' + a.id + '">' + activityCaption(a) + '</small></summary>' +
            '<div class="lt-entry-body"><div class="lt-form-grid">' + basic + '</div>' +
            (a.source_node_id ? '<p class="lt-note">' + (a.source_missing ? '原时间日志已移除或日期已更改，本条描述保留，当前不计时。可转为手动记录后填写。' : '已关联时间日志；时长随源日志更新，无需重复补录。') + '<button type="button" class="lt-text-button" data-detach="' + a.id + '">转为手动记录</button></p>' : '') +
            '<details class="lt-extra"' + (a.note || a.unplanned || a.topics.length ? ' open' : '') + '><summary>补充细节与感受</summary><div class="lt-form-grid">' + extra + '</div></details>' +
            (a.work_session_id ? '<p class="lt-note">工作片同步 · 原计时 '+time(a.work_source?.seconds || 0)+(a.source_changed?' · 来源已更新，请核对手动调整':'')+(a.source_missing?' · 此日来源已移出，保留说明，暂不计时':'')+'。本页修改仅影响长期目标。</p><div class="lt-entry-actions"><button type="button" class="lt-text-button" data-work-restore="'+a.id+'">恢复自动同步</button><button type="button" class="lt-text-button" data-work-exclude="'+a.id+'">'+(a.work_excluded?'恢复计入':'不计入本方向')+'</button><button type="button" class="lt-text-button" data-work-source="'+a.work_session_id+'">更正原工作片</button></div>' : a.reader_book_key ? '<p class="lt-note">知间逐书来源：' + esc(a.reader_source?.label || '已同步记录') + '。书名与时长随来源更新；分类和收获可补充。' + (a.source_missing ? '来源已修订移除，保留补充说明，当前不计时。' : '') + '</p>' : '<div class="lt-entry-actions"><button type="button" class="lt-text-button" data-remove-a="' + a.id + '">移除这条活动</button></div>') + '</div></details>';
    }
    function renderActivities() {
        el('ltManual').innerHTML = keys.map((key,i) => '<details class="lt-activity" data-panel="' + key + '"' + (openPanels.has(key) ? ' open' : '') + ' style="--activity-color:' + colors[i] + '"><summary><span class="lt-activity-number">' + String(i+1).padStart(2,'0') + '</span><span class="lt-activity-name">' + labels[key] + '</span><span class="lt-activity-track"><span data-bar="' + key + '"></span></span><output data-total="' + key + '"></output><span class="lt-activity-action">展开</span></summary><div class="lt-activity-editor">' +
            day.activities.filter(a => a.category === key).map(activityEditor).join('') +
            '<button type="button" class="lt-text-button" data-add-a="' + key + '">＋ 添加' + labels[key] + '记录</button>' +
            '<label class="lt-check"><input type="checkbox" data-confirm-category="'+key+'"'+(day.category_confirmed?.includes(key)?' checked':'')+'>此方向已核对（没有记录表示本日没有）</label>'+
            '<datalist id="ltRecent-' + key + '">' + recent.filter(r => r.category === key).map(r => '<option value="' + esc(r.title) + '"></option>').join('') + '</datalist></div></details>').join('');
        el('ltManual').querySelectorAll('[data-panel]').forEach(d => d.addEventListener('toggle', () => { d.open ? openPanels.add(d.dataset.panel) : openPanels.delete(d.dataset.panel); }));
        el('ltManual').querySelectorAll('[data-entry]').forEach(d => d.addEventListener('toggle', () => { d.open ? openEntries.add(d.dataset.entry) : openEntries.delete(d.dataset.entry); }));
        renderNodes();
        updateTotals();
    }
    function renderExpenses() {
        el('ltExpenseList').innerHTML = day.expenses.map(e => {
            const attr = ' data-e="' + esc(e.id) + '" ';
            const links = Object.fromEntries(day.activities.map(a => [a.id,(a.title || labels[a.category]) + ' · ' + labels[a.category]]));
            return '<details class="lt-entry lt-expense-entry"' + (openEntries.has(e.id) ? ' open' : '') + ' data-entry="' + e.id + '"><summary><span data-exp-label="' + e.id + '">' + esc(expenseNames()[e.category] || '选择类别') + (e.kind === 'refund' ? ' · 退款' : '') + '</span><small data-exp-value="' + e.id + '">¥ ' + yuan(e.amount_cents) + '</small></summary><div class="lt-entry-body"><div class="lt-form-grid">' +
                field('类型','<select' + attr + 'data-field="kind">' + options({expense:'消费',refund:'退款'},e.kind) + '</select>') +
                field('类别','<select' + attr + 'data-field="category" required>' + options(expenseNames(false,e.category),e.category,'请选择') + '</select>') +
                field('金额（元）','<input' + attr + 'data-field="amount" type="number" step="0.01" min="0.01" max="1000000000" inputmode="decimal" required value="' + esc(e._amount ?? yuan(e.amount_cents)) + '">') +
                field('备注（选填）','<input' + attr + 'data-field="note" maxlength="500" value="' + esc(e.note) + '">') +
                field('关联当天活动（选填）','<select' + attr + 'data-field="activity_id">' + options(links,e.activity_id,'不关联') + '</select>','lt-full') +
                '</div>' + (e.group_id ? '<p class="lt-note">已拆分账目，同组总额 ¥ ' + yuan(day.expenses.filter(x => x.group_id === e.group_id).reduce((n,x) => n + x.amount_cents,0)) + '</p>' : '') +
                '<div class="lt-entry-actions"><button type="button" class="lt-text-button" data-split="' + e.id + '">拆成两笔</button><button type="button" class="lt-text-button" data-remove-e="' + e.id + '">移除</button></div>' +
                (splitId === e.id ? '<div class="lt-split-form">' + field('分出金额（元）','<input id="ltSplitAmount" type="number" min="0.01" step="0.01" inputmode="decimal">') + '<p class="lt-note">剩余金额自动保留，拆分后分别选择类别。</p><button type="button" class="lt-text-button" data-split-confirm="' + e.id + '">确认拆分</button> <button type="button" class="lt-text-button" data-split-cancel="1">取消</button></div>' : '') + '</div></details>';
        }).join('') || '<p class="lt-note">记下每笔用途；没有消费时，勾选下方确认即可。</p>';
        el('ltExpenseList').querySelectorAll('[data-entry]').forEach(d => d.addEventListener('toggle', () => { d.open ? openEntries.add(d.dataset.entry) : openEntries.delete(d.dataset.entry); }));
        updateTotals();
    }
    function renderAttention() {
        day.attention_items ||= [];
        const confirmedNoWaste = day.attention_confirmed && !day.attention_items.length;
        el('ltAttentionList').innerHTML = confirmedNoWaste
            ? '<p class="lt-zero-confirmation">✓ 今天没有注意力浪费</p>'
            : day.attention_items.map((item,i) => '<div class="lt-attention-row"><input data-attention-index="' + i + '" data-attention-field="name" aria-label="注意力浪费事项" maxlength="60" placeholder="如：刷手机" required value="' + esc(item.name) + '"><div class="lt-minute-input"><input data-attention-index="' + i + '" data-attention-field="minutes" aria-label="注意力浪费分钟" type="number" min="0" max="1440" step="1" inputmode="numeric" placeholder="0" required value="' + esc(item.minutes) + '"><span>分</span></div><button type="button" aria-label="移除注意力浪费事项" data-remove-attention="' + i + '">×</button></div>').join('');
        el('ltNoAttention').hidden = confirmedNoWaste;
        el('ltAttentionTotal').textContent = time(day.attention_items.reduce((n,item) => n + (Number(item.minutes) || 0),0) * 60);
    }
    function newAttention() {
        day.attention_confirmed = false;
        day.attention_items ||= [];
        day.attention_items.push({name:'',minutes:''});
        const index = day.attention_items.length - 1;
        touch(); renderAttention();
        el('ltAttentionList').querySelector('[data-attention-index="' + index + '"][data-attention-field="name"]').focus();
    }
    function renderNodes() {
        const used = new Set(day.activities.map(a => a.source_node_id));
        el('ltNodeCount').textContent = day.nodes.length + ' 条';
        el('ltNodes').innerHTML = day.nodes.map(n => '<div class="lt-node"><div>' + esc(n.title) + '<small>' + time(n.seconds) + (used.has(n.id) ? ' · 已关联' : '') + '</small></div>' +
            (used.has(n.id) ? '' : '<select aria-label="' + esc(n.title) + '的归类" data-source="' + n.id + '">' + options(Object.fromEntries(keys.filter(k => k !== 'investment').map(k => [k,labels[k]])),'','选择后关联') + '</select>') + '</div>').join('') || '<p class="lt-note">当天还没有时间日志，可在上方直接记录。</p>';
    }
    function updateTotals() {
        if (!day) return;
        const totals = keys.map(k => day.activities.filter(a => a.category === k && !a.reader_duplicate_of && !a.source_missing && !a.work_duplicate_of && !a.work_excluded).reduce((n,a) => n + (k === 'investment' ? 0 : Number(a.seconds) || 0),0));
        const sum = totals.reduce((a,b) => a+b,0), max = Math.max(1,...totals);
        keys.forEach((key,i) => {
            const out = el('ltManual').querySelector('[data-total="' + key + '"]'), bar = el('ltManual').querySelector('[data-bar="' + key + '"]');
            if (out) out.textContent = !day.activities.some(a=>a.category===key&&!a.source_missing&&!a.reader_duplicate_of&&!a.work_duplicate_of&&!a.work_excluded)&&!day.category_confirmed?.includes(key)?'待记录':key === 'investment' ? '¥ ' + yuan(day.activities.filter(a => a.category === key).reduce((n,a) => n + (Number(a.amount_cents) || 0),0)) : time(totals[i]);
            if (bar) bar.style.width = totals[i] / max * 100 + '%';
        });
        el('ltTotalTime').textContent = time(sum);
        el('ltDistribution').innerHTML = totals.map((n,i) => '<span style="width:' + (sum ? n / sum * 100 : 0) + '%;background:' + colors[i] + '"></span>').join('');
        const unplanned = day.activities.filter(a => a.unplanned && !a.reader_duplicate_of && !a.source_missing && !a.work_duplicate_of && !a.work_excluded).reduce((n,a) => n + (Number(a.seconds) || 0),0);
        el('ltOverviewHint').textContent = day.activities.length + ' 条活动 · 其中非计划占用 ' + time(unplanned) + (dirty ? ' · 当前草稿' : '');
        const spending = day.expenses.filter(e => e.kind === 'expense').reduce((n,e) => n + (Number(e.amount_cents) || 0),0);
        const refunds = day.expenses.filter(e => e.kind === 'refund').reduce((n,e) => n + (Number(e.amount_cents) || 0),0);
        el('ltExpenseTotals').innerHTML = '<span>消费 ¥ ' + yuan(spending) + '</span><span>退款 ¥ ' + yuan(refunds) + '</span><strong>净支出 ¥ ' + yuan(spending-refunds) + '</strong>';
        if (el('ltAttentionTotal')) el('ltAttentionTotal').textContent = time((day.attention_items || []).reduce((n,item) => n + (Number(item.minutes) || 0),0) * 60);
    }
    function renderDay() {
        day.category_confirmed ||= day.day_confirmed?[...keys]:[];
        renderActivities(); renderAttention(); renderExpenses();
        el('ltDayConfirmed').checked = day.day_confirmed;
        el('ltExpenseConfirmed').checked = day.expense_confirmed;
        el('ltLegacy').innerHTML = day.legacy_investment_seconds ? '<p class="lt-note">旧版定投时长 ' + time(day.legacy_investment_seconds) + ' 已保留在历史数据中；新版定投统计金额。</p>' : '';
        status(dirty ? '有未保存的修改' : day.recorded ? '已保存' : '待记录',dirty ? 'is-dirty' : day.recorded ? 'is-saved' : '');
    }
    function newActivity(category, source = null) {
        const a = {id:uid(),category,title:source?.title || '',seconds:source?.seconds || 0,source_node_id:source?.id || null,
            reading_kind:category === 'reading' ? '' : 'unclassified',primary_topic:category === 'reading' ? '' : 'unclassified',
            topics:[],note:'',words:null,amount_cents:0,unplanned:false};
        if (!source && category !== 'investment') a._minutes = '';
        if (category === 'investment') a._amount = '';
        day.activities.push(a); openPanels.add(category); openEntries.add(a.id); touch(); renderActivities(); renderExpenses();
        el('ltManual').querySelector('[data-entry="' + a.id + '"] input')?.focus();
    }
    function newExpense() {
        const e = {id:uid(),category:'',kind:'expense',amount_cents:0,_amount:'',note:'',activity_id:null,group_id:null};
        day.expenses.push(e); openEntries.add(e.id); touch(); renderExpenses();
    }
    function validateControls(root) {
        const invalid = [...root.querySelectorAll('input,select,textarea')].find(x => !x.disabled && !x.checkValidity());
        if (!invalid) return;
        for (let p = invalid.parentElement; p; p = p.parentElement) if (p.tagName === 'DETAILS') p.open = true;
        invalid.focus(); invalid.reportValidity();
        throw new Error('请补全已展开记录中的必要字段。');
    }
    function serializeDay() {
        validateControls(el('ltDayFields'));
        const attention = (day.attention_items || []).map(item => ({name:String(item.name || '').trim(),minutes:Number(item.minutes)}));
        if (!attention.length && !day.attention_confirmed) throw new Error('请记录注意力浪费事项，或确认今天没有注意力浪费。');
        if (attention.length > 30 || attention.some(item => !item.name || !Number.isInteger(item.minutes) || item.minutes < 0 || item.minutes > 1440)) throw new Error('请检查注意力浪费事项和分钟数。');
        if (new Set(attention.map(item => item.name)).size !== attention.length) throw new Error('注意力浪费项目名称不能重复，请合并相同项目。');
        if (attention.reduce((sum,item) => sum + item.minutes,0) > 1440) throw new Error('注意力浪费合计不能超过 1440 分钟。');
        return {
            revision:day.revision,
            activities:day.activities.map(a => {
                const {source_missing,source_changed,work_source,reader_source,_minutes,_amount,...data} = a;
                if (data.category === 'investment') data.amount_cents = moneyCents(_amount ?? yuan(data.amount_cents));
                else if (!data.source_node_id && !data.reader_book_key) data.seconds = Math.round(Number(_minutes ?? data.seconds/60) * 60);
                return data;
            }),
            expenses:day.expenses.map(e => { const {_amount,...data} = e; data.amount_cents = moneyCents(_amount ?? yuan(e.amount_cents)); return data; }),
            expense_confirmed:day.expense_confirmed,day_confirmed:day.day_confirmed,category_confirmed:day.category_confirmed,
            attention_items:attention,attention_confirmed:Boolean(day.attention_confirmed || attention.length),
        };
    }
    async function loadDay(force = false) {
        if (busy || !el('ltDate').value) return;
        if (day && dirty) drafts.set(day.date,clone(day));
        const date = el('ltDate').value, request = ++dayRequest, epoch = sessionEpoch;
        day = null; el('ltDayFields').disabled = true; status('正在读取…');
        try {
            const data = await api('/day?day=' + date);
            if (!sameSession(epoch) || request !== dayRequest) return;
            day = !force && drafts.has(date) ? clone(drafts.get(date)) : data;
            dirty = !force && drafts.has(date);
            renderDay(); el('ltDayFields').disabled = false;
            window.ShuranFeedbackDaily?.load(day.date);
            window.ShuranWorkLinks?.history(day.date,async()=>{if(dirty){status('已导入。请保留草稿并重新读取核对，避免覆盖未保存修改。','is-dirty');return;}await loadDay(true);});
            el('ltSaveHint').textContent = dirty ? '已恢复本次会话草稿，保存前请核对。' : '修改后保存；活动、注意力和消费可以分别核对。';
        } catch(e) { if (request === dayRequest && sameSession(epoch)) status(e.message || '读取失败，请重试','is-error'); }
        if (view === 'report') loadReport();
    }
    async function saveDay() {
        if (!day || busy) return;
        if (!sameSession(sessionEpoch)) { window.loadLongTerm(); return; }
        let body;
        try { body = serializeDay(); } catch(e) { status(e.message,'is-error'); return; }
        const epoch = sessionEpoch, date = day.date;
        setBusy(true); status('正在保存…');
        try {
            const data = await api('/day?day=' + date,{method:'PUT',body:JSON.stringify(body)});
            if (!sameSession(epoch)) return;
            drafts.delete(date); day = data; dirty = false; renderDay();
            el('ltSaveHint').textContent = '已保存到服务器，报告已同步。';
            window.reminderNotificationService?.checkPendingReminders();
            try { const response = await api('/recent'); if (sameSession(epoch)) recent = response.items; }
            catch { /* Saving succeeded; recent suggestions can refresh on the next visit. */ }
        } catch(e) { if (sameSession(epoch)) { status('保存失败','is-error'); el('ltSaveHint').textContent = (e.message || '请重试') + ' 当前草稿仍保留，可先导出。'; } }
        finally {
            if (sameSession(epoch)) setBusy(false);
            else if (sessionToken !== localStorage.getItem('authToken')) { busy = false; window.loadLongTerm(); }
        }
    }
    function updateInput(target) {
        if(target.dataset.confirmCategory) {
            const key=target.dataset.confirmCategory;
            day.category_confirmed=target.checked?[...new Set([...day.category_confirmed,key])]:day.category_confirmed.filter(k=>k!==key);
            day.day_confirmed=day.category_confirmed.length===keys.length;el('ltDayConfirmed').checked=day.day_confirmed;
        } else if (target.dataset.a) {
            const a = day.activities.find(x => x.id === target.dataset.a);
            if (target.dataset.topic) {
                a.topics = target.checked ? [...new Set([...a.topics,target.dataset.topic])] : a.topics.filter(x => x !== target.dataset.topic);
                if (a.topics.length > 5) { a.topics.pop(); target.checked = false; status('补充主题最多选择 5 个','is-error'); return; }
            } else {
                const f = target.dataset.field;
                if (f === 'minutes') { a._minutes = target.value; a.seconds = Math.round(Number(target.value) * 60); if(a.work_session_id){a.work_override_seconds=a.seconds;a.work_basis_seconds=a.work_source?.seconds??0;} }
                else if (f === 'amount') { a._amount = target.value; try { a.amount_cents = moneyCents(target.value); } catch { a.amount_cents = 0; } }
                else if (f === 'words') a.words = target.value === '' ? null : Number(target.value);
                else if (f === 'work_duplicate_of') a.work_duplicate_of=target.value?Number(target.value):null;
                else if (f === 'reader_duplicate_of') a.reader_duplicate_of=target.value||null;
                else a[f] = target.type === 'checkbox' ? target.checked : target.value;
                if(f==='title'&&a.work_session_id)a.work_title_override=true;
                if(f==='category'&&a.work_session_id){touch();renderActivities();return;}
                if (f === 'primary_topic') a.topics = a.topics.filter(x => x !== a.primary_topic);
                if (f === 'title' && a.category === 'reading') {
                    const old = recent.find(x => x.category === 'reading' && x.title === a.title);
                    if (old) {
                        a.reading_kind = old.reading_kind; a.primary_topic = old.primary_topic; a.topics = clone(old.topics);
                        const wrapper = target.closest('.lt-entry');
                        wrapper.querySelector('[data-field="reading_kind"]').value = a.reading_kind;
                        wrapper.querySelector('[data-field="primary_topic"]').value = a.primary_topic;
                        wrapper.querySelectorAll('[data-topic]').forEach(c => c.checked = a.topics.includes(c.dataset.topic));
                    }
                }
            }
            const caption = el('ltManual').querySelector('[data-caption="' + a.id + '"]');
            const title = el('ltManual').querySelector('[data-title="' + a.id + '"]');
            if (caption) caption.textContent = activityCaption(a);
            if (title) title.textContent = a.title || '填写一条' + labels[a.category] + '记录';
        } else if (target.dataset.e) {
            const e = day.expenses.find(x => x.id === target.dataset.e), f = target.dataset.field;
            if (f === 'amount') { e._amount = target.value; try { e.amount_cents = moneyCents(target.value); } catch { e.amount_cents = 0; } }
            else e[f] = f === 'activity_id' ? target.value || null : target.value;
            el('ltExpenseList').querySelector('[data-exp-label="' + e.id + '"]').textContent = (expenseNames()[e.category] || '选择类别') + (e.kind === 'refund' ? ' · 退款' : '');
            el('ltExpenseList').querySelector('[data-exp-value="' + e.id + '"]').textContent = '¥ ' + yuan(e.amount_cents);
        } else if (target.dataset.attentionIndex !== undefined) {
            const item = day.attention_items[Number(target.dataset.attentionIndex)];
            item[target.dataset.attentionField] = target.value;
        } else if (target.id === 'ltDayConfirmed') {day.day_confirmed = target.checked;day.category_confirmed=target.checked?[...keys]:[];el('ltManual').querySelectorAll('[data-confirm-category]').forEach(c=>c.checked=target.checked);}
        else if (target.id === 'ltExpenseConfirmed') day.expense_confirmed = target.checked;
        else return;
        touch();
    }
    function dayAction(target) {
        const b = target.closest('button');
        if (!b || !day || busy) return;
        if(b.dataset.workSource) {
            if(dirty){status('请先保存当前修改，再更正原工作片，避免丢失草稿。','is-dirty');return;}
            return window.ShuranWorkLinks?.correct(Number(b.dataset.workSource),()=>loadDay(true));
        }
        if(b.dataset.workRestore || b.dataset.workExclude) {
            const a=day.activities.find(x=>x.id===(b.dataset.workRestore||b.dataset.workExclude));
            if(b.dataset.workRestore){a.work_override_seconds=null;a.work_basis_seconds=null;a.work_title_override=false;delete a._minutes;a.seconds=a.work_source?.seconds||0;}
            else a.work_excluded=!a.work_excluded;
            touch();renderActivities();return;
        }
        if (b.dataset.addA) return newActivity(b.dataset.addA);
        if (b.dataset.removeA) {
            day.activities = day.activities.filter(a => a.id !== b.dataset.removeA);
            day.expenses.forEach(e => { if (e.activity_id === b.dataset.removeA) e.activity_id = null; });
            touch(); renderActivities(); renderExpenses();
        } else if (b.dataset.detach) {
            const a = day.activities.find(a => a.id === b.dataset.detach); a.source_node_id = null; a.source_missing = false;
            touch(); renderActivities();
        } else if (b.dataset.removeE) {
            day.expenses = day.expenses.filter(e => e.id !== b.dataset.removeE); touch(); renderExpenses();
        } else if (b.dataset.split) {
            splitId = b.dataset.split; openEntries.add(splitId); renderExpenses(); el('ltSplitAmount').focus();
        } else if (b.dataset.splitCancel) {
            splitId = null; renderExpenses();
        } else if (b.dataset.splitConfirm) {
            const e = day.expenses.find(e => e.id === b.dataset.splitConfirm);
            const answer = el('ltSplitAmount').value;
            try {
                const n = moneyCents(answer);
                if (n <= 0 || n >= e.amount_cents) throw new Error('拆分金额必须大于 0 且小于原金额。');
                e.group_id ||= uid();
                const other = {...e,id:uid(),amount_cents:n,_amount:yuan(n)};
                e.amount_cents -= n; e._amount = yuan(e.amount_cents);
                day.expenses.push(other); openEntries.add(e.id); openEntries.add(other.id);
                splitId = null; touch(); renderExpenses();
            } catch(error) { status(error.message,'is-error'); }
        } else if (b.dataset.removeAttention !== undefined) {
            day.attention_items.splice(Number(b.dataset.removeAttention),1);
            if (!day.attention_items.length) day.attention_confirmed = false;
            touch(); renderAttention();
        }
    }
    function goalUnit(g) { return g.metric === 'seconds' ? '分钟' : g.metric === 'cents' ? '元' : g.metric === 'words' ? '字' : '条记录'; }
    function goalValue(g,n) { return g.metric === 'seconds' ? time(n) : g.metric === 'cents' ? '¥ ' + yuan(n) : n + ' ' + goalUnit(g); }
    function targetTitle(g,names) {
        return (g.category === 'expense' ? (names[g.expense_category] || '全部消费') + '预算' : labels[g.category]) +
            (g.reading_kind ? ' · ' + kinds[g.reading_kind] : '') + (g.topic ? ' · ' + preferences.topics[g.topic] : '');
    }
    function renderSettings() {
        const names = Object.fromEntries(settingsDraft.expense_categories.map(c => [c.id,c.name]));
        el('ltGoals').innerHTML = settingsDraft.goals.map(g => {
            const attr = ' data-g="' + esc(g.id) + '" ';
            const metricOptions = g.category === 'expense' ? {cents:'金额（元）'} : g.category === 'investment' ? {cents:'金额（元）',count:'记录条数'} : {seconds:'时长（分钟）',count:'记录条数',...(g.category === 'writing' ? {words:'字数'} : {})};
            return '<div class="lt-goal-editor"><div class="lt-form-grid">' +
                field('方向','<select' + attr + 'data-field="category">' + options({...labels,expense:'消费预算'},g.category) + '</select>') +
                field('周期','<select' + attr + 'data-field="period">' + options({week:'每周',month:'每月',quarter:'每季',year:'每年'},g.period) + '</select>') +
                field('单位','<select' + attr + 'data-field="metric">' + options(metricOptions,g.metric) + '</select>') +
                field('目标值（' + goalUnit(g) + '）','<input' + attr + 'data-field="target" type="number" min="' + (g.metric === 'cents' ? '0.01' : '1') + '" step="' + (g.metric === 'cents' ? '0.01' : '1') + '" required value="' + esc(g._target ?? (g.metric === 'seconds' ? g.target/60 : g.metric === 'cents' ? yuan(g.target) : g.target)) + '">') +
                (g.category === 'reading' ? field('阅读类型','<select' + attr + 'data-field="reading_kind">' + options(kinds,g.reading_kind,'全部类型') + '</select>') + field('主主题','<select' + attr + 'data-field="topic">' + options(preferences.topics,g.topic,'全部主题') + '</select>') : '') +
                (g.category === 'expense' ? field('预算分类','<select' + attr + 'data-field="expense_category">' + options(names,g.expense_category,'全部消费') + '</select>') : '') +
                field('开始日期','<input' + attr + 'data-field="start_date" type="date" required value="' + esc(g.start_date) + '">') +
                field('结束日期（选填）','<input' + attr + 'data-field="end_date" type="date" value="' + esc(g.end_date || '') + '">') +
                '</div><button type="button" class="lt-text-button" data-remove-g="' + g.id + '">移除此目标</button></div>';
        }).join('') || '<p class="lt-note">尚未设置目标，可先从一个方向开始。</p>';
        el('ltCategories').innerHTML = settingsDraft.expense_categories.map(c => '<div class="lt-category-editor">' +
            '<input aria-label="消费分类名称" maxlength="30" required data-c="' + c.id + '" value="' + esc(c.name) + '"' + (c.id === 'unclassified' ? ' disabled' : '') + '>' +
            '<label class="lt-check"><input type="checkbox" data-archive-c="' + c.id + '"' + (c.archived ? ' checked' : '') + (c.id === 'unclassified' ? ' disabled' : '') + '>停用</label></div>').join('');
        const locked = !!preferences.premium_locked;
        el('ltGoalGate').hidden = !locked;
        el('ltAddGoal').disabled = locked;
        el('ltGoals').querySelectorAll('input,select,button').forEach(control => { control.disabled = locked; });
    }
    function settingsInput(t) {
        if (t.dataset.g) {
            const g = settingsDraft.goals.find(g => g.id === t.dataset.g), f = t.dataset.field;
            if (f === 'target') { g._target = t.value; }
            else {
                g[f] = ['reading_kind','topic','expense_category','end_date'].includes(f) ? t.value || null : t.value;
                if (f === 'category') {
                    g.metric = ['expense','investment'].includes(g.category) ? 'cents' : 'seconds'; g._target = ''; g.target = 0;
                    g.reading_kind = null; g.topic = null; g.expense_category = null;
                }
                if (f === 'metric') { g._target = ''; g.target = 0; }
                if (f === 'category' || f === 'metric') renderSettings();
            }
        } else if (t.dataset.c) settingsDraft.expense_categories.find(c => c.id === t.dataset.c).name = t.value;
        else if (t.dataset.archiveC) settingsDraft.expense_categories.find(c => c.id === t.dataset.archiveC).archived = t.checked;
        else return;
        settingsDirty = true; el('ltSettingsStatus').textContent = '设置有未保存的修改。';
    }
    async function saveSettings() {
        if (settingsBusy || !settingsDraft) return;
        if (!sameSession(sessionEpoch)) { window.loadLongTerm(); return; }
        let body;
        try {
            validateControls(el('ltSettingsFields'));
            body = {
                revision:settingsDraft.revision,expense_categories:settingsDraft.expense_categories,
                goals:settingsDraft.goals.map(g => {
                    const {_target,...data} = g;
                    if (_target !== undefined) data.target = g.metric === 'cents' ? moneyCents(_target) : Number(_target) * (g.metric === 'seconds' ? 60 : 1);
                    return data;
                }),
            };
        } catch(e) { el('ltSettingsStatus').textContent = e.message; return; }
        const epoch = sessionEpoch;
        settingsBusy = true; el('ltSettingsFields').disabled = true; el('ltSaveSettings').disabled = true;
        try {
            const result = await api('/preferences',{method:'PUT',body:JSON.stringify(body)});
            if (!sameSession(epoch)) return;
            preferences = result; settingsDraft = clone(result); settingsDirty = false;
            renderSettings(); if (day) { renderActivities(); renderExpenses(); }
            el('ltSettingsStatus').textContent = '目标与分类已保存。';
        } catch(e) { if (sameSession(epoch)) el('ltSettingsStatus').textContent = (e.message || '保存失败') + ' 设置草稿仍保留。'; }
        finally {
            if (sameSession(epoch)) { settingsBusy = false; el('ltSettingsFields').disabled = false; el('ltSaveSettings').disabled = false; }
            else if (sessionToken !== localStorage.getItem('authToken')) { settingsBusy = false; window.loadLongTerm(); }
        }
    }
    function reportRows(items, withIds) {
        return items.map(a => '<tr' + (withIds ? ' id="lt-record-' + esc(a.date + '-' + a.id) + '"' : '') + '><td><button type="button" class="lt-text-button" data-day="' + a.date + '">' + a.date + '</button></td><td>' + esc(a.title || '未填写名称') +
            (a.category === 'reading' ? '<small>' + kinds[a.reading_kind] + ' · ' + esc(preferences.topics[a.primary_topic]) + (a.topics.length ? '；补充：' + a.topics.map(t => esc(preferences.topics[t])).join('、') : '') + '</small>' : '') +
            '</td><td>' + (a.source_missing ? '源日志已移除' : activityCaption(a)) + (a.unplanned ? '<small>非计划占用</small>' : '') +
            '</td><td class="lt-note-cell">' + esc(a.note) +
            ((displayedReport?.expenses || []).some(e => e.date === a.date && e.activity_id === a.id) ? '<small><button type="button" class="lt-text-button" data-exp-activity="' + esc(a.date + '-' + a.id) + '">查看关联账目</button></small>' : '') + '</td></tr>').join('');
    }
    function reportTable(items, withIds = false) {
        return '<div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>日期</th><th>内容</th><th>投入／产出</th><th>感受与补充</th></tr></thead><tbody>' + reportRows(items, withIds) + '</tbody></table></div>';
    }
    function attentionSection(r) {
        const entries = Object.entries(r.attention_by_name || {}).filter(([,minutes]) => Number(minutes) > 0).sort((a,b) => b[1]-a[1]);
        const checked = Number(r.attention_confirmed_days || 0), elapsed = Number(r.elapsed_days || 0);
        const total = Number(r.attention_waste_minutes ?? r.attention_minutes ?? 0);
        const rows = entries.map(([name,minutes]) => '<div class="lt-attention-summary"><span>' + esc(name) + '</span><strong>' + time(minutes * 60) + '</strong></div>').join('');
        return '<section class="lt-report-section"><h2>注意力浪费</h2><p class="lt-note">只汇总单独登记的分心事项；活动中的非计划占用仍按活动时长单独展示。</p>' +
            '<div class="lt-attention-summary"><span>累计注意力浪费 · 已核对 ' + checked + '／' + elapsed + ' 天</span><strong>' + (checked ? time(total * 60) : '未记录') + '</strong></div>' +
            (rows || '<p class="lt-note">' + (checked ? '已核对的日期没有记录注意力浪费。' : '完成每日核对后，这里会汇总分心事项。') + '</p>') + '</section>';
    }
    function renderReport(r) {
        displayedReport = r;
        if (r.premium_locked) {
            renderFreeReport(r);
            el('ltReport').insertAdjacentHTML('beforeend',globalThis.ShuranPractice?.reportHTML(r.practice)||'');
            enhanceReport(r);
            return;
        }
        const total = Object.values(r.total_seconds).reduce((a,b) => a+b,0);
        const names = r.expense_category_names;
        const topicEntries = Object.entries(r.topics).sort((a,b) => b[1].seconds-a[1].seconds), readingTotal = r.total_seconds.reading;
        const topicMax = Math.max(1,...topicEntries.map(([,v]) => v.seconds));
        const topicHTML = topicEntries.map(([k,v]) => '<details class="lt-report-detail"><summary><span>' + esc(r.topic_names[k]) + '</span><span class="lt-report-track"><i style="width:' + v.seconds/topicMax*100 + '%"></i></span><strong>' + time(v.seconds) + ' · ' + (readingTotal ? (v.seconds/readingTotal*100).toFixed(1) : '0') + '%</strong></summary>' +
            reportTable(r.activities.filter(a => a.category === 'reading' && a.primary_topic === k)) + '</details>').join('');
        const expenseRows = Object.entries(r.expense_categories).sort((a,b) => b[1].expense_cents-a[1].expense_cents);
        const expenseMax = Math.max(1,...expenseRows.map(([,v]) => v.expense_cents));
        const expenseTable = expenseRows.map(([k,v]) => '<tr><td><button type="button" class="lt-text-button" data-exp-filter="' + esc(k) + '">' + esc(names[k] || k) + '</button><div class="lt-mini-bar"><i style="width:' + v.expense_cents/expenseMax*100 + '%"></i></div></td><td>¥ ' + yuan(v.expense_cents) + '</td><td>¥ ' + yuan(v.refund_cents) + '</td><td>¥ ' + yuan(v.net_cents) + '</td><td>' + (r.expense_cents ? (v.expense_cents/r.expense_cents*100).toFixed(1) : '0') + '%</td></tr>').join('');
        const transactionRows = r.expenses.map(e => {
            const a = r.activities.find(a => a.date === e.date && a.id === e.activity_id);
            return '<tr data-exp-category="' + esc(e.category) + '" data-linked-activity="' + esc(e.date + '-' + (e.activity_id || '')) + '"><td><button type="button" class="lt-text-button" data-day="' + e.date + '">' + e.date + '</button></td><td>' + esc(names[e.category] || e.category) + '</td><td>' + (e.kind === 'refund' ? '退款' : '消费') + ' ¥ ' + yuan(e.amount_cents) + '</td><td>' + esc(e.note) +
                (a ? '<small><button type="button" class="lt-text-button" data-activity-link="' + esc(e.date + '-' + a.id) + '">活动：' + esc(a.title || labels[a.category]) + '</button></small>' : '') + '</td></tr>';
        }).join('');
        const groups = keys.map((k,i) => {
            const records = r.activities.filter(a => a.category === k), groups = r.activity_groups[k] || {};
            return '<details class="lt-report-detail lt-board-detail"><summary><span>' + labels[k] + '</span><strong>' + (k === 'investment' ? '¥ ' + yuan(r.investment_cents) : time(r.total_seconds[k])) + (k === 'writing' ? ' · ' + r.words + ' 字' : '') + '</strong><small>' + r.counts[k] + ' 条记录</small></summary>' +
                (records.length ? '<div class="lt-group-chips">' + Object.entries(k === 'investment' ? r.investments : groups).map(([name,v]) => '<span>' + esc(name) + ' · ' + (k === 'investment' ? '¥ '+yuan(v) : time(v.seconds)) + '</span>').join('') + '</div>' + reportTable(records, true) : '<p class="lt-note">本周期尚无已记录活动。</p>') + '</details>';
        }).join('');
        const c = r.comparison;
        const compareMetrics = [
            ['时间投入',x => Object.values(x.total_seconds).reduce((a,b)=>a+b,0),time],
            ['写作字数',x=>x.words,n=>n+' 字'],['消费净支出',x=>x.money_cents,n=>'¥ '+yuan(n)],
            ['定投投入',x=>x.investment_cents,n=>'¥ '+yuan(n)],
        ];
        const comparison = c.days ? '<p class="lt-note">' + c.start + '～' + c.end + ' 对比 ' + c.previous_start + '～' + c.previous_end + '，各 ' + c.days + ' 天。消费已确认 ' + c.current.expense_confirmed_days + '／' + c.days + ' 天，对比期 ' + c.previous.expense_confirmed_days + '／' + c.days + ' 天；漏记会影响比较。</p><div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>指标</th><th>本期等长区间</th><th>上期等长区间</th><th>差额</th></tr></thead><tbody>' +
            compareMetrics.map(([name,get,format]) => {
                const a=get(c.current),b=get(c.previous);
                const has = x => name === '消费净支出' ? x.expense_record_count || x.expense_confirmed_days : x.activity_record_count || x.day_confirmed_days;
                return '<tr><td>'+name+'</td><td>'+(has(c.current)?format(a):'未记录')+'</td><td>'+(has(c.previous)?format(b):'未记录')+'</td><td>'+(has(c.current)&&has(c.previous)?(a-b>0?'+':'')+format(a-b):'—')+'</td></tr>';
            }).join('') + '</tbody></table></div>' : '<p class="lt-note">所选周期尚未开始。</p>';
        const goals = r.goals.map(g => '<div class="lt-goal-progress"><div><strong>' + esc(targetTitle(g,names)) + '</strong><span>' + goalValue(g,g.actual) + ' / ' + goalValue(g,g.target) + '</span></div><progress max="' + g.target + '" value="' + Math.max(0,Math.min(g.actual,g.target)) + '"></progress><p class="lt-note">每' + periods[g.period] + ' · ' + g.start + '～' + g.end + '（周期结束 ' + g.period_end + '） · 已确认 ' + g.confirmed_days + '／' + g.elapsed_days + ' 天' + (g.category === 'expense' ? ' · ' + (g.actual > g.target ? '超出预算 ¥ '+yuan(g.actual-g.target) : '预算剩余 ¥ '+yuan(g.target-g.actual)) : '') + '</p></div>').join('');
        const trend = r.trend.map(t => '<tr><td>' + t.label + '</td><td>' + (t.activity_record_count || t.day_confirmed_days ? time(Object.values(t.total_seconds).reduce((a,b)=>a+b,0)) : '未记录') + '</td><td>' + (t.attention_confirmed_days ? time(t.attention_waste_minutes * 60) : '未记录') + '</td><td>' + (t.counts.writing || t.day_confirmed_days ? t.words : '未记录') + '</td><td>' + (t.expense_record_count || t.expense_confirmed_days ? '¥ ' + yuan(t.money_cents) : '未记录') + '</td><td>' + t.expense_confirmed_days + '</td></tr>').join('');
        el('ltReport').innerHTML =
            '<p class="lt-report-range">' + r.start + ' — ' + r.end + '<span>活动核对 ' + r.day_confirmed_days + '／' + r.elapsed_days + ' 天 · 注意力核对 ' + r.attention_confirmed_days + '／' + r.elapsed_days + ' 天 · 消费核对 ' + r.expense_confirmed_days + '／' + r.elapsed_days + ' 天</span></p>' +
            (dirty || drafts.size ? '<p class="lt-note lt-notice">有尚未保存的每日记录，本报告展示服务器已保存数据。</p>' : '') +
            '<div class="lt-report-metrics"><div><span>时间投入</span><strong>' + (r.activity_record_count || r.day_confirmed_days ? time(total) : '未记录') + '</strong></div><div><span>注意力浪费</span><strong>' + (r.attention_confirmed_days ? time(r.attention_waste_minutes * 60) : '未记录') + '</strong></div><div><span>写作产出</span><strong>' + r.words + ' 字</strong></div><div><span>消费净支出 · 已记录金额</span><strong>' + (r.expense_record_count || r.expense_confirmed_days ? '¥ ' + yuan(r.money_cents) : '未记录') + '</strong></div><div><span>定投累计投入</span><strong>¥ ' + yuan(r.investment_cents) + '</strong></div></div>' +
            '<section class="lt-report-section"><h2>阅读地图</h2><p class="lt-note">按主主题分配阅读时长。主题反映这段时间的阅读选择，不据此推断人格。</p><div class="lt-reading-types">' + Object.entries(r.reading).map(([k,v]) => '<span>' + kinds[k] + '<strong>' + time(v.seconds) + '</strong><small>' + v.count + ' 条记录</small></span>').join('') + '</div>' +
            (topicHTML || '<p class="lt-note">记录书籍的类型和主题后，这里会显示阅读分布。</p>') +
            (Object.keys(r.secondary_topics).length ? '<p class="lt-note">补充主题涉及记录数（可重叠）：' + Object.entries(r.secondary_topics).map(([k,n]) => esc(r.topic_names[k])+' '+n+' 条').join(' · ') + '</p>' : '') + '</section>' +
            attentionSection(r) +
            '<section class="lt-report-section"><h2>消费分类</h2><p class="lt-note">消费 ¥ ' + yuan(r.expense_cents) + ' − 退款 ¥ ' + yuan(r.refund_cents) + ' = 净支出 ¥ ' + yuan(r.money_cents) + '。退款按实际到账日统计，比例以消费总额为分母。</p>' +
            '<div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>类别 · 点击看账目</th><th>消费</th><th>退款</th><th>净支出</th><th>消费占比</th></tr></thead><tbody>' + (expenseTable || '<tr><td colspan="5">本周期没有已记录账目；请结合核对天数判断是否漏记。</td></tr>') + '</tbody></table></div>' +
            '<details id="ltReportExpenses" class="lt-report-detail"><summary><span>消费与退款明细</span><small>' + r.expenses.length + ' 笔</small></summary><button type="button" class="lt-text-button" data-exp-filter="">显示全部类别</button><p id="ltExpenseFilterLabel" class="lt-note"></p><div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>日期</th><th>类别</th><th>金额</th><th>备注与关联活动</th></tr></thead><tbody>' + transactionRows + '</tbody></table></div></details></section>' +
            '<section class="lt-report-section"><h2>各板块记录</h2>' + groups + '<p class="lt-note">其中非计划占用 ' + time(r.unplanned_seconds) + '，已包含在活动总时长内。' + (r.source_missing_count ? '有 '+r.source_missing_count+' 条源日志已移除或变更日期，描述保留，暂不计时。' : '') + '</p></section>' +
            '<section class="lt-report-section"><h2>目标与预算进展</h2>' + (goals || '<p class="lt-note">当前日期没有适用目标，可在“目标与分类”中设置。</p>') + '</section>' +
            '<section class="lt-report-section"><h2>与上一周期比较</h2>' + comparison + '</section>' +
            '<details class="lt-report-detail"><summary><span>周期内趋势</span><small>' + (['year','quarter'].includes(r.period) ? '按月' : '按日') + '</small></summary><div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>日期</th><th>时间投入</th><th>注意力浪费</th><th>写作字数</th><th>消费净支出</th><th>消费核对天数</th></tr></thead><tbody>' + trend + '</tbody></table></div></details>' +
            '<section class="lt-report-section"><h2>消费记录足迹</h2><div class="lt-report-calendar">' + r.days.map(d => '<button type="button" data-day="' + d.date + '" class="' + (d.expense_confirmed ? 'is-recorded' : d.recorded ? 'is-partial' : '') + '" title="' + d.date + (d.expense_confirmed ? ' 消费已核对' : d.recorded ? '有记录，消费待核对' : '未记录') + '">' + d.date.slice(5).replace('-','/') + '</button>').join('') + '</div><p class="lt-note">深绿：消费已核对；浅褐：有记录待核对；浅灰：未记录。未来日期不计入已过天数。点击日期可补记。</p></section>';
        el('ltReport').insertAdjacentHTML('beforeend',globalThis.ShuranPractice?.reportHTML(r.practice)||'');
        enhanceReport(r);
    }
    function enhanceReport(r) {
        window.ShuranFeedbackReports?.render(r,el('ltReport'));
    }
    function renderFreeReport(r) {
        const total = Object.values(r.total_seconds || {}).reduce((a,b) => a + b, 0);
        const names = r.expense_category_names || {};
        const spending = Object.entries(r.expense_categories || {}).map(([key,value]) =>
            '<tr><td>' + esc(names[key] || key) + '</td><td>¥ ' + yuan(value.expense_cents) + '</td><td>¥ ' + yuan(value.refund_cents) + '</td><td>¥ ' + yuan(value.net_cents) + '</td></tr>').join('');
        const reading = Object.entries(r.reading || {}).map(([key,value]) =>
            '<span>' + esc(kinds[key] || key) + '<strong>' + time(value.seconds) + '</strong><small>' + value.count + ' 条记录</small></span>').join('');
        const boards = keys.map(key => '<div class="lt-attention-summary"><span>' + labels[key] + '</span><strong>' +
            (key === 'investment' ? '¥ ' + yuan(r.investment_cents) : time((r.total_seconds || {})[key])) +
            ' · ' + ((r.counts || {})[key] || 0) + ' 条</strong></div>').join('');
        el('ltReport').innerHTML =
            '<p class="lt-report-range">' + esc(r.start) + ' — ' + esc(r.end) + '<span>活动核对 ' + r.day_confirmed_days + '／' + r.elapsed_days + ' 天 · 注意力核对 ' + r.attention_confirmed_days + '／' + r.elapsed_days + ' 天 · 消费核对 ' + r.expense_confirmed_days + '／' + r.elapsed_days + ' 天</span></p>' +
            (dirty || drafts.size ? '<p class="lt-note lt-notice">有尚未保存的每日记录，本报告展示服务器已保存数据。</p>' : '') +
            '<div class="lt-report-metrics"><div><span>时间投入</span><strong>' + (r.activity_record_count || r.day_confirmed_days ? time(total) : '未记录') + '</strong></div><div><span>注意力浪费</span><strong>' + (r.attention_confirmed_days ? time(r.attention_waste_minutes * 60) : '未记录') + '</strong></div><div><span>写作产出</span><strong>' + r.words + ' 字</strong></div><div><span>消费净支出 · 已记录金额</span><strong>' + (r.expense_record_count || r.expense_confirmed_days ? '¥ ' + yuan(r.money_cents) : '未记录') + '</strong></div><div><span>定投累计投入</span><strong>¥ ' + yuan(r.investment_cents) + '</strong></div></div>' +
            '<section class="lt-report-section"><h2>各方向投入</h2>' + boards + '</section>' +
            attentionSection(r) +
            '<section class="lt-report-section"><h2>阅读类型</h2><div class="lt-reading-types">' + reading + '</div></section>' +
            '<section class="lt-report-section"><h2>消费分类</h2><p class="lt-note">按已记录账目汇总；未核对的日期可能有漏记。</p><div class="lt-table-wrap"><table class="lt-table"><thead><tr><th>类别</th><th>消费</th><th>退款</th><th>净支出</th></tr></thead><tbody>' + (spending || '<tr><td colspan="4">本周期没有已记录消费。</td></tr>') + '</tbody></table></div></section>' +
            '<div class="lt-premium-gate"><strong>把一周的记录连成更长的线索</strong><p>月报、季报、年报、阅读主题地图、账目明细、目标预算与跨期对比属于付费深度复盘。你的记录会保留，开通后可继续分析。</p><button type="button" class="lt-text-button" data-upgrade>查看套餐与开通方式 →</button></div>';
    }
    async function loadReport() {
        const request = ++reportRequest, epoch = sessionEpoch, selected = period, date = el('ltDate').value;
        el('ltReport').innerHTML = '<p class="lt-note">正在汇总…</p>';
        try {
            const report = await api('/report?period=' + selected + '&anchor=' + date);
            if (!sameSession(epoch) || request !== reportRequest || view !== 'report') return;
            renderReport(report);
        } catch(e) {
            if (!sameSession(epoch) || request !== reportRequest) return;
            el('ltReport').innerHTML = e.status === 403
                ? '<div class="lt-premium-gate"><strong>' + periods[selected] + '报属于付费深度复盘</strong><p>开通月卡或学期卡后即可查看。记录、日报、周报和个人数据导出继续可用。</p><button type="button" class="lt-text-button" data-upgrade>查看套餐与开通方式 →</button></div>'
                : '<p class="lt-note">' + esc(e.message || '报告读取失败，请重试。') + '</p>';
        }
    }
    function switchView(next) {
        view = next;
        el('ltDailyPanel').hidden = view !== 'daily'; el('ltReportPanel').hidden = view !== 'report'; el('ltSettingsPanel').hidden = view !== 'settings';
        document.querySelectorAll('[data-lt-view]').forEach(b => { const on = b.dataset.ltView === view; b.classList.toggle('active',on); b.setAttribute('aria-pressed',on); });
        if (view === 'report' && preferences) loadReport();
        if (view === 'settings' && preferences) renderSettings();
    }
    function downloadDraft() {
        if (!day && !settingsDraft) return;
        const blob = new Blob([JSON.stringify({day,settings:settingsDirty ? settingsDraft : undefined},null,2)],{type:'application/json'});
        const link=document.createElement('a'), url=URL.createObjectURL(blob); link.href=url; link.download='书然-未保存草稿-'+(day?.date || today())+'.json'; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    window.prepareDailyFeedback = function (section) {
        const feedback = section === 'daily-feedback';
        const page = document.querySelector('.lt-page');
        el(section).appendChild(page);
        page.classList.toggle('is-daily-feedback', feedback);
        el('ltPageTitle').textContent = feedback ? '每日反馈' : '长期目标';
        el('ltFeedbackEntry').hidden = feedback;
        el('ltGoalsEntry').hidden = !feedback;
        ['dailyFeedbackIntro','dailyFeedbackJump','dailyFeedbackReport'].forEach(id => el(id).hidden = !feedback);
        el('feedbackDaily').hidden = false;
        document.querySelector('[data-lt-view="daily"]').textContent = feedback ? '填写反馈' : '每日记录';
    };
    window.loadLongTerm = async function () {
        if (!el('ltDate')) return;
        el('dailyFeedbackReport').onclick = () => {
            period = 'day';
            document.querySelectorAll('[data-period]').forEach(b => {const on=b.dataset.period==='day';b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
            switchView('report');
            el('ltReportPanel').scrollIntoView({block:'start',behavior:'smooth'});
        };
        document.querySelectorAll('[data-feedback-jump]').forEach(b => b.onclick = e => {e.preventDefault();el(b.dataset.feedbackJump).scrollIntoView({block:'start',behavior:'smooth'});});
        const token = localStorage.getItem('authToken');
        if (sessionToken !== token) {
            window.ShuranFeedbackDaily?.clear();
            sessionToken = token; sessionEpoch++; dayRequest++; reportRequest++;
            drafts.clear(); day=null; preferences=null; settingsDraft=null; recent=[]; displayedReport=null; dirty=false; settingsDirty=false;
            busy=false; settingsBusy=false; splitId=null; setBusy(false);
            openPanels.clear(); openEntries.clear();
            ['ltManual','ltExpenseList','ltNodes','ltLegacy','ltReport','ltGoals','ltCategories','ltExpenseTotals'].forEach(id=>el(id).innerHTML='');
            el('ltDayFields').disabled=true; el('ltSettingsFields').disabled=true;
            el('ltSaveSettings').disabled=false; el('ltTotalTime').textContent='—';
            el('ltDistribution').innerHTML=''; el('ltOverviewHint').textContent='';
            el('ltSettingsStatus').textContent=''; el('ltSaveHint').textContent='';
        }
        if (busy) return;
        if (!token) { status('请登录后记录'); return; }
        const url = new URL(window.location.href);
        if (url.searchParams.get('record') === 'today') {
            el('ltDate').value = today();
            switchView('daily');
            url.searchParams.delete('record');
            window.history.replaceState(null, '', url);
        }
        else if (/^\d{4}-\d{2}-\d{2}$/.test(url.searchParams.get('record')||'')) {
            el('ltDate').value=url.searchParams.get('record');url.searchParams.delete('record');
            if (periods[url.searchParams.get('report')]) {period=url.searchParams.get('report');url.searchParams.delete('report');document.querySelectorAll('[data-period]').forEach(b=>{b.classList.toggle('active',b.dataset.period===period);b.setAttribute('aria-pressed',String(b.dataset.period===period));});switchView('report');}
            else switchView('daily');
            window.history.replaceState(null,'',url);
        }
        const epoch=sessionEpoch; el('ltDate').value ||= today();
        try {
            if (!preferences) {
                const [p,r] = await Promise.all([api('/preferences'),api('/recent')]);
                if (!sameSession(epoch)) return;
                preferences=p; settingsDraft=clone(p); recent=r.items; el('ltSettingsFields').disabled=false;
            }
            await loadDay();
            if (view==='settings') renderSettings();
        } catch(e) { if(sameSession(epoch)) status(e.message || '读取失败，请重试','is-error'); }
    };
    window.openLongTermToday = function () {
        if (busy) { status('正在保存，请稍后打开今日记录。'); return; }
        const url = new URL(window.location.href);
        url.searchParams.set('record', 'today');
        window.history.replaceState(null, '', url);
        window.navigateTo('long-term');
    };
    document.addEventListener('DOMContentLoaded',() => {
        if (!el('ltDate')) return;
        el('ltReminderSettings').onclick = () => {
            window.navigateTo('user-center');
            document.querySelector('.record-reminder-settings')?.scrollIntoView({block:'center',behavior:'smooth'});
        };
        el('ltDate').onchange=()=>loadDay();
        ['ltPrevDay','ltNextDay'].forEach((id,i)=>el(id).onclick=()=>{
            const d=new Date(el('ltDate').value+'T12:00:00'); d.setDate(d.getDate()+(i?1:-1));
            el('ltDate').value=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); loadDay();
        });
        el('ltDayFields').addEventListener('input',e=>updateInput(e.target));
        el('ltDayFields').addEventListener('click',e=>dayAction(e.target));
        el('ltDayFields').addEventListener('change',e=>{
            if(e.target.dataset.source && e.target.value) newActivity(e.target.value,day.nodes.find(n=>n.id===Number(e.target.dataset.source)));
            // Refresh links after a title edit without disrupting typing.
            if(e.target.dataset.a && e.target.dataset.field==='title') renderExpenses();
        });
        el('ltAddAttention').onclick=newAttention;
        el('ltNoAttention').onclick=()=>{if(!day || busy)return;day.attention_items=[];day.attention_confirmed=true;touch();renderAttention();};
        el('ltAddExpense').onclick=newExpense; el('ltSave').onclick=saveDay; el('ltDraftExport').onclick=downloadDraft;
        el('ltReload').onclick=()=>{
            if(dirty && !window.confirm('重新读取将丢弃当前日期的未保存修改。需要保留时，请先导出草稿。'))return;
            drafts.delete(el('ltDate').value); dirty=false; loadDay(true);
        };
        document.querySelectorAll('[data-lt-view]').forEach(b=>b.onclick=()=>switchView(b.dataset.ltView));
        document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>{
            period=b.dataset.period; document.querySelectorAll('[data-period]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',x===b);}); loadReport();
        });
        el('ltReport').addEventListener('click',e=>{
            const b=e.target.closest('button'); if(!b)return;
            if(b.dataset.upgrade !== undefined){window.navigateTo('user-center');return;}
            if(b.dataset.day){el('ltDate').value=b.dataset.day;switchView('daily');loadDay();document.querySelector('.lt-page').scrollIntoView({block:'start'});}
            if(b.dataset.expFilter!==undefined){
                const detail=el('ltReportExpenses');detail.open=true;
                detail.querySelectorAll('[data-exp-category]').forEach(row=>row.hidden=!!b.dataset.expFilter && row.dataset.expCategory!==b.dataset.expFilter);
                el('ltExpenseFilterLabel').textContent=b.dataset.expFilter ? '当前分类：'+(expenseNames()[b.dataset.expFilter]||b.dataset.expFilter) : '全部类别';
                detail.scrollIntoView({block:'nearest',behavior:'smooth'});
            }
            if(b.dataset.expActivity){
                const detail=el('ltReportExpenses');detail.open=true;
                detail.querySelectorAll('[data-exp-category]').forEach(row=>row.hidden=row.dataset.linkedActivity!==b.dataset.expActivity);
                el('ltExpenseFilterLabel').textContent='当前活动关联的账目';
                detail.scrollIntoView({block:'nearest',behavior:'smooth'});
            }
            if(b.dataset.activityLink){
                const row=el('lt-record-'+b.dataset.activityLink);
                if(row){for(let p=row.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;row.scrollIntoView({block:'center',behavior:'smooth'});row.classList.add('lt-highlight');}
            }
        });
        el('ltSettingsFields').addEventListener('input',e=>settingsInput(e.target));
        el('ltSettingsFields').addEventListener('click',e=>{
            const b=e.target.closest('[data-remove-g]');if(!b)return;
            settingsDraft.goals=settingsDraft.goals.filter(g=>g.id!==b.dataset.removeG);settingsDirty=true;renderSettings();el('ltSettingsStatus').textContent='设置有未保存的修改。';
        });
        el('ltAddGoal').onclick=()=>{
            settingsDraft.goals.push({id:uid(),category:'reading',metric:'seconds',target:180*60,period:'week',reading_kind:null,topic:null,expense_category:null,start_date:today(),end_date:null});
            settingsDirty=true;renderSettings();el('ltSettingsStatus').textContent='设置有未保存的修改。';
        };
        el('ltAddCategory').onclick=()=>{
            settingsDraft.expense_categories.push({id:'custom-'+uid(),name:'',archived:false});settingsDirty=true;renderSettings();
            el('ltCategories').lastElementChild.querySelector('input').focus();
        };
        el('ltSaveSettings').onclick=saveSettings;
        el('ltExportSettings').onclick=downloadDraft;
        el('ltReloadSettings').onclick=async()=>{
            if(settingsBusy || (settingsDirty && !window.confirm('重新读取将丢弃未保存的设置修改。需要保留时，请先导出设置草稿。')))return;
            const epoch=sessionEpoch;
            try{const p=await api('/preferences');if(!sameSession(epoch))return;preferences=p;settingsDraft=clone(p);settingsDirty=false;renderSettings();el('ltSettingsStatus').textContent='已重新读取设置。';}
            catch(e){el('ltSettingsStatus').textContent=e.message;}
        };
        window.addEventListener('beforeunload',e=>{if(dirty||drafts.size||settingsDirty){e.preventDefault();e.returnValue='';}});
        window.addEventListener('storage',e=>{if(e.key==='authToken')window.loadLongTerm();});
    });
})();
