/* Single dates and local date-times, using the paper/slate planning calendar. */
(() => {
  'use strict';
  const selector = 'input[data-paper-date], body[data-paper-dates] input[type="date"], body[data-paper-dates] input[type="datetime-local"]';
  const fields = new WeakMap();
  const valueProperty = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  const pad = n => String(n).padStart(2, '0');
  const dayString = d => `${String(d.getUTCFullYear()).padStart(4, '0')}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const parseDay = value => { const d = new Date(0); const [y,m,day] = value.split('-').map(Number); d.setUTCFullYear(y,m-1,day); d.setUTCHours(12,0,0,0); return d; };
  const shiftDay = (value, amount) => { const d = parseDay(value); d.setUTCDate(d.getUTCDate()+amount); return dayString(d); };
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`; };
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v5M16 3v5M4 11h16M8 15h2M14 15h2"/></svg>';
  let dialog, active = null, month, selected, focused;

  function caption(input) {
    return input.getAttribute('aria-label') || input.labels?.[0]?.textContent.trim().replace(/\s+/g,' ') || '选择日期';
  }
  function sync(input) {
    const button = fields.get(input);
    if (!button) return;
    button.querySelector('span').textContent = input.value ? input.value.replaceAll('-', ' / ').replace('T', '　') : (input.type === 'datetime-local' ? '选择日期与时间' : '选择日期');
    button.classList.toggle('is-empty', !input.value);
    button.disabled = input.disabled || input.readOnly;
    button.setAttribute('aria-label', `${caption(input)}${input.value ? '：'+input.value.replace('T',' ') : ''}`);
    button.setAttribute('aria-required', String(input.required));
  }
  function finish() {
    const previous = active;
    active = null;
    if (dialog?.open) dialog.close();
    if (previous) {
      previous.button.setAttribute('aria-expanded','false');
      if (previous.button.isConnected) previous.button.focus({preventScroll:true});
    }
  }
  function inBounds(value) {
    if (!active || value.length !== 10 || value < '0001-01-01' || value > '9999-12-31') return false;
    const {input} = active;
    return (!input.min || value >= input.min.slice(0,10)) && (!input.max || value <= input.max.slice(0,10));
  }
  function moveMonth(amount) {
    const d = parseDay(month);
    d.setUTCMonth(d.getUTCMonth()+amount);
    const next = dayString(d);
    if (next >= '0001-01-01' && next <= '9999-12-31') {
      month = next; focused = next; render(true);
    }
  }
  function render(restoreFocus = false) {
    const first = parseDay(month), offset = (first.getUTCDay()+6)%7;
    dialog.querySelector('[data-month-label]').textContent = `${first.getUTCFullYear()} 年 ${first.getUTCMonth()+1} 月`;
    const grid = dialog.querySelector('[data-calendar]');
    grid.replaceChildren(...Array.from({length:42}, (_,i) => {
      const value = shiftDay(month,i-offset), day = parseDay(value), button = document.createElement('button');
      button.type = 'button'; button.dataset.date = value; button.textContent = day.getUTCDate();
      button.className = `${value.slice(0,7) === month.slice(0,7) ? '' : 'other-month '}${value === selected ? 'is-selected ' : ''}${value === today() ? 'is-today' : ''}`;
      button.setAttribute('aria-label',value); button.setAttribute('aria-pressed',String(value === selected));
      if (value === today()) button.setAttribute('aria-current','date');
      button.disabled = !inBounds(value); button.tabIndex = value === focused ? 0 : -1;
      return button;
    }));
    if (!grid.querySelector('button[tabindex="0"]:not(:disabled)')) {
      const fallback = grid.querySelector('button:not(:disabled)');
      if (fallback) { fallback.tabIndex = 0; focused = fallback.dataset.date; }
    }
    dialog.querySelector('[data-today]').disabled = !inBounds(today());
    dialog.querySelector('[data-selected]').textContent = `已选：${selected.replaceAll('-',' / ')}`;
    dialog.querySelector('[data-error]').textContent = '';
    if (restoreFocus) grid.querySelector('button[tabindex="0"]')?.focus({preventScroll:true});
  }
  function position() {
    if (!active || !dialog.open) return;
    const anchor = active.button.getBoundingClientRect(), box = dialog.getBoundingClientRect();
    const viewport = window.visualViewport, width = viewport?.width || innerWidth, height = viewport?.height || innerHeight;
    const x = viewport?.offsetLeft || 0, y = viewport?.offsetTop || 0;
    let top = anchor.bottom+8;
    if (top+box.height > y+height-12) top = anchor.top-box.height-8;
    top = Math.max(y+12,Math.min(top,y+height-box.height-12));
    dialog.style.left = `${Math.max(x+12,Math.min(anchor.left,x+width-box.width-12))}px`;
    dialog.style.top = `${top}px`;
  }
  function commit(clear = false) {
    if (!active) return;
    const {input} = active;
    let value = clear ? '' : selected;
    if (!clear && input.type === 'datetime-local') {
      const hour = dialog.querySelector('[data-hour]'), minute = dialog.querySelector('[data-minute]');
      if (!hour.reportValidity() || !minute.reportValidity()) return;
      value += `T${pad(Number(hour.value))}:${pad(Number(minute.value))}`;
      const local = new Date(value);
      if (local.getHours() !== Number(hour.value) || local.getMinutes() !== Number(minute.value)) {
        dialog.querySelector('[data-error]').textContent = '此时间在本机时区不存在，请重新选择。'; return;
      }
    }
    // Validate a detached native field; failed choices must leave the saved value untouched.
    const check = input.cloneNode(false); check.value = value;
    if (!check.validity.valid) {
      dialog.querySelector('[data-error]').textContent = check.validationMessage || '请选择允许范围内的日期与时间。'; return;
    }
    input.value = value;
    finish();
    input.dispatchEvent(new Event('input',{bubbles:true}));
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement('dialog');
    dialog.className = 'sdp-dialog'; dialog.id = 'paperDateDialog'; dialog.setAttribute('aria-labelledby','paperDateTitle');
    dialog.innerHTML = `<div class="sdp-title" id="paperDateTitle"></div><div class="fb-calendar sdp-calendar"><div class="fb-calendar-head"><button type="button" data-month="-1" aria-label="上个月">‹</button><strong data-month-label aria-live="polite"></strong><button type="button" data-month="1" aria-label="下个月">›</button></div><div class="fb-week-head" aria-hidden="true">${['一','二','三','四','五','六','日'].map(day=>`<span>${day}</span>`).join('')}</div><div class="fb-calendar-grid" data-calendar aria-label="选择日期"></div></div><div class="sdp-selected" data-selected aria-live="polite"></div><div class="sdp-time" data-time><span>时间</span><label>小时<input type="number" min="0" max="23" step="1" inputmode="numeric" data-hour required></label><span aria-hidden="true">:</span><label>分钟<input type="number" min="0" max="59" step="1" inputmode="numeric" data-minute required></label></div><p class="sdp-error" data-error role="alert"></p><div class="sdp-footer"><div><button type="button" data-today>今天</button><button type="button" data-clear>清空</button></div><div><button type="button" data-cancel>取消</button><button type="button" data-confirm>确定</button></div></div>`;
    document.body.append(dialog);
    dialog.addEventListener('cancel',event=>{event.preventDefault();finish();});
    dialog.addEventListener('click',event=>{
      if (event.target === dialog) {
        const r = dialog.getBoundingClientRect();
        if (event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) finish();
        return;
      }
      const button = event.target.closest('button');
      if (!button || !active) return;
      if (button.dataset.month) moveMonth(Number(button.dataset.month));
      else if (button.dataset.date) { selected = focused = button.dataset.date; month = selected.slice(0,7)+'-01'; render(true); }
      else if (button.hasAttribute('data-today')) { selected = focused = today(); month = selected.slice(0,7)+'-01'; render(true); }
      else if (button.hasAttribute('data-clear')) commit(true);
      else if (button.hasAttribute('data-cancel')) finish();
      else if (button.hasAttribute('data-confirm')) commit();
    });
    dialog.addEventListener('keydown',event=>{
      if (!event.target.matches('[data-date]')) return;
      const shifts = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};
      let next;
      if (event.key in shifts) next = shiftDay(focused,shifts[event.key]);
      if (event.key === 'Home') next = shiftDay(focused,-((parseDay(focused).getUTCDay()+6)%7));
      if (event.key === 'End') next = shiftDay(focused,6-((parseDay(focused).getUTCDay()+6)%7));
      if (event.key === 'PageUp' || event.key === 'PageDown') {event.preventDefault(); moveMonth(event.key === 'PageUp' ? -1 : 1);return;}
      if (next) {event.preventDefault();if(inBounds(next)){focused=next;month=next.slice(0,7)+'-01';render(true);}}
    });
    window.addEventListener('resize',position);
    window.visualViewport?.addEventListener('resize',position);
    window.visualViewport?.addEventListener('scroll',position);
  }
  function open(input, button) {
    if (input.disabled || input.readOnly) return;
    ensureDialog();
    if (active) finish();
    active = {input,button};
    selected = input.value.slice(0,10) || today();
    if (input.min && selected<input.min.slice(0,10)) selected=input.min.slice(0,10);
    if (input.max && selected>input.max.slice(0,10)) selected=input.max.slice(0,10);
    focused=selected;month=selected.slice(0,7)+'-01';
    dialog.querySelector('#paperDateTitle').textContent = input.type === 'datetime-local' ? '选择日期与时间' : '选择日期';
    dialog.querySelector('[data-time]').hidden = input.type !== 'datetime-local';
    dialog.querySelector('[data-clear]').hidden = input.required;
    const time = input.value.split('T')[1] || `${pad(new Date().getHours())}:${pad(new Date().getMinutes())}`;
    dialog.querySelector('[data-hour]').value = Number(time.slice(0,2));
    dialog.querySelector('[data-minute]').value = Number(time.slice(3,5));
    render();button.setAttribute('aria-expanded','true');
    dialog.showModal();position();
    dialog.querySelector('[data-calendar] button[tabindex="0"]')?.focus({preventScroll:true});
  }
  function enhance(input) {
    if (fields.has(input) || !['date','datetime-local'].includes(input.type)) return;
    const wrapper = document.createElement('span'), button = document.createElement('button');
    wrapper.className = 'sdp-field';button.type = 'button';button.className = 'sdp-trigger';
    // Read the label before adding the trigger text to it.
    if (!input.hasAttribute('aria-label')) input.setAttribute('aria-label',caption(input));
    button.innerHTML = `<span></span>${icon}`;
    button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','paperDateDialog');
    input.before(wrapper);wrapper.append(input,button);input.classList.add('sdp-native');input.tabIndex=-1;input.setAttribute('aria-hidden','true');
    input.dataset.sdpBound='true';fields.set(input,button);
    Object.defineProperty(input,'value',{configurable:true,get(){return valueProperty.get.call(this);},set(value){valueProperty.set.call(this,value);sync(this);}});
    button.addEventListener('click',()=>open(input,button));
    input.addEventListener('click',event=>{event.preventDefault();if(!active)open(input,button);});
    input.addEventListener('focus',()=>button.focus({preventScroll:true}));
    input.addEventListener('input',()=>sync(input));input.addEventListener('change',()=>sync(input));
    input.addEventListener('invalid',event=>{event.preventDefault();if(!active)open(input,button);});
    sync(input);
  }
  function bindAll(root = document) {
    if (root.matches?.(selector)) enhance(root);
    root.querySelectorAll?.(selector).forEach(enhance);
  }
  function init() {
    bindAll();
    document.addEventListener('reset',event=>queueMicrotask(()=>event.target.querySelectorAll('input[data-sdp-bound]').forEach(sync)));
    new MutationObserver(records=>{
      if (active && (!active.input.isConnected || active.input.disabled || active.input.readOnly)) finish();
      for (const record of records) {
        if (record.type === 'attributes') sync(record.target);
        else record.addedNodes.forEach(node=>{if(node.nodeType===1)bindAll(node);});
      }
    }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','readonly','required','value','min','max']});
  }
  globalThis.ShuranDatePicker = {bindAll,enhance};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
