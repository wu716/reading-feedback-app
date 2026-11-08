const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_PACKAGE||'playwright');
let browser;
(async()=>{
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],writes=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>localStorage.setItem('authToken','synthetic-only'));
  const script=fs.readFileSync(path.resolve(__dirname,'../static/js/core-review.js'),'utf8');
  const html=`<!doctype html><html><body><section id="daily-feedback" class="active"><section id="dailyCoreReview" hidden><div id="dailyCoreReviewItems"></div></section><section id="dailyExecutionFeedback"><div id="dailyExecutionFeedbackItems"></div></section></section><script>${script}</script></body></html>`;
  await page.route('http://shuran.test/**',route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
    if(url.pathname==='/api/schedule')return route.fulfill({contentType:'application/json',body:JSON.stringify({tasks:[{id:1,text:'今天必须完成',core_selected:true,core_review_completed:null,core_review_reason:null,children:[]},{id:2,text:'想做',core_selected:false,children:[]}]})});
    if(url.pathname==='/api/schedule/tasks/1'){writes.push(req.postDataJSON());return route.fulfill({contentType:'application/json',body:'{}'});}
    throw new Error('Unexpected '+url.pathname);
  });
  await page.goto('http://shuran.test/',{waitUntil:'domcontentloaded'});
  await page.evaluate(()=>window.ShuranCoreReview.load('2026-11-08'));
  await page.locator('[data-core-review="1"]').waitFor();
  assert.equal(await page.locator('[data-core-review]').count(),1);
  assert.equal(await page.locator('[name=completed]').inputValue(),'');
  await page.locator('[name=completed]').selectOption('no');
  await page.locator('[name=reason]').fill('外部确认尚未收到');
  await page.locator('[data-save-core]').click();
  assert.deepEqual(writes.at(-1),{core_review_completed:false,core_review_reason:'外部确认尚未收到'});
  assert((await page.locator('#dailyExecutionFeedbackItems a').first().getAttribute('href')).includes('day=2026-11-08'));
  assert.deepEqual(errors,[]);
  console.log('PASS core selection review, optional reason and original day link');
  await browser.close();
})().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});
