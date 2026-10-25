/** “记”的独立收集箱；录入、查看与安排日期不受日程视图模式影响。 */
(function () {
    let items = [];
    let loaded = false;
    let loadFailed = false;
    let busy = false;
    let epoch = 0;
    let editing = null;
    let arranging = null;
    let undo = null;
    const drafts = new Map();
    const dates = new Map();
    let composerTrigger = null;

    const byId = id => document.getElementById(id);
    const text = (key, fallback) => window.shuranI18n?.t('schedule.later.' + key, fallback) ?? fallback;
    const common = (key, fallback) => window.shuranI18n?.t('common.' + key, fallback) ?? fallback;
    const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
    const request = (path, options) => apiRequest('/api/schedule/future' + path, options);

    function today() {
        const now = new Date();
        return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    }

    function status(message, error = false) {
        const target = byId('scheduleLaterDialog')?.open ? 'scheduleLaterComposerStatus'
            : byId('future-actions')?.classList.contains('active') ? 'scheduleLaterStatus' : 'captureFutureStatus';
        for (const id of ['scheduleLaterStatus', 'captureFutureStatus', 'scheduleLaterComposerStatus']) {
            const label = byId(id);
            if (label) { label.textContent = id === target ? message : ''; label.dataset.error = String(id === target && error); }
        }
    }

    function openComposer(event) {
        composerTrigger = event.currentTarget;
        status('');
        byId('scheduleLaterDialog').showModal();
        byId('scheduleLaterInput').focus({preventScroll:true});
    }

    function closeComposer() {
        byId('scheduleLaterDialog').close();
        return composerTrigger;
    }

    window.closeFutureActionComposer = () => {
        if (!byId('scheduleLaterDialog')?.open) return false;
        if (!busy) closeComposer()?.focus({preventScroll:true});
        return true;
    };

    function focusEdit() {
        byId('scheduleLaterList')?.querySelector(`[data-later-id="${editing}"] textarea`)?.focus({preventScroll:true});
    }

    function render() {
        const list = byId('scheduleLaterList');
        if (!list) return;
        const focused = document.activeElement;
        const focusedId = focused?.matches('[data-later-act="text"]') ? focused.closest('[data-later-id]').dataset.laterId : null;
        const selection = focusedId ? [focused.selectionStart, focused.selectionEnd] : null;
        byId('scheduleLaterSummary').textContent = loaded ? text('count', '{count} 个').replace('{count}', items.length) : '—';
        byId('scheduleLaterUndo').hidden = !undo;
        byId('scheduleLaterRetry').hidden = !loadFailed;
        if (!loaded) { list.innerHTML = `<p class="schedule-later-empty">${escape(loadFailed ? text('loadFailed', '读取失败，请重试') : text('loading', '正在读取…'))}</p>`; return; }
        if (!items.length) { list.innerHTML = `<p class="schedule-later-empty">${escape(text('empty', '先记下来，准备好了再安排到日程'))}</p>`; return; }
        list.innerHTML = items.map(item => {
            if (editing === item.id) return `<article class="schedule-later-item capture-later-editor" data-later-id="${item.id}"><label for="futureEdit${item.id}">${escape(text('editAria', '修改以后想做'))}</label><textarea id="futureEdit${item.id}" data-later-act="text" rows="3" maxlength="500">${escape(drafts.get(item.id) ?? item.text)}</textarea><div class="capture-later-actions"><button type="button" class="capture-later-save" data-later-act="save">${escape(common('save', '保存'))}</button><button type="button" class="capture-later-text" data-later-act="cancel">${escape(common('cancel', '取消'))}</button></div></article>`;
            return `<article class="schedule-later-item" data-later-id="${item.id}"><button type="button" class="capture-later-title" data-later-act="edit" aria-label="${escape(text('editAria', '修改以后想做'))}：${escape(item.text)}">${escape(item.text)}</button><div class="capture-later-item-actions"><button type="button" class="capture-later-text" data-later-act="arrange">${escape(text('arrange', '安排到日程'))}</button><button type="button" class="capture-later-text is-secondary" data-later-act="edit">${escape(text('edit', '修改'))}</button><button type="button" class="capture-later-text is-secondary" data-later-act="delete">${escape(text('delete', '删除'))}</button></div>${arranging === item.id ? `<div class="capture-later-date"><label for="futureDate${item.id}">${escape(text('whichDay', '安排在哪一天？'))}</label><input id="futureDate${item.id}" data-later-act="date" type="date" value="${escape(dates.get(item.id) || today())}" required><div class="capture-later-actions"><button type="button" class="capture-later-save" data-later-act="confirm">${escape(text('confirm', '确认安排'))}</button><button type="button" class="capture-later-text" data-later-act="cancel-date">${escape(common('cancel', '取消'))}</button></div></div>` : ''}</article>`;
        }).join('');
        if (focusedId && editing === Number(focusedId)) {
            const input = list.querySelector(`[data-later-id="${focusedId}"] textarea`);
            input?.focus({preventScroll:true});
            if (input && selection) input.setSelectionRange(...selection);
        }
    }

    async function load() {
        if (busy) return;
        const version = ++epoch;
        if (!localStorage.getItem('authToken')) { items = []; undo = null; loaded = true; render(); return; }
        try {
            const result = await request('');
            if (version !== epoch) return;
            items = result.items || [];
            loaded = true;
            loadFailed = false;
            render();
        } catch (error) {
            if (version === epoch) { loadFailed = true; status(error.message || text('loadFailed', '读取失败，请重试'), true); render(); }
        }
    }
    window.loadFutureActions = load;

    async function mutate(action) {
        if (busy) return;
        busy = true;
        ++epoch; // Discard reads started before this mutation.
        const buttons = [...document.querySelectorAll('#scheduleLater button, #scheduleLaterDialog button, #scheduleLaterWrite, #scheduleLaterToggle')];
        buttons.forEach(button => { button.disabled = true; });
        byId('scheduleLaterInput').readOnly = true;
        byId('scheduleLater').setAttribute('aria-busy', 'true');
        let focusTarget;
        try { focusTarget = await action(); }
        catch (error) { status(error.message || text('saveFailed', '保存失败，内容已保留，请重试'), true); }
        finally {
            busy = false;
            buttons.forEach(button => { button.disabled = false; });
            byId('scheduleLaterInput').readOnly = false;
            byId('scheduleLater').removeAttribute('aria-busy');
            focusTarget?.focus({preventScroll:true});
        }
    }

    function ready() {
        const root = byId('scheduleLater');
        if (!root || root.dataset.bound) return;
        root.dataset.bound = '1';
        const input = byId('scheduleLaterInput');
        const composer = byId('scheduleLaterComposer');
        const list = byId('scheduleLaterList');
        byId('scheduleLaterWrite').addEventListener('click', openComposer);
        byId('scheduleLaterWriteFromList').addEventListener('click', openComposer);
        byId('scheduleLaterDialog').addEventListener('cancel', event => {
            event.preventDefault();
            if (!busy) closeComposer()?.focus({preventScroll:true});
        });
        byId('scheduleLaterDialog').addEventListener('keydown', event => {
            if (event.key !== 'Tab') return;
            const fields = [...byId('scheduleLaterDialog').querySelectorAll('textarea, button')].filter(field => !field.disabled);
            if (!fields.length) { event.preventDefault(); return; }
            const first = fields[0], last = fields[fields.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        byId('scheduleLaterCancel').addEventListener('click', () => {
            if (busy) return;
            const trigger = closeComposer();
            status('');
            trigger?.focus({preventScroll:true});
        });
        composer.addEventListener('submit', event => {
            event.preventDefault();
            const submitted = input.value;
            if (!submitted.trim()) { status(text('required', '先写下一件想做的事。'), true); input.focus(); return; }
            mutate(async () => {
                const result = await request('', {method:'POST', body:JSON.stringify({text:submitted.trim()})});
                items = result.items || [];
                loaded = true;
                loadFailed = false;
                if (input.value === submitted) input.value = '';
                render();
                const trigger = closeComposer();
                status(text('saved', '已记下'));
                return trigger;
            });
        });
        input.addEventListener('keydown', event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); composer.requestSubmit(); }
        });
        input.addEventListener('input', () => { if (byId('scheduleLaterComposerStatus').dataset.error === 'true') status(''); });
        byId('scheduleLaterRetry').addEventListener('click', () => { status(''); load(); });
        list.addEventListener('input', event => {
            const row = event.target.closest('[data-later-id]');
            if (!row) return;
            if (event.target.dataset.laterAct === 'text') drafts.set(Number(row.dataset.laterId), event.target.value);
            if (event.target.dataset.laterAct === 'date') dates.set(Number(row.dataset.laterId), event.target.value);
        });
        list.addEventListener('click', event => {
            const button = event.target.closest('button[data-later-act]');
            const row = button?.closest('[data-later-id]');
            if (!row || busy) return;
            const id = Number(row.dataset.laterId);
            const action = button.dataset.laterAct;
            if (editing !== null && editing !== id) { status(text('finishEdit', '请先保存或取消正在修改的内容。'), true); focusEdit(); return; }
            if (action === 'edit') { editing = id; arranging = null; render(); focusEdit(); }
            if (action === 'cancel') { drafts.delete(id); editing = null; render(); status(''); list.querySelector(`[data-later-id="${id}"] button`)?.focus({preventScroll:true}); }
            if (action === 'save') {
                const value = row.querySelector('textarea').value.trim();
                if (!value) { status(text('required', '先写下一件想做的事。'), true); focusEdit(); return; }
                mutate(async () => {
                    const result = await request('/' + id, {method:'PATCH',body:JSON.stringify({text:value})});
                    items = result.items || [];
                    editing = null;
                    drafts.delete(id);
                    render();
                    status(text('edited', '已保存修改'));
                    list.querySelector(`[data-later-id="${id}"] button`)?.focus({preventScroll:true});
                });
            }
            if (action === 'arrange') { arranging = arranging === id ? null : id; render(); byId('futureDate' + id)?.focus({preventScroll:true}); }
            if (action === 'cancel-date') { arranging = null; render(); list.querySelector(`[data-later-id="${id}"] [data-later-act="arrange"]`)?.focus({preventScroll:true}); }
            if (action === 'delete') mutate(async () => {
                const result = await request('/' + id, {method:'DELETE'});
                items = result.items || [];
                undo = result.undo_token ? {id, token:result.undo_token} : null;
                arranging = null;
                render();
                status(text('deleted', '已删除，可在十分钟内撤销'));
                return byId('scheduleLaterUndo');
            });
            if (action === 'confirm') {
                const dateInput = byId('futureDate' + id);
                if (!dateInput.value || !dateInput.checkValidity()) { status(text('dateRequired', '请选择有效日期。'), true); dateInput.focus(); return; }
                const selectedDate = dateInput.value;
                mutate(async () => {
                    await request('/' + id + '/schedule', {method:'POST',body:JSON.stringify({task_date:selectedDate})});
                    items = items.filter(item => item.id !== id);
                    arranging = null;
                    dates.delete(id);
                    render();
                    status(text('scheduled', '已安排到 {date} 的日程').replace('{date}', selectedDate));
                    window.loadDailySchedule?.();
                    return byId('scheduleLaterWriteFromList');
                });
            }
        });
        list.addEventListener('keydown', event => {
            if (event.target.dataset.laterAct !== 'text' || busy) return;
            const row = event.target.closest('[data-later-id]');
            if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); row.querySelector('[data-later-act="save"]').click(); }
            if (event.key === 'Escape') { event.preventDefault(); row.querySelector('[data-later-act="cancel"]').click(); }
        });
        byId('scheduleLaterUndo').addEventListener('click', () => {
            if (!undo) return;
            const entry = undo;
            mutate(async () => {
                const result = await request('/' + entry.id + '/restore', {method:'POST',body:JSON.stringify({undo_token:entry.token})});
                items = result.items || [];
                undo = null;
                render();
                status(text('restored', '已恢复'));
                return byId('scheduleLaterWriteFromList');
            });
        });
        window.addEventListener('shuran-language-change', render);
        render();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
    else ready();
})();
