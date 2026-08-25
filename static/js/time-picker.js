/**
 * 底部双滚轮时间选择器：时 / 分，紫配色，替代系统绿色圆盘时钟。
 */
(function () {
    const ITEM_H = 44;
    const PAD = 2;
    const PRESETS = ['07:00', '08:00', '09:00', '12:00', '18:00', '20:00', '21:00', '22:00'];

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
            '    <div class="tp-title" id="tpTitle">选择时间</div>',
            '    <button type="button" class="tp-text-btn tp-ok">确定</button>',
            '  </div>',
            '  <div class="tp-presets" id="tpPresets"></div>',
            '  <div class="tp-wheels">',
            '    <div class="tp-highlight"></div>',
            '    <div class="tp-col" id="tpHourCol"></div>',
            '    <div class="tp-colon">:</div>',
            '    <div class="tp-col" id="tpMinuteCol"></div>',
            '  </div>',
            '  <button type="button" class="tp-clear" id="tpClear">不设置提醒</button>',
            '</div>',
        ].join('');
        document.body.appendChild(overlay);

        const presets = overlay.querySelector('#tpPresets');
        PRESETS.forEach((time) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'tp-preset';
            btn.dataset.time = time;
            btn.textContent = time;
            presets.appendChild(btn);
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cancel();
        });
        overlay.querySelector('.tp-cancel').addEventListener('click', cancel);
        overlay.querySelector('.tp-ok').addEventListener('click', confirm);
        overlay.querySelector('#tpClear').addEventListener('click', clearTime);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('is-open')) {
                e.preventDefault();
                cancel();
            }
        });
        presets.addEventListener('click', (e) => {
            const btn = e.target.closest('.tp-preset');
            if (!btn) return;
            setWheels(btn.dataset.time);
        });
        return overlay;
    }

    function buildColumn(col, count, unit) {
        col.innerHTML = '';
        const frag = document.createDocumentFragment();
        for (let i = 0; i < PAD; i++) {
            const pad = document.createElement('div');
            pad.className = 'tp-item is-pad';
            pad.textContent = '';
            frag.appendChild(pad);
        }
        for (let i = 0; i < count; i++) {
            const el = document.createElement('div');
            el.className = 'tp-item';
            el.dataset.value = String(i);
            el.innerHTML = `<span>${pad2(i)}</span><span class="tp-unit">${unit}</span>`;
            el.addEventListener('click', () => scrollToIndex(col, i, true));
            frag.appendChild(el);
        }
        for (let i = 0; i < PAD; i++) {
            const pad = document.createElement('div');
            pad.className = 'tp-item is-pad';
            pad.textContent = '';
            frag.appendChild(pad);
        }
        col.appendChild(frag);
        bindColumn(col, count);
    }

    function bindColumn(col, count) {
        if (col.dataset.tpBound) return;
        col.dataset.tpBound = '1';
        const snap = () => {
            const idx = Math.round(col.scrollTop / ITEM_H);
            scrollToIndex(col, Math.min(count - 1, Math.max(0, idx)), true);
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
            el.classList.toggle('is-active', Number(el.dataset.value) === idx);
        });
    }

    function scrollToIndex(col, index, smooth) {
        const top = index * ITEM_H;
        if (Math.abs(col.scrollTop - top) > 1) {
            col.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
        }
        updateActive(col);
    }

    function columnValue(col) {
        const count = col.querySelectorAll('.tp-item[data-value]').length || 1;
        return Math.min(count - 1, Math.max(0, Math.round(col.scrollTop / ITEM_H)));
    }

    function currentValue() {
        const overlay = ensureOverlay();
        const hour = columnValue(overlay.querySelector('#tpHourCol'));
        const minute = columnValue(overlay.querySelector('#tpMinuteCol'));
        return `${pad2(hour)}:${pad2(minute)}`;
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
        scrollToIndex(overlay.querySelector('#tpHourCol'), h, false);
        scrollToIndex(overlay.querySelector('#tpMinuteCol'), m, false);
        syncPresets();
    }

    let resolver = null;
    let hourColReady = false;

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
        if (!hourColReady) {
            buildColumn(overlay.querySelector('#tpHourCol'), 24, '时');
            buildColumn(overlay.querySelector('#tpMinuteCol'), 60, '分');
            hourColReady = true;
        }
        overlay.querySelector('#tpTitle').textContent = options.title || '选择时间';
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
