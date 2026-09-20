(function () {
    const state = { program: null, summary: null };
    let loading = null;

    function t(key, fallback) {
        return window.shuranI18n ? window.shuranI18n.t(key, fallback) : fallback;
    }

    function fmt(template, values) {
        return String(template || '').replace(/\{(\w+)\}/g, (match, key) => (
            Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
        ));
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function todayISO() {
        try {
            return new Intl.DateTimeFormat('en-CA', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
            }).format(new Date());
        } catch (e) {
            return new Date().toISOString().slice(0, 10);
        }
    }

    function api(path, options) {
        if (typeof apiRequest !== 'function') return Promise.reject(new Error(t('habit.signIn', '请先登录')));
        return apiRequest(`/api/habits${path}`, options || {});
    }

    function sourceLabel(kind) {
        return {
            moment: t('capture.kind.moment', '时刻'),
            idea: t('capture.kind.idea', '灵感'),
            todo_today: t('capture.kind.todo', '待办'),
            todo_later: t('capture.kind.todo', '待办'),
        }[kind] || t('nav.capture', '记');
    }

    function dayNumber(program) {
        const start = new Date(`${program.start_date}T00:00:00`);
        const now = new Date(`${todayISO()}T00:00:00`);
        const diff = Math.floor((now.getTime() - start.getTime()) / 86400000);
        return Math.max(1, diff + 1);
    }

    function emptyMarkup() {
        return `
            <div class="habit-focus habit-empty">
                <p class="habit-kicker">${escapeHtml(t('habit.kicker', '本阶段只改变一件事'))}</p>
                <h2>${escapeHtml(t('habit.empty.title', '选择一个主要习惯'))}</h2>
                <p>${escapeHtml(t('habit.empty.desc', '先定义触发点和最小行动。'))}</p>
                <button type="button" class="habit-primary" data-habit-act="create">${escapeHtml(t('habit.empty.start', '开始设计'))}</button>
            </div>
        `;
    }

    function activeMarkup(program, summary) {
        const isBreak = program.mode === 'break';
        const target = summary.target_days || program.target_days_per_week || 1;
        const completed = summary.completed_days || 0;
        const progress = Math.min(100, Math.round((completed / target) * 100));
        const scale = isBreak ? summary.average_urge : summary.average_effort;
        const scaleLabel = isBreak
            ? t('habit.metric.urge', '平均冲动')
            : t('habit.metric.effort', '平均费力');
        const today = {
            completed: t('habit.today.completed', '今天已完成'),
            partial: t('habit.today.partial', '今天部分完成'),
            missed: t('habit.today.missed', '今天未发生'),
        }[summary.today_outcome] || t('habit.today.none', '今天还没有反馈');
        const signals = (summary.recent_signals || []).map((item) => `
            <div class="habit-signal-row">
                <span class="habit-signal-kind">${escapeHtml(sourceLabel(item.source_kind))}</span>
                <span>${escapeHtml(item.text)}</span>
            </div>
        `).join('');
        const behavior = isBreak ? program.replacement_action : program.minimum_action;
        const behaviorLabel = isBreak
            ? t('habit.design.replacement', '替代动作')
            : t('habit.design.minimum', '最小行动');
        return `
            <div class="habit-focus" data-program-id="${program.id}">
                <div class="habit-focus-head">
                    <div>
                        <p class="habit-kicker">${escapeHtml(fmt(t('habit.day', '第 {day} 天'), { day: dayNumber(program) }))}</p>
                        <h2>${escapeHtml(program.title)}</h2>
                    </div>
                    <span class="habit-mode-tag${isBreak ? ' is-break' : ''}">${escapeHtml(isBreak ? t('habit.mode.break', '戒掉坏习惯') : t('habit.mode.build', '建立好习惯'))}</span>
                </div>
                <div class="habit-body">
                    <dl class="habit-design-lines">
                        <div class="habit-design-line"><dt>${escapeHtml(t('habit.design.anchor', '触发点'))}</dt><dd>${escapeHtml(program.anchor_text)}</dd></div>
                        <div class="habit-design-line"><dt>${escapeHtml(behaviorLabel)}</dt><dd>${escapeHtml(behavior || program.title)}</dd></div>
                    </dl>
                    <div class="habit-metrics">
                        <div class="habit-metric"><strong>${completed}/${target}</strong><span>${escapeHtml(t('habit.metric.week', '近7天完成'))}</span></div>
                        <div class="habit-metric"><strong>${summary.signal_count || 0}</strong><span>${escapeHtml(t('habit.metric.signals', '复盘线索'))}</span></div>
                        <div class="habit-metric"><strong>${scale == null ? '—' : escapeHtml(scale)}</strong><span>${escapeHtml(scaleLabel)}</span></div>
                    </div>
                    <div class="habit-progress-track" aria-hidden="true"><div class="habit-progress-fill" style="width:${progress}%"></div></div>
                    <div class="habit-actions">
                        <button type="button" class="habit-primary" data-habit-act="schedule">${escapeHtml(t('habit.schedule', '排进这一天'))}</button>
                        <button type="button" data-habit-act="edit">${escapeHtml(t('habit.adjust', '调整设计'))}</button>
                    </div>
                    <div class="habit-checkin-row" aria-label="${escapeHtml(t('habit.checkin.aria', '今日反馈'))}">
                        <button type="button" data-habit-act="checkin" data-outcome="completed">${escapeHtml(t('habit.checkin.completed', '完成'))}</button>
                        <button type="button" data-habit-act="checkin" data-outcome="partial">${escapeHtml(t('habit.checkin.partial', '做了一部分'))}</button>
                        <button type="button" data-habit-act="checkin" data-outcome="missed">${escapeHtml(t('habit.checkin.missed', '没有做到'))}</button>
                    </div>
                    <p class="habit-today-state">${escapeHtml(today)}</p>
                    ${signals ? `<div class="habit-signals"><h3>${escapeHtml(t('habit.signals.title', '最近从「记」留下的线索'))}</h3>${signals}</div>` : ''}
                </div>
            </div>
        `;
    }

    function render() {
        const mount = document.getElementById('habitFocusMount');
        if (!mount) return;
        if (!localStorage.getItem('authToken')) {
            mount.innerHTML = '';
            return;
        }
        mount.innerHTML = state.program ? activeMarkup(state.program, state.summary || {}) : emptyMarkup();
    }

    async function loadHabitFocus() {
        if (!localStorage.getItem('authToken')) {
            state.program = null;
            state.summary = null;
            render();
            return null;
        }
        if (loading) return loading;
        loading = api('/active')
            .then((result) => {
                state.program = result.program || null;
                state.summary = result.summary || null;
                render();
                return state.program;
            })
            .catch((error) => {
                state.program = null;
                state.summary = null;
                if (!localStorage.getItem('authToken')) {
                    render();
                    return null;
                }
                const mount = document.getElementById('habitFocusMount');
                if (mount) mount.innerHTML = `<div class="habit-focus habit-empty"><p>${escapeHtml(error.message || t('habit.loadFailed', '加载失败'))}</p></div>`;
                return null;
            })
            .finally(() => { loading = null; });
        return loading;
    }

    function closeModal() {
        document.getElementById('habitModal')?.remove();
        document.getElementById('habitModalBackdrop')?.remove();
        document.body.classList.remove('tl-composing');
    }

    function modalShell(title, body) {
        closeModal();
        const backdrop = document.createElement('div');
        backdrop.id = 'habitModalBackdrop';
        backdrop.className = 'habit-modal-backdrop';
        const modal = document.createElement('section');
        modal.id = 'habitModal';
        modal.className = 'habit-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.innerHTML = `
            <div class="habit-modal-head">
                <h3>${escapeHtml(title)}</h3>
                <button type="button" class="habit-modal-close" aria-label="${escapeHtml(t('common.close', '关闭'))}">×</button>
            </div>
            ${body}
        `;
        document.body.appendChild(backdrop);
        document.body.appendChild(modal);
        document.body.classList.add('tl-composing');
        backdrop.addEventListener('click', closeModal);
        modal.querySelector('.habit-modal-close')?.addEventListener('click', closeModal);
        return modal;
    }

    async function actionChoices(selectedId) {
        try {
            const result = await apiRequest('/api/actions/?size=100');
            const items = Array.isArray(result) ? result : (result.items || []);
            return items
                .filter((item) => item.status !== 'done')
                .map((item) => `<option value="${item.id}"${Number(selectedId) === item.id ? ' selected' : ''}>${escapeHtml(item.action_text)}</option>`)
                .join('');
        } catch (e) {
            return '';
        }
    }

    async function openProgramForm(actionId) {
        const editing = !actionId && state.program;
        let sourceAction = null;
        if (actionId) {
            try {
                sourceAction = await apiRequest(`/api/actions/${actionId}`);
            } catch (error) {
                if (typeof showMessage === 'function') showMessage(error.message, 'error');
                return;
            }
        }
        const program = editing ? state.program : null;
        const mode = program?.mode || 'build';
        const selectedActionId = sourceAction?.id || program?.action_id || '';
        const options = await actionChoices(selectedActionId);
        const modal = modalShell(
            editing ? t('habit.form.editTitle', '调整习惯设计') : t('habit.form.createTitle', '设计主要习惯'),
            `<form class="habit-form" id="habitProgramForm">
                ${editing ? '' : `<div class="habit-field"><label for="habitActionId">${escapeHtml(t('habit.form.sourceAction', '从现有行动开始（可选）'))}</label><select id="habitActionId"><option value="">${escapeHtml(t('habit.form.newAction', '新建一个习惯'))}</option>${options}</select></div>`}
                ${editing ? '' : `<div class="habit-field"><label>${escapeHtml(t('habit.form.mode', '改变方向'))}</label><div class="habit-mode-picks"><button type="button" data-mode="build" class="${mode === 'build' ? 'is-on' : ''}">${escapeHtml(t('habit.mode.build', '建立好习惯'))}</button><button type="button" data-mode="break" class="${mode === 'break' ? 'is-on' : ''}">${escapeHtml(t('habit.mode.break', '戒掉坏习惯'))}</button></div></div>`}
                <input type="hidden" id="habitMode" value="${escapeHtml(mode)}">
                <div class="habit-field"><label for="habitTitle">${escapeHtml(t('habit.form.name', '习惯名称'))}</label><input id="habitTitle" maxlength="120" required value="${escapeHtml(program?.title || sourceAction?.action_text || '')}"></div>
                <div class="habit-field"><label for="habitAnchor">${escapeHtml(t('habit.form.anchor', '在什么时刻或场景发生'))}</label><textarea id="habitAnchor" maxlength="500" required>${escapeHtml(program?.anchor_text || '')}</textarea></div>
                <div class="habit-field" id="habitMinimumField"><label for="habitMinimum">${escapeHtml(t('habit.form.minimum', '小到一定能开始的行动'))}</label><textarea id="habitMinimum" maxlength="500">${escapeHtml(program?.minimum_action || sourceAction?.action_text || '')}</textarea></div>
                <div class="habit-field" id="habitReplacementField"><label for="habitReplacement">${escapeHtml(t('habit.form.replacement', '触发后立刻做的替代动作'))}</label><textarea id="habitReplacement" maxlength="500">${escapeHtml(program?.replacement_action || '')}</textarea></div>
                <div class="habit-field"><label for="habitTarget">${escapeHtml(t('habit.form.target', '每周目标天数'))}</label><input id="habitTarget" type="number" min="1" max="7" step="1" value="${program?.target_days_per_week || 5}"></div>
                <div class="habit-field"><label for="habitReason">${escapeHtml(t('habit.form.reason', '为什么要改变（可选）'))}</label><textarea id="habitReason" maxlength="500">${escapeHtml(program?.reason || '')}</textarea></div>
                <div class="habit-form-actions">
                    ${editing ? `<button type="button" class="habit-pause" id="habitPauseBtn">${escapeHtml(t('habit.pause', '暂停计划'))}</button>` : '<span></span>'}
                    <div class="habit-form-actions-end"><button type="button" data-close>${escapeHtml(t('common.cancel', '取消'))}</button><button type="submit" class="habit-save">${escapeHtml(t('common.save', '保存'))}</button></div>
                </div>
            </form>`
        );
        const form = modal.querySelector('#habitProgramForm');
        const syncMode = () => {
            const current = modal.querySelector('#habitMode').value;
            modal.querySelector('#habitMinimumField').hidden = current !== 'build';
            modal.querySelector('#habitReplacementField').hidden = current !== 'break';
            modal.querySelectorAll('[data-mode]').forEach((button) => button.classList.toggle('is-on', button.dataset.mode === current));
        };
        modal.querySelectorAll('[data-mode]').forEach((button) => button.addEventListener('click', () => {
            modal.querySelector('#habitMode').value = button.dataset.mode;
            syncMode();
        }));
        modal.querySelector('#habitActionId')?.addEventListener('change', (event) => {
            const selected = event.target.options[event.target.selectedIndex];
            if (!event.target.value) return;
            if (!modal.querySelector('#habitTitle').value.trim()) modal.querySelector('#habitTitle').value = selected.textContent.trim();
            if (!modal.querySelector('#habitMinimum').value.trim()) modal.querySelector('#habitMinimum').value = selected.textContent.trim();
        });
        modal.querySelector('[data-close]')?.addEventListener('click', closeModal);
        modal.querySelector('#habitPauseBtn')?.addEventListener('click', async () => {
            if (!window.confirm(t('habit.pauseConfirm', '暂停这个习惯计划？记录会保留。'))) return;
            await api(`/${program.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'paused' }) });
            closeModal();
            await loadHabitFocus();
        });
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const currentMode = modal.querySelector('#habitMode').value;
            const payload = {
                title: modal.querySelector('#habitTitle').value.trim(),
                anchor_text: modal.querySelector('#habitAnchor').value.trim(),
                minimum_action: currentMode === 'build' ? modal.querySelector('#habitMinimum').value.trim() : null,
                replacement_action: currentMode === 'break' ? modal.querySelector('#habitReplacement').value.trim() : null,
                target_days_per_week: Number(modal.querySelector('#habitTarget').value || 5),
                reason: modal.querySelector('#habitReason').value.trim() || null,
            };
            if (!editing) {
                payload.mode = currentMode;
                payload.action_id = Number(modal.querySelector('#habitActionId')?.value || actionId || 0) || null;
            }
            try {
                const result = await api(editing ? `/${program.id}` : '', {
                    method: editing ? 'PATCH' : 'POST',
                    body: JSON.stringify(payload),
                });
                state.program = result.program;
                state.summary = result.summary;
                closeModal();
                render();
                if (typeof showMessage === 'function') showMessage(t('habit.saved', '主要习惯已保存'), 'success');
            } catch (error) {
                if (typeof showMessage === 'function') showMessage(error.message, 'error');
            }
        });
        syncMode();
        modal.querySelector('#habitTitle')?.focus();
    }

    function openCheckIn(outcome) {
        if (!state.program) return;
        const isBreak = state.program.mode === 'break';
        const modal = modalShell(
            t('habit.checkin.title', '今天的反馈'),
            `<form class="habit-form" id="habitCheckInForm">
                <input type="hidden" id="habitOutcome" value="${escapeHtml(outcome)}">
                <div class="habit-field"><label>${escapeHtml(isBreak ? t('habit.checkin.urge', '当时的冲动强度') : t('habit.checkin.effort', '做起来有多费力'))}</label><div class="habit-scale-picks">${[1, 2, 3, 4, 5].map((value) => `<label><input type="radio" name="habitScale" value="${value}"${value === 3 ? ' checked' : ''}><span>${value}</span></label>`).join('')}</div></div>
                <div class="habit-field"><label for="habitBarrier">${escapeHtml(t('habit.checkin.barrier', '最大阻力（可选）'))}</label><select id="habitBarrier"><option value="">${escapeHtml(t('habit.checkin.none', '没有填写'))}</option><option value="time">${escapeHtml(t('habit.barrier.time', '时间不合适'))}</option><option value="forgot">${escapeHtml(t('habit.barrier.forgot', '忘记了'))}</option><option value="energy">${escapeHtml(t('habit.barrier.energy', '精力不足'))}</option><option value="environment">${escapeHtml(t('habit.barrier.environment', '环境打断'))}</option><option value="emotion">${escapeHtml(t('habit.barrier.emotion', '情绪影响'))}</option><option value="other">${escapeHtml(t('habit.barrier.other', '其他'))}</option></select></div>
                <div class="habit-field"><label for="habitCheckInNote">${escapeHtml(t('habit.checkin.note', '补充一句（可选）'))}</label><textarea id="habitCheckInNote" maxlength="500"></textarea></div>
                <div class="habit-form-actions"><span></span><div class="habit-form-actions-end"><button type="button" data-close>${escapeHtml(t('common.cancel', '取消'))}</button><button type="submit" class="habit-save">${escapeHtml(t('common.save', '保存'))}</button></div></div>
            </form>`
        );
        modal.querySelector('[data-close]')?.addEventListener('click', closeModal);
        modal.querySelector('#habitCheckInForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const scale = Number(modal.querySelector('input[name="habitScale"]:checked')?.value || 3);
            const payload = {
                event_date: todayISO(),
                outcome,
                effort: isBreak ? null : scale,
                urge: isBreak ? scale : null,
                barrier: modal.querySelector('#habitBarrier').value || null,
                note: modal.querySelector('#habitCheckInNote').value.trim() || null,
            };
            try {
                const result = await api(`/${state.program.id}/check-ins`, { method: 'POST', body: JSON.stringify(payload) });
                state.program = result.program;
                state.summary = result.summary;
                closeModal();
                render();
                if (typeof showMessage === 'function') showMessage(t('habit.checkin.saved', '今天的反馈已保存'), 'success');
            } catch (error) {
                if (typeof showMessage === 'function') showMessage(error.message, 'error');
            }
        });
    }

    async function scheduleCurrent() {
        if (!state.program) return;
        const taskDate = typeof window.getScheduleDay === 'function' ? window.getScheduleDay() : todayISO();
        try {
            const result = await api(`/${state.program.id}/schedule`, {
                method: 'POST',
                body: JSON.stringify({ task_date: taskDate }),
            });
            if (typeof window.loadDailySchedule === 'function') await window.loadDailySchedule();
            await loadHabitFocus();
            if (typeof showMessage === 'function') {
                showMessage(result.created ? t('habit.schedule.saved', '已排进这一天') : t('habit.schedule.exists', '这一天已经安排过了'), result.created ? 'success' : 'info');
            }
        } catch (error) {
            if (typeof showMessage === 'function') showMessage(error.message, 'error');
        }
    }

    function bindMount() {
        const mount = document.getElementById('habitFocusMount');
        if (!mount || mount.dataset.bound === '1') return;
        mount.dataset.bound = '1';
        mount.addEventListener('click', (event) => {
            const button = event.target.closest('[data-habit-act]');
            if (!button) return;
            const act = button.dataset.habitAct;
            if (act === 'create') openProgramForm(null);
            if (act === 'edit') openProgramForm(null);
            if (act === 'schedule') scheduleCurrent();
            if (act === 'checkin') openCheckIn(button.dataset.outcome);
        });
    }

    window.loadHabitFocus = loadHabitFocus;
    window.getActiveHabitProgram = () => state.program;
    window.openHabitProgram = (actionId) => openProgramForm(actionId || null);

    function onReady() {
        bindMount();
        if (window.authCheckSettled) loadHabitFocus();
        else window.addEventListener('auth-check-settled', loadHabitFocus, { once: true });
        window.addEventListener('shuran-language-change', render);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && document.getElementById('habitModal')) closeModal();
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
    else onReady();
})();
