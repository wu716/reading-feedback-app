/**
 * 3D 滚轮数字选择器（立体感投影）
 */
class WheelPicker {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        if (!this.container) return;

        this.min = options.min ?? 0;
        this.max = options.max ?? 99;
        this.value = Math.min(this.max, Math.max(this.min, options.value ?? this.min));
        this.onChange = options.onChange || (() => {});
        this.itemHeight = options.itemHeight ?? 40;
        this.suffix = options.suffix ?? '';

        this.container.classList.add('wheel-picker');
        this.container.innerHTML = [
            '<div class="wheel-picker-viewport">',
            '  <div class="wheel-picker-highlight"></div>',
            '  <div class="wheel-picker-list"></div>',
            '</div>',
            `<input type="number" class="wheel-picker-input" min="${this.min}" max="${this.max}">`,
        ].join('');

        this.viewport = this.container.querySelector('.wheel-picker-viewport');
        this.list = this.container.querySelector('.wheel-picker-list');
        this.input = this.container.querySelector('.wheel-picker-input');
        this._build();
        this._bind();
        this.setValue(this.value, false);
    }

    _build() {
        const frag = document.createDocumentFragment();
        for (let i = this.min; i <= this.max; i++) {
            const el = document.createElement('div');
            el.className = 'wheel-picker-item';
            el.dataset.value = String(i);
            el.innerHTML = `<span>${i}${this.suffix}</span>`;
            frag.appendChild(el);
        }
        this.list.appendChild(frag);
        this.list.style.paddingTop = `${this.itemHeight * 2}px`;
        this.list.style.paddingBottom = `${this.itemHeight * 2}px`;
    }

    _bind() {
        let startY = 0;
        let startScroll = 0;
        let dragging = false;

        const snap = () => {
            const idx = Math.round(this.list.scrollTop / this.itemHeight);
            const v = Math.min(this.max, Math.max(this.min, this.min + idx));
            this.setValue(v, true);
        };

        this.list.addEventListener('scroll', () => this._update3d(), { passive: true });
        this.list.addEventListener('scrollend', snap);
        this.list.addEventListener('mouseup', snap);
        this.list.addEventListener('touchend', snap);

        this.list.addEventListener('wheel', (e) => {
            e.preventDefault();
            this.list.scrollTop += e.deltaY;
            clearTimeout(this._wheelTimer);
            this._wheelTimer = setTimeout(snap, 120);
        }, { passive: false });

        this.list.addEventListener('mousedown', (e) => {
            dragging = true;
            startY = e.clientY;
            startScroll = this.list.scrollTop;
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            this.list.scrollTop = startScroll - (e.clientY - startY);
            this._update3d();
        });
        window.addEventListener('mouseup', () => { dragging = false; });

        this.list.addEventListener('touchstart', (e) => {
            dragging = true;
            startY = e.touches[0].clientY;
            startScroll = this.list.scrollTop;
        }, { passive: true });
        this.list.addEventListener('touchmove', (e) => {
            if (!dragging) return;
            this.list.scrollTop = startScroll - (e.touches[0].clientY - startY);
            this._update3d();
        }, { passive: true });
        this.list.addEventListener('touchend', () => { dragging = false; });

        this.input.addEventListener('change', () => {
            const v = parseInt(this.input.value, 10);
            if (!Number.isNaN(v)) this.setValue(v, true);
        });

        this.list.querySelectorAll('.wheel-picker-item').forEach((el) => {
            el.addEventListener('click', () => {
                this.setValue(parseInt(el.dataset.value, 10), true);
            });
        });
    }

    _update3d() {
        const center = this.viewport.clientHeight / 2;
        this.list.querySelectorAll('.wheel-picker-item').forEach((el) => {
            const elCenter = el.offsetTop + this.itemHeight / 2 - this.list.scrollTop;
            const dist = (elCenter - center) / this.itemHeight;
            const abs = Math.min(Math.abs(dist), 3);
            const scale = 1 - abs * 0.12;
            const opacity = 1 - abs * 0.35;
            const rotateX = dist * -18;
            el.style.transform = `rotateX(${rotateX}deg) scale(${scale})`;
            el.style.opacity = String(Math.max(0.25, opacity));
        });
    }

    setValue(v, notify = true) {
        this.value = Math.min(this.max, Math.max(this.min, v));
        this.input.value = this.value;
        this.list.scrollTop = (this.value - this.min) * this.itemHeight;
        this._update3d();
        if (notify) this.onChange(this.value);
    }

    getValue() {
        return this.value;
    }
}

window.WheelPicker = WheelPicker;
