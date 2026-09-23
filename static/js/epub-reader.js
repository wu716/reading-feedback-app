(function () {
    let books = [];
    let currentBook = null;
    let currentChapter = null;
    let selectedText = '';

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
            <button type="button" class="epub-book-card" data-book-id="${book.id}">
                <strong>${esc(book.title)}</strong>
                <span>${book.chapter_count} 个章节 · ${Math.round(book.file_size / 1024 / 1024)}MB</span>
            </button>`).join('');
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

    async function openBook(book) {
        currentBook = book;
        $('epubBookTitle').textContent = book.title;
        $('epubShelf').hidden = true;
        $('epubReader').hidden = false;
        $('epubChapterList').innerHTML = book.chapters.map((chapter) => `<button type="button" data-chapter-id="${chapter.id}">${esc(chapter.title)}</button>`).join('');
        await openChapter(book.chapters[0]);
    }

    async function openChapter(chapter) {
        currentChapter = chapter;
        selectedText = '';
        const data = await api(`/${currentBook.id}/chapters/${chapter.id}`);
        $('epubChapterTitle').textContent = data.title;
        $('epubChapterText').innerHTML = esc(data.text).split(/\n+/).filter(Boolean).map((line) => `<p>${line}</p>`).join('');
        document.querySelectorAll('#epubChapterList button').forEach((button) => button.classList.toggle('active', Number(button.dataset.chapterId) === chapter.id));
        $('epubSelectedText').textContent = '先在正文中选中一句话';
        $('epubNoteInput').value = '';
        $('epubActionInput').value = '';
        updateActionMode();
    }

    function captureSelection() {
        const selection = window.getSelection();
        const value = selection ? selection.toString().trim() : '';
        if (!value || !currentChapter) return;
        selectedText = value.slice(0, 10000);
        $('epubSelectedText').textContent = `“${selectedText}”`;
        $('epubNoteInput').value = '';
        $('epubNoteBox').hidden = false;
    }

    async function saveNote() {
        const note = $('epubNoteInput').value.trim();
        if (!selectedText) return showMessage('请先在正文中选中一段内容', 'error');
        if (!note) return showMessage('请先写下你的想法', 'error');
        await api(`/${currentBook.id}/notes`, { method: 'POST', body: JSON.stringify({ chapter_id: currentChapter.id, selected_text: selectedText, note_text: note }) });
        showMessage('想法已保存', 'success');
    }

    async function makeAction() {
        const note = $('epubNoteInput').value.trim();
        if (!selectedText) return showMessage('请先在正文中选中一段内容', 'error');
        if (!note) return showMessage('请先写下你的想法', 'error');
        const mode = document.querySelector('input[name="epubActionMode"]:checked')?.value || 'manual';
        const actionText = $('epubActionInput').value.trim();
        if (mode === 'manual' && !actionText) return showMessage('请写下要执行的具体行动', 'error');
        try {
            const action = await api(`/${currentBook.id}/action`, { method: 'POST', body: JSON.stringify({ chapter_id: currentChapter.id, selected_text: selectedText, note_text: note, mode, action_text: mode === 'manual' ? actionText : null }) });
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

    function onReady() {
        if (!$('epubUploadBtn')) return;
        $('epubUploadBtn').addEventListener('click', uploadBook);
        $('epubSaveNoteBtn').addEventListener('click', () => saveNote().catch((e) => showMessage(e.message, 'error')));
        $('epubActionBtn').addEventListener('click', makeAction);
        document.querySelectorAll('input[name="epubActionMode"]').forEach((input) => input.addEventListener('change', updateActionMode));
        updateActionMode();
        $('epubBackBtn').addEventListener('click', () => { $('epubReader').hidden = true; $('epubShelf').hidden = false; });
        $('epubShelf').addEventListener('click', (event) => {
            const card = event.target.closest('[data-book-id]');
            const book = books.find((item) => item.id === Number(card?.dataset.bookId));
            if (book) openBook(book).catch((e) => showMessage(e.message, 'error'));
        });
        $('epubChapterList').addEventListener('click', (event) => {
            const button = event.target.closest('[data-chapter-id]');
            const chapter = currentBook?.chapters.find((item) => item.id === Number(button?.dataset.chapterId));
            if (chapter) openChapter(chapter).catch((e) => showMessage(e.message, 'error'));
        });
        $('epubChapterText').addEventListener('mouseup', captureSelection);
        $('epubChapterText').addEventListener('touchend', captureSelection);
        const originalSwitch = window.switchUploadTab;
        window.switchUploadTab = function (tab) {
            if (typeof originalSwitch === 'function') originalSwitch(tab);
            if (tab === 'epub') loadBooks();
        };
    }

    window.openEpubLibrary = function () {
        if (typeof navigateTo === 'function') navigateTo('upload');
        document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.section === 'library'));
        setTimeout(() => window.switchUploadTab?.('epub'), 0);
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
    else onReady();
}());
