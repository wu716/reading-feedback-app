(function () {
    let books = [];
    let currentBook = null;
    let currentChapter = null;
    let selectedText = '';
    let progressSaveTimer = null;
    let progressRequest = null;
    let allNotes = [];
    let notesView = 'book';
    let notesBookId = null;
    let readerReturnToNotes = false;

    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const api = (path, options) => apiRequest(`/api/ebooks${path}`, options || {});

    function renderQuota(data) {
        const hint = $('epubQuotaHint');
        if (!hint) return;
        const used = Math.round((data.used_bytes || 0) / 1024 / 1024);
        hint.textContent = `已使用 ${used}MB / 500MB`;
    }

    function renderShelf() {
        const shelf = $('epubShelf');
        if (!shelf) return;
        if (!books.length) {
            shelf.innerHTML = '<p class="epub-empty">还没有书。上传一本 EPUB，从一句话开始实践。</p>';
            return;
        }
        shelf.innerHTML = books.map((book) => `
            <div class="epub-book-card" data-book-id="${book.id}">
                <strong>${esc(book.title)}</strong>
                <span>${book.chapter_count} 个章节 · ${Math.round(book.file_size / 1024 / 1024)}MB</span>
                <div class="epub-book-actions"><button type="button" data-book-action="notes">查看笔记</button><button type="button" data-book-action="delete">删除书籍</button></div>
            </div>`).join('');
    }

    function downloadNotes(book, notes) {
        const blob = new Blob([JSON.stringify({ book: book.title, exported_at: new Date().toISOString(), notes }, null, 2)], { type: 'application/json' });
        const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${book.title}-读书笔记.json`; link.click(); URL.revokeObjectURL(link.href);
    }

    const thoughtLabels = { concept: '概念 / 模型', relation: '关系', process: '流程' };
    const relationLabels = { comparison: '比较', classification: '分类', set: '集合', correlation: '相关', causation: '因果' };

    function visibleNotes() {
        return notesBookId == null ? allNotes : allNotes.filter((note) => note.book_id === notesBookId);
    }

    function noteCard(note) {
        const label = thoughtLabels[note.thought_type] || '未分类';
        const relation = note.thought_type === 'relation' ? relationLabels[note.relation_type] || '未细分' : '';
        const date = note.created_at ? new Date(note.created_at).toLocaleDateString('zh-CN') : '';
        return `<article class="epub-note-card">
            <div class="epub-note-card-meta"><span>${esc(note.book_title)}</span><span>${esc(note.chapter_title)}</span><span class="epub-note-tag">${esc(label)}${relation ? ` · ${esc(relation)}` : ''}</span>${date ? `<time>${esc(date)}</time>` : ''}</div>
            <blockquote>${esc(note.selected_text)}</blockquote>
            <p>${esc(note.note_text)}</p>
            <div class="epub-note-card-actions"><button type="button" class="epub-note-source" data-note-source="${note.id}">定位原文 →</button></div>
        </article>`;
    }

    function noteGroup(title, notes, body) {
        return `<section class="epub-notes-group"><div class="epub-notes-group-head"><h2>${esc(title)}</h2><span>${notes.length} 条笔记</span></div>${body || notes.map(noteCard).join('')}</section>`;
    }

    function renderNotesPage() {
        const items = visibleNotes();
        $('epubNotesSummary').textContent = `共 ${items.length} 条笔记 · ${new Set(items.map((note) => note.book_id)).size} 本书`;
        const filter = $('epubNotesBookFilter');
        const bookOptions = new Map(books.map((book) => [book.id, book.title]));
        allNotes.forEach((note) => bookOptions.set(note.book_id, note.book_title));
        filter.innerHTML = '<option value="">全部书籍</option>' + [...bookOptions].sort((a, b) => a[1].localeCompare(b[1], 'zh-CN')).map(([id, title]) => `<option value="${id}">${esc(title)}</option>`).join('');
        filter.value = notesBookId == null ? '' : String(notesBookId);
        document.querySelectorAll('[data-notes-view]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.notesView === notesView)));
        if (!items.length) {
            $('epubNotesGroups').innerHTML = '<p class="epub-notes-empty">这里还没有笔记。读书时选中原文，写下想法后就会出现在这里。</p>';
            return;
        }
        if (notesView === 'book') {
            const groups = new Map();
            items.forEach((note) => {
                if (!groups.has(note.book_id)) groups.set(note.book_id, []);
                groups.get(note.book_id).push(note);
            });
            $('epubNotesGroups').innerHTML = [...groups.values()]
                .sort((a, b) => a[0].book_title.localeCompare(b[0].book_title, 'zh-CN'))
                .map((group) => noteGroup(group[0].book_title, group)).join('');
            return;
        }
        const typeOrder = ['concept', 'relation', 'process'];
        const relationOrder = ['comparison', 'classification', 'set', 'correlation', 'causation', 'other'];
        $('epubNotesGroups').innerHTML = typeOrder.map((type) => {
            const group = items.filter((note) => note.thought_type === type);
            if (!group.length) return '';
            if (type !== 'relation') return noteGroup(thoughtLabels[type], group);
            const subgroups = relationOrder.map((key) => {
                const subset = group.filter((note) => (relationLabels[note.relation_type] ? note.relation_type : 'other') === key);
                return subset.length ? `<h3 class="epub-notes-subhead">${esc(relationLabels[key] || '未细分')} · ${subset.length}</h3>${subset.map(noteCard).join('')}` : '';
            }).join('');
            return noteGroup(thoughtLabels[type], group, subgroups);
        }).join('');
    }

    async function loadNotesPage() {
        $('epubNotesGroups').innerHTML = '<p class="epub-notes-empty">正在读取笔记…</p>';
        try {
            const data = await api('/notes');
            allNotes = data.items || [];
            renderNotesPage();
        } catch (error) {
            $('epubNotesGroups').innerHTML = `<p class="epub-notes-empty">${esc(error.message || '笔记加载失败，请稍后重试')}</p>`;
        }
    }

    async function deleteBook(book) {
        const data = await api(`/${book.id}/notes`);
        if (data.items?.length) downloadNotes(book, data.items);
        if (!confirm(`确定删除《${book.title}》吗？${data.items?.length ? `已先下载 ${data.items.length} 条笔记备份。` : ''}\n书籍、章节和数据库中的笔记都会删除。`)) return;
        await api(`/${book.id}`, { method: 'DELETE' });
        showMessage('书籍已删除', 'success'); await loadBooks();
    }

    async function openNoteSource(note) {
        const book = books.find((item) => item.id === note.book_id) || await api(`/${note.book_id}`);
        window.openEpubLibrary();
        await openBook(book, note.chapter_id, note.selected_text);
    }

    async function loadBooks() {
        try {
            const data = await api('');
            books = data.items || [];
            renderQuota(data);
            renderShelf();
        } catch (error) {
            if ($('epubQuotaHint')) $('epubQuotaHint').textContent = error.message || '书架加载失败';
        }
    }

    async function uploadBook() {
        const input = $('epubFileInput');
        const file = input?.files?.[0];
        if (!file) return showMessage('请选择 EPUB 文件', 'error');
        if (file.size > 120 * 1024 * 1024) return showMessage('单本 EPUB 不能超过 120MB', 'error');
        const form = new FormData();
        form.append('file', file);
        const button = $('epubUploadBtn');
        if (button) button.disabled = true;
        try {
            await api('/upload', { method: 'POST', body: form });
            input.value = '';
            showMessage('上传完成，可以开始阅读了', 'success');
            await loadBooks();
        } catch (error) {
            showMessage(error.message || '上传失败', 'error');
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function openBook(book, targetChapterId = null, sourceQuote = '') {
        if (currentBook && currentChapter) await persistProgress();
        currentChapter = null;
        currentBook = book;
        readerReturnToNotes = Boolean(targetChapterId);
        $('epubBookTitle').textContent = book.title;
        $('epubShelf').hidden = true;
        $('epubReader').hidden = false;
        $('epubChapterList').innerHTML = book.chapters.map((chapter) => `<button type="button" data-chapter-id="${chapter.id}">${esc(chapter.title)}</button>`).join('');
        const targetChapter = targetChapterId && book.chapters.find((item) => item.id === targetChapterId);
        const savedChapter = book.progress && book.chapters.find((item) => item.id === book.progress.chapter_id);
        await openChapter(targetChapter || savedChapter || book.chapters[0], targetChapter ? 0 : savedChapter ? book.progress.scroll_ratio : 0, sourceQuote);
    }

    function focusSourceQuote(quote) {
        const paragraphs = $('epubChapterText').querySelectorAll('p');
        const positions = [];
        let searchable = '';
        for (const paragraph of paragraphs) {
            const node = paragraph.firstChild;
            if (!node) continue;
            if (searchable && !searchable.endsWith(' ')) {
                searchable += ' ';
                positions.push({ node, offset: 0 });
            }
            for (let offset = 0; offset < node.length; offset++) {
                const character = node.textContent[offset];
                if (/\s/.test(character)) {
                    if (searchable.endsWith(' ')) continue;
                    searchable += ' ';
                } else {
                    searchable += character.toLowerCase();
                }
                positions.push({ node, offset });
            }
        }
        const needle = quote.replace(/\s+/g, ' ').trim().toLowerCase();
        const start = searchable.indexOf(needle);
        if (!needle || start < 0) return false;
        const first = positions[start];
        const last = positions[start + needle.length - 1];
        const range = document.createRange();
        range.setStart(first.node, first.offset);
        range.setEnd(last.node, last.offset + 1);
        if (window.CSS?.highlights && window.Highlight) {
            CSS.highlights.set('epub-source-quote', new Highlight(range));
        } else {
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }
        first.node.parentElement.scrollIntoView({ block: 'center', behavior: 'smooth' });
        return true;
    }

    async function openChapter(chapter, savedRatio = 0, sourceQuote = '') {
        if (currentChapter && currentBook) await persistProgress();
        currentChapter = chapter;
        selectedText = '';
        if (window.CSS?.highlights) CSS.highlights.delete('epub-source-quote');
        window.getSelection()?.removeAllRanges();
        $('epubSourceStatus').hidden = true;
        const data = await api(`/${currentBook.id}/chapters/${chapter.id}`);
        $('epubChapterTitle').textContent = data.title;
        $('epubChapterText').innerHTML = esc(data.text).split(/\n+/).filter(Boolean).map((line) => `<p>${line}</p>`).join('');
        requestAnimationFrame(() => {
            const content = $('epubChapterText').parentElement;
            content.scrollTop = Math.round((content.scrollHeight - content.clientHeight) * Math.min(10000, Math.max(0, savedRatio)) / 10000);
            if (sourceQuote && !focusSourceQuote(sourceQuote)) {
                $('epubSourceStatus').textContent = '已打开笔记所属章节，但摘录与当前正文未能精确匹配。';
                $('epubSourceStatus').hidden = false;
            }
        });
        document.querySelectorAll('#epubChapterList button').forEach((button) => button.classList.toggle('active', Number(button.dataset.chapterId) === chapter.id));
        $('epubSelectedText').textContent = '先在正文中选中一句话';
        $('epubNoteInput').value = '';
        $('epubActionInput').value = '';
        updateActionMode();
    }

    function progressPayload() {
        if (!currentBook || !currentChapter) return;
        const content = $('epubChapterText').parentElement;
        const max = Math.max(1, content.scrollHeight - content.clientHeight);
        const ratio = Math.round((content.scrollTop / max) * 10000);
        return { bookId: currentBook.id, chapterId: currentChapter.id, scrollRatio: ratio };
    }

    function persistProgress() {
        const payload = progressPayload();
        if (!payload) return Promise.resolve();
        clearTimeout(progressSaveTimer);
        progressRequest = api(`/${payload.bookId}/progress`, {
            method: 'PUT', body: JSON.stringify({ chapter_id: payload.chapterId, scroll_ratio: payload.scrollRatio })
        }).then((data) => {
            if (currentBook?.id === payload.bookId) currentBook.progress = data;
        }).catch(() => {}).finally(() => { progressRequest = null; });
        return progressRequest;
    }

    function saveProgress() {
        clearTimeout(progressSaveTimer);
        progressSaveTimer = setTimeout(() => persistProgress(), 400);
    }

    function saveProgressBeforeLeaving() {
        const payload = progressPayload();
        if (!payload) return;
        clearTimeout(progressSaveTimer);
        const token = localStorage.getItem('authToken');
        if (!token || typeof API_BASE === 'undefined') return;
        fetch(`${API_BASE}/api/ebooks/${payload.bookId}/progress`, {
            method: 'PUT',
            keepalive: true,
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ chapter_id: payload.chapterId, scroll_ratio: payload.scrollRatio })
        }).catch(() => {});
    }

    function captureSelection() {
        const selection = window.getSelection();
        const value = selection ? selection.toString().trim() : '';
        if (!value || !currentChapter) return;
        selectedText = value.slice(0, 10000);
        $('epubSelectedText').textContent = `“${selectedText}”`;
        $('epubNoteInput').value = '';
        $('epubNoteBox').hidden = false;
        if (window.matchMedia('(max-width: 700px)').matches) {
            $('epubNoteBox').scrollIntoView({ behavior: 'smooth', block: 'start' });
            setTimeout(() => $('epubNoteInput')?.focus({ preventScroll: true }), 350);
        }
    }

    function openMobileNoteBox() {
        if (!window.matchMedia('(max-width: 700px)').matches) return;
        $('epubNoteBox')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showMessage('请先在正文中选中一句话，再写下你的理解', 'info');
    }

    async function saveNote() {
        const note = $('epubNoteInput').value.trim();
        if (!selectedText) return showMessage('请先在正文中选中一段内容', 'error');
        if (!note) return showMessage('请先写下你的想法', 'error');
        const thoughtType = document.querySelector('input[name="epubThoughtType"]:checked')?.value || 'concept';
        const relationType = $('epubRelationType').value || null;
        if (thoughtType === 'relation' && !relationType) return showMessage('请选择关系类型', 'error');
        await api(`/${currentBook.id}/notes`, { method: 'POST', body: JSON.stringify({ chapter_id: currentChapter.id, selected_text: selectedText, note_text: note, thought_type: thoughtType, relation_type: relationType }) });
        showMessage('想法已保存', 'success');
    }

    async function makeAction() {
        const note = $('epubNoteInput').value.trim();
        if (!selectedText) return showMessage('请先在正文中选中一段内容', 'error');
        if (!note) return showMessage('请先写下你的想法', 'error');
        const thoughtType = document.querySelector('input[name="epubThoughtType"]:checked')?.value || 'concept';
        if (thoughtType !== 'process') return showMessage('只有流程类想法可以加入今天', 'error');
        const mode = document.querySelector('input[name="epubActionMode"]:checked')?.value || 'manual';
        const actionText = $('epubActionInput').value.trim();
        if (mode === 'manual' && !actionText) return showMessage('请写下要执行的具体行动', 'error');
        try {
            const action = await api(`/${currentBook.id}/action`, { method: 'POST', body: JSON.stringify({ chapter_id: currentChapter.id, selected_text: selectedText, note_text: note, mode, action_text: mode === 'manual' ? actionText : null, thought_type: thoughtType }) });
            await apiRequest('/api/schedule/tasks', { method: 'POST', body: JSON.stringify({ text: action.action_text, action_id: action.id, priority: 0 }) });
            showMessage(`已生成行动项，并加入今天的日程：${action.action_text}`, 'success');
        } catch (error) {
            showMessage(error.message || '行动项生成失败', 'error');
        }
    }

    function updateActionMode() {
        const mode = document.querySelector('input[name="epubActionMode"]:checked')?.value || 'manual';
        const manualInput = $('epubActionInput');
        const aiHint = $('epubAiHint');
        const button = $('epubActionBtn');
        if (manualInput) manualInput.hidden = mode !== 'manual';
        if (aiHint) aiHint.hidden = mode !== 'ai';
        if (button) button.textContent = mode === 'ai' ? 'AI 生成并加入今天' : '加入今天';
    }

    function updateThoughtType() {
        const type = document.querySelector('input[name="epubThoughtType"]:checked')?.value || 'concept';
        const relation = $('epubRelationType');
        const prompt = $('epubThoughtPrompt');
        if (relation) relation.hidden = type !== 'relation';
        if (prompt) prompt.textContent = type === 'concept' ? '这段内容让我理解了什么概念或模型？' : type === 'relation' ? '这段内容揭示了什么关系？由此形成了什么判断？' : '这段内容让我以后具体怎么做？';
        document.querySelector('.epub-action-choice')?.toggleAttribute('hidden', type !== 'process');
        $('epubActionInput')?.toggleAttribute('hidden', type !== 'process');
        $('epubActionBtn')?.toggleAttribute('hidden', type !== 'process');
    }

    function onReady() {
        if (!$('epubUploadBtn')) return;
        $('epubUploadBtn').addEventListener('click', uploadBook);
        $('epubAllNotesBtn').addEventListener('click', () => window.openEpubNotes());
        $('epubNotesBackBtn').addEventListener('click', () => window.openEpubLibrary());
        $('epubNotesBookFilter').addEventListener('change', (event) => {
            notesBookId = event.target.value ? Number(event.target.value) : null;
            renderNotesPage();
        });
        $('epubNotesExportBtn').addEventListener('click', () => {
            const items = visibleNotes();
            if (!items.length) return showMessage('当前没有可下载的笔记', 'info');
            const title = notesBookId == null ? '全部读书笔记' : items[0].book_title;
            downloadNotes({ title }, items);
        });
        document.querySelectorAll('[data-notes-view]').forEach((button) => button.addEventListener('click', () => {
            notesView = button.dataset.notesView;
            renderNotesPage();
        }));
        $('epubNotesGroups').addEventListener('click', (event) => {
            const button = event.target.closest('[data-note-source]');
            const note = allNotes.find((item) => item.id === Number(button?.dataset.noteSource));
            if (note) openNoteSource(note).catch((error) => showMessage(error.message || '打开原文失败', 'error'));
        });
        $('epubFileInput')?.addEventListener('change', (event) => {
            const name = $('epubFileName');
            const file = event.target.files?.[0];
            if (name) name.textContent = file ? file.name : '选择一本 EPUB 书籍';
        });
        $('epubSaveNoteBtn').addEventListener('click', () => saveNote().catch((e) => showMessage(e.message, 'error')));
        $('epubActionBtn').addEventListener('click', makeAction);
        $('epubMobileNoteTrigger')?.addEventListener('click', openMobileNoteBox);
        document.querySelectorAll('input[name="epubActionMode"]').forEach((input) => input.addEventListener('change', updateActionMode));
        updateActionMode();
        document.querySelectorAll('input[name="epubThoughtType"]').forEach((input) => input.addEventListener('change', updateThoughtType));
        updateThoughtType();
        $('epubBackBtn').addEventListener('click', async () => {
            await persistProgress();
            $('epubReader').hidden = true;
            $('epubShelf').hidden = false;
            if (readerReturnToNotes) {
                readerReturnToNotes = false;
                navigateTo('ebook-notes');
            }
        });
        $('epubShelf').addEventListener('click', (event) => {
            const card = event.target.closest('[data-book-id]');
            const book = books.find((item) => item.id === Number(card?.dataset.bookId));
            const action = event.target.closest('[data-book-action]')?.dataset.bookAction;
            if (book && action === 'notes') return window.openEpubNotes(book.id);
            if (book && action === 'delete') return deleteBook(book).catch((e) => showMessage(e.message, 'error'));
            if (book) openBook(book).catch((e) => showMessage(e.message, 'error'));
        });
        $('epubChapterList').addEventListener('click', (event) => {
            const button = event.target.closest('[data-chapter-id]');
            const chapter = currentBook?.chapters.find((item) => item.id === Number(button?.dataset.chapterId));
            if (chapter) openChapter(chapter).catch((e) => showMessage(e.message, 'error'));
        });
        $('epubChapterText').addEventListener('mouseup', captureSelection);
        $('epubChapterText').addEventListener('touchend', captureSelection);
        $('epubChapterText').parentElement.addEventListener('scroll', saveProgress, { passive: true });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') saveProgressBeforeLeaving();
        });
        window.addEventListener('pagehide', saveProgressBeforeLeaving);
        const originalSwitch = window.switchUploadTab;
        window.switchUploadTab = function (tab) {
            if (typeof originalSwitch === 'function') originalSwitch(tab);
            if (tab === 'epub') loadBooks();
        };
    }

    window.openEpubLibrary = function () {
        if (typeof navigateTo === 'function') navigateTo('upload');
        document.getElementById('upload')?.classList.add('epub-only');
        document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.section === 'library'));
        setTimeout(() => window.switchUploadTab?.('epub'), 0);
    };

    window.openEpubNotes = function (bookId = null) {
        notesBookId = bookId;
        if (typeof navigateTo === 'function') navigateTo('ebook-notes');
    };

    window.loadEpubNotesPage = loadNotesPage;

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
    else onReady();
}());
