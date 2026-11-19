(() => {
  const pick = options => {
    const anchor = document.activeElement;
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.className = 'b03-clock';
      const [hour, minute] = (options.value || '09:00').split(':');
      dialog.innerHTML = '<form method="dialog"><div class="b03-clock-head"><span>' + options.title + '</span><button value="cancel" aria-label="关闭">×</button></div><div class="b03-clock-input"><label><input name="hour" type="text" inputmode="numeric" maxlength="2" aria-label="小时" value="' + hour + '"><small>小时</small></label><span>:</span><label><input name="minute" type="text" inputmode="numeric" maxlength="2" aria-label="分钟" value="' + minute + '"><small>分钟</small></label></div><div class="b03-clock-grid" aria-label="选择小时"></div><div class="b03-clock-minutes" aria-label="选择分钟"></div><p role="status"></p><footer><button value="clear">清除时间</button><button value="cancel">取消</button><button value="save">确定</button></footer></form>';
      const form = dialog.querySelector('form');
      const refresh = () => {
        dialog.querySelectorAll('[data-hour]').forEach(b => b.setAttribute('aria-pressed',String(Number(form.elements.hour.value) === Number(b.dataset.hour))));
        dialog.querySelectorAll('[data-minute]').forEach(b => b.setAttribute('aria-pressed',String(Number(form.elements.minute.value) === Number(b.dataset.minute))));
      };
      for (let h=0; h<24; h++) {
        const button = document.createElement('button'); button.type='button';button.dataset.hour=h;button.textContent=String(h).padStart(2,'0');
        button.onclick=()=>{form.elements.hour.value=button.textContent;refresh();};dialog.querySelector('.b03-clock-grid').append(button);
      }
      for (const m of [0,10,15,20,30,40,45,50]) {
        const button=document.createElement('button');button.type='button';button.dataset.minute=m;button.textContent=':'+String(m).padStart(2,'0');
        button.onclick=()=>{form.elements.minute.value=String(m).padStart(2,'0');refresh();};dialog.querySelector('.b03-clock-minutes').append(button);
      }
      form.oninput=refresh;
      form.onsubmit=event=>{
        if(event.submitter?.value!=='save')return;
        const h=form.elements.hour.value,m=form.elements.minute.value;
        if(!/^\d{1,2}$/.test(h)||!/^\d{1,2}$/.test(m)||Number(h)>23||Number(m)>59){event.preventDefault();dialog.querySelector('[role=status]').textContent='小时填0—23，分钟填0—59。';}
      };
      dialog.onclose=()=>{
        const value=dialog.returnValue==='save'?String(Number(form.elements.hour.value)).padStart(2,'0')+':'+String(Number(form.elements.minute.value)).padStart(2,'0'):dialog.returnValue==='clear'?'':null;
        dialog.remove();anchor?.focus();resolve(value);
      };
      document.body.append(dialog);refresh();dialog.showModal();form.elements.hour.focus();form.elements.hour.select();
    });
  };
  const fields = ['deadline_time', 'window_start', 'window_end'];
  const safe = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(value || '') ? value : '';
  function controls(values = {}) {
    const button = key => `<button type="button" data-time="${key}" aria-label="${{deadline_time:'最晚完成时间',window_start:'开始时间',window_end:'结束时间'}[key]}">${safe(values[key]) || '________'}</button>`;
    const conflict = values.window_start && values.window_end && values.window_start >= values.window_end
      ? '结束时间须晚于开始时间，请核对。'
      : values.deadline_time && values.window_start && values.deadline_time <= values.window_start ? '截止早于可开始时间，请核对。' : '';
    return `<div class="b03-time"><span>时间安排 <small>选填</small></span><label>最晚 ${button(fields[0])} 完成</label><label>可在 ${button(fields[1])} 至 ${button(fields[2])} 做</label><button type="button" data-clear-time>清除</button><span role="status">${conflict}</span></div>`;
  }
  function loadText(load) {
    const total=load.known_minutes || 0, available=load.available_minutes, missing=load.unknown_count || 0;
    const over=available != null && total > available;
    return `已选 ${load.selected_count || 0} 项 · 已知预计 ${total} 分钟。` +
      (over ? `超出可用时间 ${total-available} 分钟。可以调整任务，也可保留全部。` : '') +
      (missing ? `${missing} 项缺少当天估时，无法判断完整负荷。` : available == null ? '可用时间未填，无法判断负荷。' : over ? '' : `在可用时间内，剩余 ${available-total} 分钟。`);
  }
  function summary(values) {
    const pieces=[];
    if(safe(values.deadline_time))pieces.push('最晚 '+values.deadline_time+' 完成');
    if(safe(values.window_start)||safe(values.window_end))pieces.push('可执行时段 '+(safe(values.window_start)||'未定')+'—'+(safe(values.window_end)||'未定'));
    return pieces.join(' · ');
  }
  window.ShuranSchedulePlanning = {pick, controls, loadText, fields, summary};
})();
