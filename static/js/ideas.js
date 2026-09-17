/**
 * 灵感：快捷记下的去处之一，按时间倒序。
 */
(function () {
    let items = [];
    let editingId = null;

    function escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatWhen(iso) {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return '';
        return d.toLocaleString('zh-CN', {
            month: 'numeric',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });
    }

    async function load() {
        const box = document.getElementById('ideasList');
        if (!box) return;
        try {
            const data = await apiRequest('/api/capture/ideas');
            items = data.items || [];
            render();
        } catch (e) {
            box.innerHTML = `<p class="flow-empty">${escapeHtml(e.message || '加载失败')}</p>`;
        }
    }

    function render() {
        const box = document.getElementById('ideasList');
        if (!box) return;
        if (!items.length) {
            box.innerHTML = '<p class="flow-empty">三击或点「记」，去处选「灵感」，写下就会出现在这里。</p>';
            return;
        }
        box.innerHTML = items.map((item) => {
            const editing = editingId === item.id;
            const body = editing
                ? `<input type="text" class="flow-task-text-input" maxlength="500" value="${escapeHtml(item.text)}" data-idea-act="text" aria-label="修改灵感">`
                : `<div class="flow-task-text" data-idea-act="edit" title="点此修改">${escapeHtml(item.text)}</div>`;
            return `
                <article class="schedule-later-item" data-idea-id="${item.id}">
                    <div class="flow-task-main">
                        ${body}
                        <div class="tl-duration">${escapeHtml(formatWhen(item.created_at))}</div>
                    </div>
                    <div class="flow-task-actions">
                        <button type="button" data-idea-act="edit">${editing ? '保存' : '修改'}</button>
                        <button type="button" class="flow-mini-btn flow-danger" data-idea-act="delete">删除</button>
                    </div>
                </article>`;
        }).join('');
        if (editingId) {
            const input = box.querySelector(`[data-idea-id="${editingId}"] [data-idea-act="text"]`);
            if (input) {
                input.focus();
                const len = input.value.length;
                input.setSelectionRange(len, len);
            }
        }
    }

    async function saveEdit(id, text) {
        const next = String(text || '').trim();
        if (!next) {
            if (typeof showMessage === 'function') showMessage('请先写下内容', 'error');
            return;
        }
        try {
            await apiRequest(`/api/capture/ideas/${id}`, {
                method: 'PATCH',
                body: JSON.stringify({ text: next }),
            });
            editingId = null;
            await load();
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
    }

    async function remove(id) {
        if (!window.confirm('确定删除这条灵感？')) return;
        try {
            const data = await apiRequest(`/api/capture/ideas/${id}`, { method: 'DELETE' });
            items = data.items || [];
            editingId = null;
            render();
        } catch (e) {
            if (typeof showMessage === 'function') showMessage(e.message, 'error');
        }
    }

    function onReady() {
        const list = document.getElementById('ideasList');
        if (!list) return;
        list.addEventListener('click', async (e) => {
            const article = e.target.closest('[data-idea-id]');
            if (!article) return;
            const id = parseInt(article.dataset.ideaId, 10);
            const act = e.target.dataset.ideaAct;
            if (act === 'delete') {
                remove(id);
                return;
            }
            if (act === 'edit') {
                if (editingId === id) {
                    const input = article.querySelector('[data-idea-act="text"]');
                    await saveEdit(id, input?.value);
                    return;
                }
                editingId = id;
                render();
            }
        });
        list.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter' || e.shiftKey) return;
            const input = e.target.closest('[data-idea-act="text"]');
            if (!input) return;
            e.preventDefault();
            const article = input.closest('[data-idea-id]');
            const id = parseInt(article?.dataset.ideaId, 10);
            if (id) saveEdit(id, input.value);
        });
        document.getElementById('ideasAddBtn')?.addEventListener('click', () => {
            if (typeof window.punchTimeLog === 'function') {
                window.punchTimeLog(false, 'idea');
            }
        });
    }

    window.loadIdeas = load;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
