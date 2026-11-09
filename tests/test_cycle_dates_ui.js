const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright');
const root=path.resolve(__dirname,'..');
let browser;
(async()=>{
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('authToken','synthetic-only'));
  await page.route('http://shuran.test/**',route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.pathname.startsWith('/static/')){const file=path.join(root,url.pathname.slice(1));return route.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file)});}
    if(url.pathname==='/api/projects/practice/projects/1/cycles')return route.fulfill({contentType:'application/json',body:JSON.stringify({items:[{id:5,expected_result:'整理访谈',start_date:'2026-11-08',end_date:'2026-11-14',plan:{feedback:{deliverable:'访谈提纲',deadline:'21:00',reminders:true}},feedback_nodes:[{id:10,date:'2026-11-09',submitted:true},{id:11,date:'2026-11-11',submitted:false},{id:12,date:'2026-11-14',submitted:false}]}]})});
    if(url.pathname==='/api/projects/practice/cycles/5/dates'&&request.method()==='PUT'){writes.push(request.postDataJSON());return route.fulfill({contentType:'application/json',body:'{}'});}
    if(url.pathname==='/return')return route.fulfill({contentType:'text/html',body:'返回项目'});
    throw Error('Unexpected '+request.method()+' '+url.pathname);
  });
  await page.goto('http://shuran.test/static/cycle-dates.html?project=1&cycle=5&return=http%3A%2F%2Fshuran.test%2Freturn');
  assert.equal(await page.locator('[data-node]').count(),2);
  assert.match(await page.locator('#fixed').textContent(),/已提交/);
  await page.locator('[name=start_date]').fill('2026-11-10');
  await page.locator('[data-node="12"] [value=move]').check();
  await page.locator('[data-node="12"] [type=date]').fill('2026-11-18');
  assert.match(await page.locator('#summary').textContent(),/2026-11-14 → 2026-11-18/);
  await page.getByRole('button',{name:'确认周期及节点日期'}).click();
  await page.waitForURL('**/return');
  assert.deepEqual(writes[0].nodes,[{id:11,original_date:'2026-11-11',date:'2026-11-11'},{id:12,original_date:'2026-11-14',date:'2026-11-18'}]);
  assert.deepEqual(errors,[]);
  console.log('PASS cycle date editor on mobile viewport');
  await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});
