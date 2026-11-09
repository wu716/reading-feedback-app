// PLAYWRIGHT_PACKAGE=<package path> node tests/test_schedule_inline_ui.js
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');

(async () => {
  const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<div id="new-panel"></div><div style="height:1200px">Earlier tasks</div><article data-task-id="9"><button data-act="expectation">预期结果</button><button data-act="feedback">实际结果</button><div data-inline-panel></div></article><div style="height:900px"></div>');
    await page.evaluate(() => {
      window.saved = new Map(); window.posts = [];
      window.apiRequest = async (url, options={}) => {
        const method = options.method || 'GET';
        window.posts.push({url,method,body:options.body && JSON.parse(options.body)});
        if (url.startsWith('/api/editor-drafts/')) {
          if (method === 'GET') return {content:window.saved.get(url) || {}};
          if (method === 'PUT') {window.saved.set(url,JSON.parse(options.body).content); return {saved:true};}
          if (method === 'DELETE') {window.saved.delete(url); return {deleted:true};}
        }
        if (url === '/api/projects/practice/tasks/daily/9') return {title:'靠后的任务',original_estimate:30,recorded_minutes:12,feedback:{actual_minutes:20,result:'partial',basis:'self_report',outcome:'旧结果'},history:[]};
        return {};
      };
    });
    await page.addScriptTag({path:path.resolve(__dirname,'../static/js/schedule-inline-editor.js')});
    await page.locator('[data-task-id="9"]').scrollIntoViewIfNeeded();
    await page.evaluate(() => ShuranScheduleInline.open({kind:'expectation',id:9,day:'2026-11-09',root:document.querySelector('[data-inline-panel]'),task:{expected_result:'旧预期',completion_basis:''},onSaved:async()=>{document.querySelector('[data-inline-panel]').innerHTML='';scrollTo(0,0)}}));
    assert.equal(await page.locator('[name="expected_result"]').inputValue(),'旧预期');
    await page.locator('[name="expected_result"]').fill('新预期');
    await page.locator('[data-inline-close]').click();
    assert.equal(await page.locator('[data-inline-kind="expectation"]').count(),0);
    await page.evaluate(() => ShuranScheduleInline.open({kind:'expectation',id:9,day:'2026-11-09',root:document.querySelector('[data-inline-panel]'),task:{expected_result:'旧预期'},onSaved:async()=>{document.querySelector('[data-inline-panel]').innerHTML='';scrollTo(0,0)}}));
    assert.equal(await page.locator('[name="expected_result"]').inputValue(),'新预期');
    const before = await page.evaluate(() => scrollY);
    await page.locator('[data-inline-kind="expectation"] [type="submit"]').click();
    assert(Math.abs((await page.evaluate(() => scrollY))-before)<3,'saving must retain the viewed task position');
    assert((await page.evaluate(() => posts)).some(p=>p.url==='/api/schedule/tasks/9' && p.body.expected_result==='新预期'));
    await page.evaluate(() => ShuranScheduleInline.open({kind:'feedback',id:9,day:'2026-11-09',root:document.querySelector('[data-inline-panel]'),onSaved:async()=>{document.querySelector('[data-inline-panel]').innerHTML=''}}));
    assert.equal(await page.locator('[name="outcome"]').inputValue(),'旧结果');
    await page.locator('[name="outcome"]').fill('完成整理');
    await page.locator('[data-inline-kind="feedback"] [type="submit"]').click();
    assert((await page.evaluate(() => posts)).some(p=>p.url==='/api/projects/practice/tasks/daily/9/feedback' && p.body.outcome==='完成整理' && p.body.actual_minutes===20));
    await page.evaluate(() => saved.set('/api/editor-drafts/task-new%3A2026-11-09',{text:'尚未添加的任务',hours:'1',expected_result:''}));
    await page.evaluate(() => ShuranScheduleInline.open({kind:'expectation',id:null,day:'2026-11-09',root:document.querySelector('#new-panel'),task:{},newTask:()=>{}}));
    await page.locator('#new-panel [name="expected_result"]').fill('得到一份提纲');
    await page.locator('#new-panel [type="submit"]').click();
    assert.deepEqual(await page.evaluate(() => saved.get('/api/editor-drafts/task-new%3A2026-11-09')),{text:'尚未添加的任务',hours:'1',expected_result:'得到一份提纲',completion_basis:''});
    assert.deepEqual(errors,[]);
    console.log('PASS inline expectation draft, retained scroll, project feedback fields');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
