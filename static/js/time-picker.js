/**
 * 底部双滚轮时间选择器：时 / 分，紫配色，替代系统绿色圆盘时钟。
 */
(function () {
    const ITEM_H = 44;
    const PAD = 2;
    const PRESETS = ['07:00', '08:00', '09:00', '12:00', '18:00', '20:00', '21:00', '22:00'];
    const RECORD_PRESETS = ['07:00', '12:00', '18:00', '21:00'];

    function pad2(n) {
        return String(n).padStart(2, '0');
    }

    function toHHmm(raw) {
        if (raw == null) return '';
        const match = String(raw).trim().match(/(\d{1,2}):(\d{2})/);
        if (!match) return '';
        const hour = Math.min(23, Math.max(0, Number(match[1])));
        const minute = Math.min(59, Math.max(0, Number(match[2])));
        return `${pad2(hour)}:${pad2(minute)}`;
    }

    function clockIcon() {
        return '<svg class="tp-clock-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>';
    }

    function ensureOverlay() {
        let overlay = document.getElementById('tpOverlay');
        if (overlay) return overlay;
        overlay = document.createElement('div');
        overlay.id = 'tpOverlay';
        overlay.className = 'tp-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        overlay.innerHTML = [
            '<div class="tp-sheet" role="dialog" aria-modal="true" aria-labelledby="tpTitle">',
            '  <div class="tp-head">',
            '    <button type="button" class="tp-text-btn tp-cancel">取消</button>',
            '    <div class="tp-title-wrap"><div class="tp-title" id="tpTitle">选择时间</div><small class="tp-subtitle" id="tpSubtitle"></small></div>',
            '    <button type="button" class="tp-text-btn tp-ok">确定</button>',
            '  </div>',
            '  <div class="tp-presets" id="tpPresets"></div>',
            '  <div class="tp-selected-time" id="tpSelectedTime" aria-live="polite">20:00</div>',
            '  <div class="tp-wheels">',
            '    <div class="tp-highlight"></div>',
            '    <div class="tp-col" id="tpHourCol"></div>',
            '    <div class="tp-colon">:</div>',
            '    <div class="tp-col" id="tpMinuteCol"></div>',
            '  </div>',
            '  <button type="button" class="tp-clear" id="tpClear">不设置提醒</button>',
            '  <button type="button" class="tp-close" aria-label="关闭">×</button>',
            '  <div class="tp-footer"><button type="button" class="tp-footer-cancel">取消</button><button type="button" class="tp-footer-ok">保存时间</button></div>',
            '</div>',
        ].join('');
        document.body.appendChild(overlay);

        renderPresets(overlay, PRESETS);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cancel();
        });
        overlay.addEventListener('pointerdown', (e) => {
            if (e.target === overlay) {
                e.preventDefault();
                cancel();
            }
        });
        overlay.querySelector('.tp-cancel').addEventListener('click', cancel);
        overlay.querySelector('.tp-ok').addEventListener('click', confirm);
        overlay.querySelector('.tp-footer-cancel').addEventListener('click', cancel);
        overlay.querySelector('.tp-footer-ok').addEventListener('click', confirm);
        overlay.querySelector('.tp-close').addEventListener('click', cancel);
        overlay.querySelector('#tpClear').addEventListener('click', clearTime);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('is-open')) {
                e.preventDefault();
                cancel();
            }
        });
        overlay.querySelector('#tpPresets').addEventListener('click', (e) => {
            const btn = e.target.closest('.tp-preset');
            if (!btn) return;
            setWheels(btn.dataset.time);
        });
        return overlay;
    }

    function renderPresets(overlay, times) {
        const presets = overlay.querySelector('#tpPresets');
        const signature = times.join(',');
        if (presets.dataset.times === signature) return;
        presets.dataset.times = signature;
        presets.replaceChildren();
        times.forEach((time) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'tp-preset';
            btn.dataset.time = time;
            btn.textContent = time;
            presets.appendChild(btn);
        });
    }

    function buildColumn(col, count, unit, loop) {
        col.innerHTML = '';
        col.dataset.tpCount = String(count);
        col.dataset.tpLoop = String(loop);
        const frag = document.createDocumentFragment();
        for (let i = 0; i < PAD; i++) {
            const pad = document.createElement('div');
            pad.className = 'tp-item is-pad';
            pad.textContent = '';
            frag.appendChild(pad);
        }
        const cycles = loop ? 5 : 1;
        for (let cycle = 0; cycle < cycles; cycle++) {
            for (let i = 0; i < count; i++) {
                const index = cycle * count + i;
                const el = document.createElement('div');
                el.className = 'tp-item';
                el.dataset.value = String(i);
                el.dataset.index = String(index);
                el.innerHTML = `<span>${pad2(i)}</span><span class="tp-unit">${unit}</span>`;
                el.addEventListener('click', () => scrollToIndex(col, index, true));
                frag.appendChild(el);
            }
        }
        for (let i = 0; i < PAD; i++) {
            const pad = document.createElement('div');
            pad.className = 'tp-item is-pad';
            pad.textContent = '';
            frag.appendChild(pad);
        }
        col.appendChild(frag);
        bindColumn(col);
    }

    function bindColumn(col) {
        if (col.dataset.tpBound) return;
        col.dataset.tpBound = '1';
        const snap = () => {
            const count = Number(col.dataset.tpCount) || 24;
            const loop = col.dataset.tpLoop === 'true';
            const maxIndex = (loop ? 5 : 1) * count - 1;
            const index = Math.min(maxIndex, Math.max(0, Math.round(col.scrollTop / ITEM_H)));
            scrollToIndex(col, index, true);
            if (loop && (index < count || index >= count * 4)) {
                const selected = col.querySelector(`.tp-item[data-index="${index}"]`);
                const value = Number(selected?.dataset.value || 0);
                scrollToIndex(col, count * 2 + value, false);
            }
        };
        col.addEventListener('scroll', () => {
            updateActive(col);
            syncPresets();
            clearTimeout(col._tpTimer);
            col._tpTimer = setTimeout(snap, 90);
        }, { passive: true });
        col.addEventListener('scrollend', snap);
    }

    function updateActive(col) {
        const idx = Math.round(col.scrollTop / ITEM_H);
        col.querySelectorAll('.tp-item[data-value]').forEach((el) => {
            el.classList.toggle('is-active', Number(el.dataset.index) === idx);
        });
    }

    function scrollToIndex(col, index, smooth) {
        const count = Number(col.dataset.tpCount) || 24;
        const loop = col.dataset.tpLoop === 'true';
        const maxIndex = (loop ? 5 : 1) * count - 1;
        const safeIndex = Math.min(maxIndex, Math.max(0, index));
        const top = safeIndex * ITEM_H;
        if (Math.abs(col.scrollTop - top) > 1) {
            col.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
        }
        updateActive(col);
    }

    function columnValue(col) {
        const index = Math.round(col.scrollTop / ITEM_H);
        const selected = col.querySelector(`.tp-item[data-index="${index}"]`);
        return Number(selected?.dataset.value || 0);
    }

    function currentValue() {
        const overlay = ensureOverlay();
        const hour = columnValue(overlay.querySelector('#tpHourCol'));
        const minute = columnValue(overlay.querySelector('#tpMinuteCol'));
        const value = `${pad2(hour)}:${pad2(minute)}`;
        const display = overlay.querySelector('#tpSelectedTime');
        if (display) display.textContent = value;
        return value;
    }

    function syncPresets() {
        const overlay = document.getElementById('tpOverlay');
        if (!overlay) return;
        const value = currentValue();
        overlay.querySelectorAll('.tp-preset').forEach((btn) => {
            btn.classList.toggle('is-active', btn.dataset.time === value);
        });
    }

    function setWheels(hhmm) {
        const value = toHHmm(hhmm) || '20:00';
        const [h, m] = value.split(':').map(Number);
        const overlay = ensureOverlay();
        const base = activeLoop ? 2 : 0;
        scrollToIndex(overlay.querySelector('#tpHourCol'), base * 24 + h, false);
        scrollToIndex(overlay.querySelector('#tpMinuteCol'), base * 60 + m, false);
        syncPresets();
    }

    let resolver = null;
    let hourColReady = false;
    let builtLoopMode = null;
    let activeLoop = false;

    function finish(result) {
        const overlay = document.getElementById('tpOverlay');
        if (overlay) {
            overlay.classList.remove('is-open', 'is-optional');
            overlay.setAttribute('aria-hidden', 'true');
        }
        document.body.style.overflow = '';
        const resolve = resolver;
        resolver = null;
        if (resolve) resolve(result);
    }

    function cancel() {
        finish(undefined);
    }

    function confirm() {
        finish(currentValue());
    }

    function clearTime() {
        finish('');
    }

    function pick(options = {}) {
        const overlay = ensureOverlay();
        if (overlay.classList.contains('is-open')) {
            cancel();
            return Promise.resolve(undefined);
        }
        activeLoop = options.loop === true;
        if (!hourColReady || builtLoopMode !== activeLoop) {
            buildColumn(overlay.querySelector('#tpHourCol'), 24, '时', activeLoop);
            buildColumn(overlay.querySelector('#tpMinuteCol'), 60, '分', activeLoop);
            hourColReady = true;
            builtLoopMode = activeLoop;
        }
        overlay.querySelector('#tpTitle').textContent = options.title || '选择时间';
        const locale = window.shuranI18n?.getLanguage?.() || 'zh-CN';
        overlay.querySelector('#tpSubtitle').textContent = options.subtitle || (locale === 'en' ? 'Beijing Time · 24-hour clock' : '北京时间 · 24 小时制');
        overlay.querySelector('.tp-footer-cancel').textContent = locale === 'en' ? 'Cancel' : '取消';
        overlay.querySelector('.tp-footer-ok').textContent = locale === 'en' ? 'Save time' : '保存时间';
        overlay.querySelector('.tp-close').setAttribute('aria-label', locale === 'en' ? 'Close' : '关闭');
        overlay.classList.toggle('is-shuran', options.variant === 'shuran');
        renderPresets(overlay, options.presets || (options.variant === 'shuran' ? RECORD_PRESETS : PRESETS));
        overlay.classList.toggle('is-optional', !!options.optional);
        overlay.classList.add('is-open');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        const initial = options.value || '20:00';
        setWheels(initial);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => setWheels(initial));
        });
        return new Promise((resolve) => {
            resolver = resolve;
        });
    }

    function labelFor(input, value) {
        if (value) return value;
        if (input.classList.contains('todo-remind-input')) return '时间';
        return '选择';
    }

    function syncButton(input, btn) {
        const value = toHHmm(input.value);
        btn.classList.toggle('is-empty', !value);
        btn.innerHTML = `${clockIcon()}<span>${labelFor(input, value)}</span>`;
        btn.setAttribute('aria-label', value ? `${input.dataset.timeTitle || '时间'} ${value}` : (input.getAttribute('aria-label') || '选择时间'));
        btn.title = input.title || '选择时间';
    }

    function patchValue(input, btn) {
        const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        Object.defineProperty(input, 'value', {
            configurable: true,
            enumerable: true,
            get() {
                return toHHmm(desc.get.call(this));
            },
            set(next) {
                desc.set.call(this, toHHmm(next));
                syncButton(input, btn);
            },
        });
    }

    function enhance(input) {
        if (!input || input.dataset.tpBound === '1') return;
        input.dataset.tpBound = '1';
        input.classList.add('tp-native-hidden');
        input.setAttribute('tabindex', '-1');
        input.setAttribute('aria-hidden', 'true');
        const wrap = document.createElement('div');
        wrap.className = 'tp-field';
        if (input.classList.contains('me-control')) wrap.classList.add('tp-field-me');
        if (input.classList.contains('todo-remind-input')) wrap.classList.add('tp-field-todo');
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'tp-field-btn';
        wrap.appendChild(btn);
        patchValue(input, btn);
        syncButton(input, btn);

        const optional = input.classList.contains('todo-remind-input') || input.dataset.optional === 'true';
        btn.addEventListener('click', async () => {
            if (input.disabled) return;
            const picked = await pick({
                value: input.value || '20:00',
                title: input.dataset.timeTitle || input.getAttribute('aria-label') || '选择时间',
                optional,
                subtitle: input.dataset.timeSubtitle || undefined,
                variant: input.dataset.timeVariant || undefined,
                loop: input.dataset.timeLoop === 'true',
                presets: input.dataset.timePresets ? input.dataset.timePresets.split(',') : undefined,
            });
            if (picked === undefined) return;
            input.value = picked;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        });
    }

    function bindAll(root) {
        (root || document).querySelectorAll('input[type="time"]').forEach(enhance);
    }

    window.TimePicker = { pick, enhance, bindAll, toHHmm };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => bindAll(document));
    } else {
        bindAll(document);
    }
})();
