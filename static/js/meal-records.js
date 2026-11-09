(() => {
  'use strict';
  const kinds={breakfast:'早饭',lunch:'午饭',dinner:'晚饭',snack:'加餐'};
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const uid=()=>globalThis.crypto?.randomUUID?.()||'meal_'+Date.now().toString(36)+Math.random().toString(36).slice(2);
  const root=()=>document.getElementById('ltMeals');
  const photoCache=new Map();
  let photoToken=localStorage.getItem('authToken');
  let getDay,touch,renderExpenses,status;
  function photoHTML(ids,kind,id){return `<div class="lt-meal-photos">${(ids||[]).map(photo=>`<figure><img data-photo-preview="${photo}" alt="${kind==='meal'?'饮食':'零食消费'}照片" width="76" height="76"><button type="button" data-remove-photo="${kind}:${esc(id)}:${photo}">移除</button></figure>`).join('')}</div>`;}
  async function hydrate(container){
    if(!container)return;
    if(photoToken!==localStorage.getItem('authToken')){for(const url of photoCache.values())URL.revokeObjectURL(url);photoCache.clear();photoToken=localStorage.getItem('authToken');}
    for(const img of container.querySelectorAll('[data-photo-preview]')){
      const id=Number(img.dataset.photoPreview);
      if(photoCache.has(id)){img.src=photoCache.get(id);continue;}
      try{const response=await fetch(`/api/long-term/details/photos/${id}`,{headers:{Authorization:'Bearer '+localStorage.getItem('authToken')}});
        if(!response.ok)throw Error('图片读取失败');const blob=await response.blob(),url=URL.createObjectURL(blob);photoCache.set(id,url);if(img.isConnected)img.src=url;
      }catch{if(img.isConnected)img.alt='图片暂不可用';}
    }
  }
  function expensePhotosHTML(expense){if(expense.category!=='snacks'&&!(expense.photo_ids||[]).length)return '';
    return `<div class="lt-expense-photos"><label class="lt-meal-upload">＋ 从相册选择图片<input type="file" accept="image/*" multiple data-photo-upload="expense:${esc(expense.id)}"></label><span class="lt-note">${(expense.photo_ids||[]).length} 张</span>${photoHTML(expense.photo_ids,'expense',expense.id)}</div>`;
  }
  function render(day){const target=root();if(!target||!day)return;day.meals||=[];
    target.querySelector('[data-meal-list]').innerHTML=day.meals.map((meal,i)=>`<article class="lt-meal-entry" data-meal="${esc(meal.id)}"><div class="lt-meal-head"><strong>${kinds[meal.type]||'饮食记录'} ${i+1}</strong><button type="button" data-remove-meal="${esc(meal.id)}">移除</button></div><div class="lt-meal-grid"><label>餐次<select data-meal-id="${esc(meal.id)}" data-meal-field="type">${Object.entries(kinds).map(([key,name])=>`<option value="${key}" ${meal.type===key?'selected':''}>${name}</option>`).join('')}</select></label><label>关联当天消费（选填）<select data-meal-id="${esc(meal.id)}" data-meal-field="expense_id"><option value="">不关联</option>${day.expenses.map(e=>`<option value="${esc(e.id)}" ${meal.expense_id===e.id?'selected':''}>${esc(e.category==='snacks'?'零食':e.category==='food'?'餐饮':e.category)} · ¥${(Number(e.amount_cents||0)/100).toFixed(2)}</option>`).join('')}</select></label></div><label>吃了什么（选填）<textarea data-meal-id="${esc(meal.id)}" data-meal-field="text" rows="2" maxlength="2000">${esc(meal.text)}</textarea></label><div class="lt-meal-photo-row"><label class="lt-meal-upload">＋ 从相册选择图片<input type="file" accept="image/*" multiple data-photo-upload="meal:${esc(meal.id)}"></label><span class="lt-note">${(meal.photo_ids||[]).length} 张</span></div>${photoHTML(meal.photo_ids,'meal',meal.id)}</article>`).join('')||'<p class="lt-note">还没有饮食记录；未记录不表示没有吃。</p>';
    hydrate(target);
  }
  function find(kind,id){const day=getDay();return kind==='meal'?day?.meals?.find(m=>m.id===id):day?.expenses?.find(e=>e.id===id);}
  async function upload(input){const [kind,id]=input.dataset.photoUpload.split(':'),record=find(kind,id),day=getDay();if(!record||!day)return;
    const files=[...input.files];if(!files.length)return;status(`正在上传 ${files.length} 张图片…`);
    let added=0;for(const file of files){try{const body=new FormData();body.append('file',file);const query=new URLSearchParams({day:day.date,owner_kind:kind,owner_id:id});const response=await fetch('/api/long-term/details/photos?'+query,{method:'POST',headers:{Authorization:'Bearer '+localStorage.getItem('authToken')},body});const data=await response.json();if(!response.ok)throw Error(data.detail||'图片上传失败');if(getDay()!==day){status('日期已切换；刚上传的照片未关联，请回原日期重新选择。');break;}record.photo_ids||=[];record.photo_ids.push(data.id);photoCache.set(data.id,URL.createObjectURL(file));added++;touch();}catch(error){status(error.message||'图片上传失败');break;}}
    if(added)status(`已上传 ${added} 张图片，请保存这一天的记录。`);
    if(kind==='meal')render(day);else renderExpenses();
  }
  function init(dependencies){({getDay,touch,renderExpenses,status}=dependencies);
    root()?.addEventListener('click',event=>{const button=event.target.closest('button');if(!button||!getDay())return;
      if(button.dataset.addMeal!==undefined){getDay().meals||=[];getDay().meals.push({id:uid(),type:'breakfast',text:'',expense_id:null,photo_ids:[]});touch();render(getDay());root().querySelector('.lt-meal-entry:last-of-type textarea')?.focus();}
      if(button.dataset.removeMeal){getDay().meals=getDay().meals.filter(m=>m.id!==button.dataset.removeMeal);touch();render(getDay());}
      if(button.dataset.removePhoto)removePhoto(button.dataset.removePhoto);
    });
    root()?.addEventListener('input',event=>{const field=event.target.dataset.mealField,id=event.target.dataset.mealId;if(!field||!id)return;const meal=find('meal',id);if(!meal)return;meal[field]=field==='expense_id'?event.target.value||null:event.target.value;touch();});
    root()?.addEventListener('change',event=>{if(event.target.dataset.photoUpload)upload(event.target);});
    document.getElementById('ltExpenseList')?.addEventListener('change',event=>{if(event.target.dataset.photoUpload)upload(event.target);});
    document.getElementById('ltExpenseList')?.addEventListener('click',event=>{const button=event.target.closest('[data-remove-photo]');if(button)removePhoto(button.dataset.removePhoto);});
  }
  function removePhoto(value){const [kind,id,photo]=value.split(':'),record=find(kind,id);if(!record)return;record.photo_ids=(record.photo_ids||[]).filter(item=>item!==Number(photo));touch();if(kind==='meal')render(getDay());else renderExpenses();}
  function renderReport(report,container){const meals=report.meals||[];const counts=report.meal_counts||{};
    const section=document.createElement('section');section.className='lt-report-section';section.innerHTML=`<h2>饮食回看</h2><p class="lt-note">按实际食用日期与餐次记录；未记录不表示没吃，饮食记录不重复统计消费金额。</p><div class="lt-meal-report-counts">${Object.entries(kinds).map(([key,name])=>`<span>${name} · ${counts[key]||0} 条</span>`).join('')}</div>${meals.map(meal=>`<p><button type="button" class="lt-text-button" data-day="${esc(meal.date)}">${esc(meal.date)}</button> · ${kinds[meal.type]||'饮食'}：${esc(meal.text||'图片记录')} · ${(meal.photo_ids||[]).length} 张图片</p>`).join('')||'<p class="lt-note">本周期尚无饮食记录。</p>'}`;
    container.append(section);
  }
  window.ShuranMeals={init,render,hydrate,expensePhotosHTML,renderReport};
})();
