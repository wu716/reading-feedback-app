const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright');
const script=fs.readFileSync(path.resolve(__dirname,'../static/js/meal-records.js'),'utf8');
let browser;
(async()=>{
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],uploads=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('authToken','synthetic-only'));
  await page.route('http://shuran.test/**',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.pathname==='/'){return route.fulfill({contentType:'text/html',body:'<div id="ltMeals"><div data-meal-list></div><button data-add-meal>＋ 添加饮食</button></div><div id="ltExpenseList"></div><div id="ltReport"></div>'});}
    if(url.pathname==='/api/long-term/details/photos'&&request.method()==='POST'){
      uploads.push({kind:url.searchParams.get('owner_kind'),owner:url.searchParams.get('owner_id')});
      return route.fulfill({contentType:'application/json',body:JSON.stringify({id:uploads.length,url:`/api/long-term/details/photos/${uploads.length}`})});
    }
    throw Error('Unexpected '+request.method()+' '+url.pathname);
  });
  await page.goto('http://shuran.test/');
  await page.addScriptTag({content:script});
  if(errors.length)throw Error(errors.join('; '));
  await page.evaluate(()=>{window.demo={date:'2026-11-09',meals:[{id:'m1',type:'snack',text:'饼干',expense_id:'e1',photo_ids:[]}],expenses:[{id:'e1',category:'snacks',amount_cents:1200,photo_ids:[]}]};window.changed=0;ShuranMeals.init({getDay:()=>demo,touch:()=>changed++,status:()=>{},renderExpenses:()=>{document.querySelector('#ltExpenseList').innerHTML=ShuranMeals.expensePhotosHTML(demo.expenses[0]);ShuranMeals.hydrate(document.querySelector('#ltExpenseList'));}});ShuranMeals.render(demo);document.querySelector('#ltExpenseList').innerHTML=ShuranMeals.expensePhotosHTML(demo.expenses[0]);});
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lE8AAAAASUVORK5CYII=','base64');
  const files=[{name:'一.png',mimeType:'image/png',buffer:png},{name:'二.png',mimeType:'image/png',buffer:png}];
  await page.locator('[data-photo-upload="meal:m1"]').setInputFiles(files);
  await page.locator('#ltMeals [data-photo-preview]').first().waitFor();
  await page.locator('[data-photo-upload="expense:e1"]').setInputFiles(files);
  await page.locator('#ltExpenseList [data-photo-preview]').first().waitFor();
  assert.equal(await page.locator('#ltMeals [data-photo-preview]').count(),2);
  assert.equal(await page.locator('#ltExpenseList [data-photo-preview]').count(),2);
  assert.deepEqual(uploads.map(x=>x.kind),['meal','meal','expense','expense']);
  await page.locator('#ltMeals [data-remove-photo]').first().click();
  assert.equal(await page.evaluate(()=>demo.meals[0].photo_ids.length),1);
  await page.evaluate(()=>ShuranMeals.renderReport({meals:[{date:'2026-11-09',type:'snack',text:'饼干',photo_ids:[2]}],meal_counts:{snack:1}},document.querySelector('#ltReport')));
  assert.match(await page.locator('#ltReport').textContent(),/加餐 · 1 条/);
  assert.deepEqual(errors,[]);
  console.log('PASS meal and snack multi-image controls on mobile viewport');
  await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});
