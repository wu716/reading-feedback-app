/* First release: a situation, a first step, and evidence from actual use. */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const DEMO_KEY = 'shuran.methods.demo.v1';
    const SESSION_KEY = 'shuran.methods.session.v1';
    const OUTCOMES = { helpful: '试了，有帮助', not_helpful: '试了，没帮助', not_used: '这次没用上' };
    const BARRIERS = { forgot: '当时没想起来', too_hard: '这一步还是太麻烦', interrupted: '被其他事情打断', not_suitable: '方法不适合这个情境', other: '其他' };
    const EXAMPLES = {
        start: { title: '坐下后，先打开材料', situation: '第一次坐到图书馆，打开书后又开始刷手机。', first_step: '把手机放进包里，打开要看的那一页，只读第一段。', source_title: '写法示例，请按自己的情况调整' },
        overload: { title: '事情太多时，先选一件', situation: '看着一长串任务，不知道先做哪个，开始逃避。', first_step: '只选现在最重要的一件，写下第一个能动手的动作。', source_title: '写法示例，请按自己的情况调整' },
        interruption: { title: '被打断后，重新接上', situation: '临时事情结束，原来的安排被打乱，不知道怎么继续。', first_step: '回到材料前，写下刚才做到哪里，再选接下来能做的一小步。', source_title: '写法示例，请按自己的情况调整' },
    };
    let cards = [];
    let identity = null;
    let filter = 'active';
    let query = '';
    let editId = null;
    let editKey = null;
    let sourceNoteId = null;
    let currentUse = null;
    let currentCardId = null;
    let sources = [];
    let mutationBusy = false;
    let loadNumber = 0;
    let total = 0;
    let ready = false;
    const visitSent = new Set();

    function uuid() {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
        return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
    }

    let sessionKey = uuid();
    try {
        sessionKey = sessionStorage.getItem(SESSION_KEY) || sessionKey;
        sessionStorage.setItem(SESSION_KEY, sessionKey);
    } catch (_) { /* Metrics remain session-local when storage is unavailable. */ }

    function token() { return localStorage.getItem('authToken') || ''; }
    function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
    function notice(message, type = 'success') { if (typeof showMessage === 'function') showMessage(message, type); }
    function dateLabel(value) {
        if (!value) return '';
        const date = new Date(value);
        return Number.isNaN(date.valueOf()) ? '' : date.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric' });
    }
    function isVisible() { return $('methods')?.classList.contains('active'); }

    async function api(path, body, method = 'GET') {
        const account = token();
        const response = await fetch('/api/methods' + path, {
            method, cache: 'no-store', headers: { 'Content-Type': 'application/json', ...(account ? { Authorization: 'Bearer ' + account } : {}) },
            ...(body ? { body: JSON.stringify(body) } : {}),
        });
        if (account !== token()) throw new Error('账号已切换，请重新操作。');
        const data = response.status === 204 ? null : await response.json();
        if (!response.ok) {
            if (response.status === 401) {
                if (typeof clearAuthSession === 'function') clearAuthSession();
                if (typeof showAuthModal === 'function') showAuthModal(true);
            }
            throw new Error(typeof data?.detail === 'string' ? data.detail : '操作未完成，请稍后再试。');
        }
        return data;
    }

    function track(eventName) {
        const key = eventName;
        if (visitSent.has(key)) return;
        visitSent.add(key);
        // Never include card text, source excerpts, or use notes in anonymous metrics.
        fetch('/api/methods/visits', { method: 'POST', credentials: 'omit', cache: 'no-store',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_key: sessionKey, event_name: eventName })
        }).then((response) => { if (!response.ok) visitSent.delete(key); }).catch(() => visitSent.delete(key));
    }

    function readDemo() {
        try {
            const data = JSON.parse(localStorage.getItem(DEMO_KEY) || '[]');
            return Array.isArray(data) ? data.filter((card) => card && typeof card.situation === 'string' && typeof card.first_step === 'string').slice(0, 100) : [];
        } catch (_) { return []; }
    }
    function writeDemo(data) {
        try { localStorage.setItem(DEMO_KEY, JSON.stringify(data)); }
        catch (_) { throw new Error('浏览器没有保存成功。请检查存储空间，或登录后保存到账号。'); }
    }
    function demoPayload(card) {
        const uses = Array.isArray(card.uses) ? card.uses : [];
        return { ...card, pending_use: uses.find((use) => !use.finished_at) || null,
            recent_uses: uses.filter((use) => use.finished_at).slice(0, 5),
            tried_count: uses.filter((use) => ['helpful', 'not_helpful'].includes(use.outcome)).length,
            helpful_count: uses.filter((use) => use.outcome === 'helpful').length };
    }
    function setBusy(value) {
        mutationBusy = value;
        document.querySelectorAll('#methodEditorForm button[type="submit"], #methodUseDialog button[data-outcome], #methodUseDetailsForm button, #methodDemoAction').forEach((button) => { button.disabled = value; });
    }

    function render() {
        if (!$('methodGrid')) return;
        const signedIn = !!token();
        const demoCount = readDemo().length;
        $('methodDemoBanner').hidden = signedIn && demoCount === 0;
        $('methodDemoTitle').textContent = signedIn ? `浏览器里还有 ${demoCount} 张体验卡片` : '可以先体验，再决定是否继续用';
        $('methodDemoHint').textContent = signedIn ? '可以保存到当前账号。体验时的反馈不会计入正式使用记录。' : '体验卡片保存在这个浏览器里；登录后可以保存到你的账号。新账号目前需要邀请码。';
        $('methodDemoAction').textContent = signedIn ? '保存到我的账号' : '登录 / 注册';
        const helpful = cards.filter((card) => card.helpful_count > 0).length;
        const tried = cards.reduce((sum, card) => sum + Number(card.tried_count || 0), 0);
        $('methodStats').innerHTML = `<span><strong>${cards.length}</strong>张卡片</span><span><strong>${tried}</strong>次试过</span><span><strong>${helpful}</strong>张有帮助${signedIn ? '' : ' · 浏览器体验'}</span>`;
        const visible = cards.filter((card) => {
            if (filter === 'helpful' ? !(card.helpful_count > 0 && card.state === 'active') : card.state !== filter) return false;
            return !query || [card.title, card.situation, card.first_step, card.source_title].some((value) => String(value || '').toLowerCase().includes(query));
        });
        document.querySelectorAll('[data-method-filter]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.methodFilter === filter)));
        $('methodLimit').hidden = !signedIn || total <= cards.length;
        $('methodLimit').textContent = `当前显示最近 ${cards.length} 张，共匹配 ${total} 张。可以用情境或关键词继续缩小范围。`;
        if (!visible.length) {
            const emptyTitle = query ? '没有找到对应的方法' : filter === 'helpful' ? '试过之后，再看哪些适合自己' : filter === 'paused' ? '暂时没有放下的方法' : '先从一个反复遇到的小问题开始';
            const emptyHint = query ? '换一个情境或关键词，或者写一张新的方法卡。' : filter === 'helpful' ? '记录“试了，有帮助”后，卡片会出现在这里。' : filter === 'paused' ? '当前不想继续的方法可以暂放，需要时再恢复。' : '只写两句话：遇到什么情境，先做哪一步。';
            $('methodGrid').innerHTML = `<div class="method-empty"><h2>${emptyTitle}</h2><p>${emptyHint}</p><button type="button" class="method-button" data-method-new>写第一张方法卡</button></div>`;
            return;
        }
        $('methodGrid').innerHTML = visible.map((card) => `<article class="method-card" data-card="${esc(card.id)}">
            <div class="method-card-top"><h2>${esc(card.title)}</h2><details class="method-manage"><summary>管理</summary><div class="method-manage-menu"><button type="button" data-card-action="edit">修改方法</button><button type="button" data-card-action="pause">${card.state === 'paused' ? '恢复使用' : '暂时放下'}</button><button type="button" data-card-action="delete">移除卡片</button></div></details></div>
            <p class="method-card-label">遇到这个情境</p><p class="method-situation">${esc(card.situation)}</p>
            <p class="method-card-label">先做这一步</p><p class="method-step">${esc(card.first_step)}</p>
            ${card.source_title || card.source_excerpt ? `<details class="method-source"><summary>来源 · ${esc(card.source_title || '我的记录')}</summary>${card.source_excerpt ? `<p>${esc(card.source_excerpt)}</p>` : ''}</details>` : ''}
            <div class="method-card-bottom">${card.state === 'active' ? `<button type="button" class="method-button${card.pending_use ? '' : ' primary'}" data-card-action="start">${card.pending_use ? '给上次尝试留个反馈' : '遇到了，先试一下'}</button>` : '<p class="method-evidence">暂时放下，需要时可以恢复。</p>'}
                <p class="method-evidence">${card.tried_count ? `试过 ${Number(card.tried_count)} 次 · ${Number(card.helpful_count)} 次有帮助` : '还没有试过的记录'}</p>
                ${card.recent_uses?.length ? `<details class="method-history"><summary>最近的尝试</summary>${card.recent_uses.map((use) => `<div class="method-history-row"><span>${esc(dateLabel(use.started_at))} · ${esc(OUTCOMES[use.outcome] || '')}</span><button type="button" data-use-edit="${esc(use.id)}">补充 / 改正</button>${use.barrier ? `<p>${esc(BARRIERS[use.barrier] || '')}</p>` : ''}${use.note ? `<p>${esc(use.note)}</p>` : ''}</div>`).join('')}</details>` : ''}
            </div></article>`).join('');
    }

    async function load() {
        if (!ready || !isVisible()) return;
        const account = token();
        if (identity !== account) { cards = []; identity = account; closeDialog(); }
        const number = ++loadNumber;
        if (!account) {
            cards = readDemo().map(demoPayload);
            total = cards.length;
            render(); track('opened');
            return;
        }
        if (!cards.length) $('methodGrid').innerHTML = '<p class="method-footnote">正在读取你的方法卡…</p>';
        try {
            const data = await api('?state=all' + (query ? '&search=' + encodeURIComponent(query) : ''));
            if (number !== loadNumber || account !== token()) return;
            cards = data.items;
            total = data.total || cards.length;
            render(); track('opened');
        } catch (error) {
            if (number !== loadNumber || account !== token()) return;
            $('methodGrid').innerHTML = `<div class="method-empty"><h2>这次没有读取成功</h2><p>${esc(error.message)}</p><button type="button" class="method-button" data-method-retry>再试一次</button></div>`;
        }
    }

    function closeDialog() {
        const dialog = document.querySelector('.method-dialog[open]');
        if (!dialog) return false;
        dialog.close();
        return true;
    }
    function openDialog(id) { closeDialog(); $(id).showModal(); }

    function openEditor(value = {}, isEdit = false) {
        editId = isEdit ? value.id : null;
        editKey = value.client_key || uuid();
        sourceNoteId = value.source_note_id || null;
        $('methodEditorTitle').textContent = isEdit ? '修改方法卡' : '写一张方法卡';
        $('methodEditorForm').reset();
        $('methodEditorError').textContent = '';
        const fields = { methodSituation: 'situation', methodFirstStep: 'first_step', methodTitleInput: 'title', methodSourceTitle: 'source_title', methodSourceExcerpt: 'source_excerpt' };
        Object.entries(fields).forEach(([id, key]) => { $(id).value = String(value[key] || '').slice(0, $(id).maxLength); });
        $('methodExistingSourceField').hidden = !token() || isEdit;
        openDialog('methodEditor');
        if (token() && !isEdit) {
            const account = token();
            api('/sources').then((data) => {
                if (account !== token() || !$('methodEditor').open || editId) return;
                sources = data.items;
                $('methodExistingSource').innerHTML = '<option value="">选择已有行动</option>' + sources.map((source) => `<option value="${source.id}">${esc(source.title)}</option>`).join('');
            }).catch(() => { $('methodExistingSourceField').hidden = true; });
        }
    }

    function editorValue() {
        return { title: $('methodTitleInput').value.trim(), situation: $('methodSituation').value.trim(),
            first_step: $('methodFirstStep').value.trim(), source_title: $('methodSourceTitle').value.trim(),
            source_excerpt: $('methodSourceExcerpt').value.trim() };
    }
    async function saveEditor(event) {
        event.preventDefault();
        if (mutationBusy) return;
        const value = editorValue();
        if (!value.situation || !value.first_step) { $('methodEditorError').textContent = '请写清具体情境和第一步。'; return; }
        setBusy(true);
        const account = token();
        try {
            if (account) {
                const existing = cards.find((card) => String(card.id) === String(editId));
                await api(editId ? '/' + editId : '', editId ? { ...value, state: existing?.state || 'active' } : { ...value, client_key: editKey, source_note_id: sourceNoteId }, editId ? 'PUT' : 'POST');
            } else {
                const data = readDemo();
                if (editId) {
                    const index = data.findIndex((card) => card.id === editId);
                    if (index < 0) throw new Error('卡片已移除，请重新打开。');
                    data[index] = { ...data[index], ...value, title: value.title || value.first_step.slice(0, 60) };
                } else {
                    if (data.length >= 100) throw new Error('浏览器体验已保存 100 张，请登录后继续。');
                    if (!data.some((card) => card.client_key === editKey)) data.unshift({ ...value, title: value.title || value.first_step.slice(0, 60), id: 'demo-' + editKey, client_key: editKey, state: 'active', uses: [], created_at: new Date().toISOString() });
                }
                writeDemo(data); track('demo_saved');
            }
            if (account !== token()) return;
            filter = 'active'; query = ''; $('methodSearch').value = '';
            closeDialog(); await load(); notice('方法卡已保存。遇到这个情境时，再来试一小步。');
        } catch (error) { if (account === token()) $('methodEditorError').textContent = error.message; }
        finally { setBusy(false); }
    }

    function renderUse(use, cardId) {
        currentUse = use; currentCardId = cardId;
        $('methodUseSituation').textContent = '遇到：' + use.situation;
        $('methodUseStep').textContent = use.first_step;
        $('methodUseTitle').textContent = use.finished_at ? '这次的反馈' : '先做这一步';
        $('methodUseError').textContent = '';
        document.querySelectorAll('[data-outcome]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.outcome === use.outcome)));
        $('methodUseDetailsForm').hidden = !use.finished_at;
        $('methodBarrier').value = use.barrier || '';
        $('methodUseNote').value = use.note || '';
        $('methodUseDetailsForm').querySelector('details').open = false;
        openDialog('methodUseDialog');
    }
    async function start(card) {
        if (mutationBusy) return;
        setBusy(true);
        const account = token();
        try {
            let use = card.pending_use;
            if (!use && account) use = await api('/' + card.id + '/uses', { client_key: uuid() }, 'POST');
            if (!use && !account) {
                use = { id: uuid(), card_id: card.id, situation: card.situation, first_step: card.first_step, started_at: new Date().toISOString(), finished_at: null, outcome: null, note: '', barrier: null };
                const data = readDemo();
                const stored = data.find((item) => item.id === card.id);
                if (!stored) throw new Error('卡片已移除，请重新打开。');
                stored.uses.unshift(use); writeDemo(data); track('demo_started');
            }
            if (account !== token()) return;
            await load(); renderUse(use, card.id);
        } catch (error) { notice(error.message, 'error'); }
        finally { setBusy(false); }
    }
    async function finish(outcome, detailOnly = false) {
        if (!currentUse || mutationBusy) return;
        setBusy(true);
        const account = token();
        const useId = currentUse.id;
        const cardId = currentCardId;
        const body = { outcome, barrier: detailOnly ? $('methodBarrier').value || null : currentUse.outcome === outcome ? currentUse.barrier : null,
            note: detailOnly ? $('methodUseNote').value.trim() : currentUse.note || '' };
        try {
            let use;
            if (account) use = await api('/uses/' + useId, body, 'PUT');
            else {
                const data = readDemo();
                const card = data.find((item) => item.id === cardId);
                const index = card?.uses.findIndex((item) => item.id === useId);
                if (index == null || index < 0) throw new Error('这次尝试已不存在。');
                use = { ...card.uses[index], ...body, finished_at: card.uses[index].finished_at || new Date().toISOString() };
                if (outcome === 'helpful') use.barrier = null;
                card.uses[index] = use; writeDemo(data); track('demo_feedback');
            }
            if (account !== token()) return;
            await load(); renderUse(use, cardId);
            if (outcome === 'helpful' || detailOnly) closeDialog();
            notice(detailOnly ? '补充已保存。' : '反馈已保存。可以根据这次情况继续调整方法。');
        } catch (error) { if (account === token()) $('methodUseError').textContent = error.message; }
        finally { setBusy(false); }
    }

    async function manage(card, action) {
        if (action === 'edit') return openEditor(card, true);
        if (action === 'start') return start(card);
        if (mutationBusy) return;
        if (action === 'delete' && !window.confirm('移除这张方法卡？它将不再出现在你的方法库。')) return;
        setBusy(true);
        const account = token();
        try {
            if (account) {
                if (action === 'delete') await api('/' + card.id, null, 'DELETE');
                else await api('/' + card.id, { title: card.title, situation: card.situation, first_step: card.first_step,
                    source_title: card.source_title, source_excerpt: card.source_excerpt, state: card.state === 'paused' ? 'active' : 'paused' }, 'PUT');
            } else {
                const data = readDemo();
                if (action === 'delete') writeDemo(data.filter((item) => item.id !== card.id));
                else { const stored = data.find((item) => item.id === card.id); if (stored) stored.state = stored.state === 'paused' ? 'active' : 'paused'; writeDemo(data); }
            }
            if (account !== token()) return;
            await load(); notice(action === 'delete' ? '卡片已移除。' : card.state === 'paused' ? '已恢复使用。' : '已暂时放下，需要时可以恢复。');
        } catch (error) { notice(error.message, 'error'); }
        finally { setBusy(false); }
    }

    async function importDemo() {
        if (!token()) { if (typeof showAuthModal === 'function') showAuthModal(true); return; }
        if (mutationBusy) return;
        const demos = readDemo();
        if (!demos.length) return;
        if (!window.confirm(`将这 ${demos.length} 张体验卡片保存到当前账号？体验反馈不会计入正式使用记录。`)) return;
        setBusy(true);
        const account = token();
        try {
            for (const card of demos) {
                await api('', { client_key: card.client_key, title: card.title, situation: card.situation,
                    first_step: card.first_step, source_title: card.source_title || '', source_excerpt: card.source_excerpt || '' }, 'POST');
                if (account !== token()) return;
                // Remove only confirmed saves, so a retry cannot duplicate a partial import.
                writeDemo(readDemo().filter((item) => item.client_key !== card.client_key));
            }
            await load(); notice('卡片已保存到账号。');
        } catch (error) { if (account === token()) { await load(); notice(error.message + ' 已保存的卡片不会重复导入。', 'error'); } }
        finally { setBusy(false); }
    }

    async function productFeedback(event) {
        event.preventDefault();
        const button = $('methodFeedbackSubmit');
        if (button.disabled) return;
        const message = $('methodFeedbackMessage').value.trim();
        if (message.length < 3) { $('methodFeedbackError').textContent = '请写下具体发生的事情，至少 3 个字。'; return; }
        button.disabled = true; $('methodFeedbackError').textContent = '';
        try {
            await api('/product-feedback', { session_key: sessionKey, category: $('methodFeedbackCategory').value, message }, 'POST');
            $('methodProductFeedbackForm').reset(); closeDialog(); notice('意见已发送给开发者，谢谢你的反馈。');
        } catch (error) { $('methodFeedbackError').textContent = error.message; }
        finally { button.disabled = false; }
    }

    async function loadMarket() {
        const body = $('methodMarketBody');
        if (!body || !token()) return;
        body.textContent = '正在读取真实使用记录…';
        try {
            const data = await api('/market');
            const metrics = [[data.visit_sessions, '访问会话'], [data.created_users, '保存卡片的账号'], [data.tried_users, '记录试过的账号'],
                [data.returning_users, '在不同日期试过的账号'], [data.helpful_feedback, '试了有帮助'], [data.not_helpful_feedback, '试了没帮助']];
            body.innerHTML = `<div class="method-market-metrics">${metrics.map(([value, label]) => `<div><strong>${Number(value || 0)}</strong>${label}</div>`).join('')}</div>
                <p>近 7 天发起尝试：${Number(data.started_users)} 个账号；“没用上”：${Number(data.not_used_feedback)} 次。<br>浏览器体验：${Number(data.demo_sessions.demo_saved)} 个会话保存，${Number(data.demo_sessions.demo_started)} 个会话点击开始，${Number(data.demo_sessions.demo_feedback)} 个会话留下反馈。体验结果不计入正式尝试。</p>
                <p>“在不同日期试过”指近 7 天至少两个北京时间日期有已完成的尝试记录。以上是分项计数，不能直接相除当作转化率。</p>
                <h2>主动提交的意见</h2>${data.feedback.length ? data.feedback.map((item) => `<div class="method-market-message"><small>${esc(dateLabel(item.created_at))} · ${item.from_member ? '账号用户' : '访客'} · ${esc({ problem: '使用问题', suggestion: '改进建议', useful: '有帮助的地方' }[item.category])}</small><p>${esc(item.message)}</p></div>`).join('') : '<p>还没有收到意见。</p>'}`;
        } catch (error) { body.textContent = error.message; }
    }

    function onAccountChange() {
        ++loadNumber; cards = []; identity = null; closeDialog();
        if (ready) { render(); load(); }
        if ($('methodMarketBody')) $('methodMarketBody').textContent = '进入后加载真实数据。';
    }
    function onReady() {
        if (!$('methods')) return;
        ready = true;
        $('methodNewBtn').addEventListener('click', () => openEditor());
        document.querySelectorAll('[data-method-close]').forEach((button) => button.addEventListener('click', closeDialog));
        $('methodEditorForm').addEventListener('submit', saveEditor);
        document.querySelectorAll('[data-method-example]').forEach((button) => button.addEventListener('click', () => openEditor(EXAMPLES[button.dataset.methodExample])));
        document.querySelectorAll('[data-method-filter]').forEach((button) => button.addEventListener('click', () => { filter = button.dataset.methodFilter; render(); }));
        let searchTimer;
        $('methodSearch').addEventListener('input', () => { query = $('methodSearch').value.trim().toLowerCase(); clearTimeout(searchTimer); searchTimer = setTimeout(() => token() ? load() : render(), 180); });
        $('methodExistingSource').addEventListener('change', () => {
            const source = sources.find((item) => item.id === Number($('methodExistingSource').value));
            if (!source) return;
            $('methodTitleInput').value = source.title; $('methodFirstStep').value = source.first_step;
            $('methodSourceTitle').value = source.source_title; $('methodSourceExcerpt').value = source.source_excerpt;
            sourceNoteId = null;
        });
        $('methodGrid').addEventListener('click', (event) => {
            if (event.target.closest('[data-method-new]')) return openEditor();
            if (event.target.closest('[data-method-retry]')) return load();
            const element = event.target.closest('[data-card]');
            const card = cards.find((item) => String(item.id) === element?.dataset.card);
            if (!card) return;
            const useButton = event.target.closest('[data-use-edit]');
            if (useButton) {
                const use = card.recent_uses?.find((item) => String(item.id) === useButton.dataset.useEdit);
                if (use) renderUse(use, card.id);
                return;
            }
            const button = event.target.closest('[data-card-action]');
            if (button) manage(card, button.dataset.cardAction);
        });
        document.querySelectorAll('[data-outcome]').forEach((button) => button.addEventListener('click', () => finish(button.dataset.outcome)));
        $('methodUseDetailsForm').addEventListener('submit', (event) => { event.preventDefault(); finish(currentUse.outcome, true); });
        const openFeedback = () => { $('methodFeedbackError').textContent = ''; openDialog('methodFeedbackDialog'); };
        $('methodFeedbackBtn').addEventListener('click', openFeedback);
        $('methodPrivacyFeedbackBtn').addEventListener('click', openFeedback);
        $('methodProductFeedbackForm').addEventListener('submit', productFeedback);
        $('methodDemoAction').addEventListener('click', importDemo);
        $('methodMarketRefresh')?.addEventListener('click', loadMarket);
        window.addEventListener('auth-check-settled', load);
        window.addEventListener('shuran-auth-change', onAccountChange);
        document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') load(); });
        window.addEventListener('storage', (event) => { if (event.key === 'authToken') onAccountChange(); if (event.key === DEMO_KEY && !token()) load(); });
        load();
    }

    window.ShuranMethods = {
        load, loadMarket, closeDialog,
        fromNote(note) {
            if (typeof navigateTo === 'function') navigateTo('methods');
            openEditor({ title: note.note_text.slice(0, 60), first_step: note.note_text.slice(0, 500),
                source_title: note.book_title + ' · ' + note.chapter_title,
                source_excerpt: note.selected_text.slice(0, 2000), source_note_id: note.id });
        },
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
    else onReady();
})();
