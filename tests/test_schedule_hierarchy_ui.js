// PLAYWRIGHT_PACKAGE=<package path> node tests/test_schedule_hierarchy_ui.js
// Exercises the real schedule markup, CSS, translations and event handlers with synthetic API responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const root = path.resolve(__dirname, '..');
const read = name => process.env.SHURAN_TEST_GIT_INDEX
  ? execFileSync('git', ['show', ':' + name], {cwd:root, encoding:'utf8', env:{...process.env, GIT_INDEX_FILE:process.env.SHURAN_TEST_GIT_INDEX}})
  : fs.readFileSync(path.join(root, name), 'utf8');
const index = read('static/index.html');
const schedule = index.slice(index.indexOf('<section id="schedule"'), index.indexOf('<!-- 个人中心区 -->'));
assert(schedule.includes('id="scheduleList"'), 'Real schedule section must be present');
const styles = [...index.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n')
  + ['app-tabbar.css','schedule-log.css','desktop-split.css','paper-shell.css','workspace.css'].map(n => read('static/css/' + n)).join('\n');
const fixture = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${styles}</style></head><body class="workspace-layout"><main class="app-main">${schedule}</main><script>window.apiRequest=async(url,options)=>{const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw new Error(data.detail);return data;};window.showMessage=text=>{window.lastMessage=text;};</script><script>${read('static/js/i18n.js')}</script><script>${read('static/js/daily-schedule.js')}</script></body></html>`;
const task = (id, text, parent_id = null) => ({id,text,parent_id,completed:false,children:[],sort_order:id,flow_order:id,practice:{},color:null,note:''});
const initialTitle = '国家助学金申请，12:00截止';
let browser;
const checks = [], layouts = [];
const check = (name, value) => {assert(value, name);checks.push(name);};
const artifacts = process.env.SCHEDULE_HIERARCHY_ARTIFACTS;
if (artifacts) fs.mkdirSync(artifacts, {recursive:true});
(async () => {
  browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  page.setDefaultTimeout(10000);
  const errors = [], writes = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {localStorage.setItem('authToken','synthetic-only');localStorage.setItem('shuran.language','zh-CN');});
  let state, nextId;
  const reset = () => {state={date:null,designed_at:null,tasks:[{...task(1,initialTitle),familiarity:'familiar',children:[task(2,'图书馆一楼打印申请表',1)]},task(3,'取快递')]};nextId=10;};
  const all = (tasks=state.tasks) => tasks.flatMap(t => [t,...all(t.children)]);
  const refreshCompletion = (tasks=state.tasks) => tasks.forEach(t => {refreshCompletion(t.children);if(t.children.length)t.completed=t.children.every(c=>c.completed);});
  reset();
  await page.route('http://shuran.test/**', async route => {
    const req=route.request(), url=new URL(req.url()), method=req.method();
    const reply = data => route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fixture});
    const body=req.postDataJSON();
    if(method!=='GET')writes.push({path:url.pathname,method,body});
    if(url.pathname==='/api/schedule' && method==='GET'){state.date=url.searchParams.get('task_date');return reply(state);}
    if(url.pathname==='/api/schedule/tasks' && method==='POST'){
      const added={...task(nextId++,body.text,body.parent_id),...body};
      if(body.parent_id)all().find(t=>t.id===body.parent_id).children.push(added);else state.tasks.push(added);
      return reply(state);
    }
    if(url.pathname==='/api/schedule/reorder'){
      for(const item of body.items)Object.assign(all().find(t=>t.id===item.id),item);
      return reply(state);
    }
    const match=url.pathname.match(/^\/api\/schedule\/tasks\/(\d+)$/);
    if(match){
      const id=Number(match[1]), selected=all().find(t=>t.id===id);
      assert(selected,'Known synthetic task');
      if(method==='PATCH'){
        Object.assign(selected,body);
        if(body.clear_familiarity)selected.familiarity=null;
        if(body.clear_note)selected.note='';
        if('completed' in body)refreshCompletion();
      }else if(method==='DELETE'){
        const remove=tasks=>tasks.filter(t=>t.id!==id).map(t=>({...t,children:remove(t.children)}));state.tasks=remove(state.tasks);
      }else assert.fail('Unexpected task request '+method);
      return reply(state);
    }
    const practice=url.pathname.match(/^\/api\/projects\/practice\/tasks\/daily\/(\d+)(\/attributes)?$/);
    if(practice){const selected=all().find(t=>t.id===Number(practice[1]));if(practice[2])Object.assign(selected.practice,body);return reply({...selected.practice,completed:selected.completed});}
    assert.fail('Unexpected request '+method+' '+url.pathname);
  });
  await page.goto('http://shuran.test/');
  await page.evaluate(()=>window.loadDailySchedule());
  const row=id=>page.locator(`[data-task-id="${id}"]`);
  const group=id=>row(id).locator('..').locator(':scope > .flow-task-children');
  await row(2).waitFor();
  check('拆出的任务处于父任务的步骤区内',await group(1).locator('[data-task-id="2"]').count()===1);
  check('步骤区明确显示数量和所属原任务',(await group(1).locator(':scope > .flow-children-heading').innerText()).includes('拆分步骤 · 1 项\n属于「'+initialTitle+'」'));
  check('独立任务不归到上一个任务下面',await row(3).evaluate(el=>!el.closest('.flow-task-children')));
  const inset=await page.evaluate(()=>document.querySelector('[data-task-id="2"]').getBoundingClientRect().left-document.querySelector('[data-task-id="1"]').getBoundingClientRect().left);
  check('步骤具有可见缩进',inset>=20);
  // Empty attribute fields and expandable forms must not alter the relationship or draft.
  await page.locator('#scheduleAddInput').fill('保留顶层输入草稿');
  for(const [width,zoom] of [[1440,1],[775,1],[390,1],[320,1],[960,1.5]]){
    await page.setViewportSize({width,height:1100});
    await page.evaluate(scale=>document.documentElement.style.zoom=String(scale),zoom);
    const parent=row(1);
    for(const mode of ['normal','more','split','both']){
      if(mode==='more')await parent.locator('[data-act="expand"]').click();
      if(mode==='split'){await parent.locator('[data-act="expand"]').click();await parent.locator('[data-act="split"]').click();await parent.locator('[data-split-input]').fill('保留拆分草稿');}
      if(mode==='both')await parent.locator('[data-act="expand"]').click();
      assert.equal(await parent.locator('.flow-task-detail').isVisible(),['more','both'].includes(mode));
      assert.equal(await parent.locator('[data-split-input]').isVisible(),['split','both'].includes(mode));
      if(mode==='both')assert.equal(await parent.locator('[data-split-input]').inputValue(),'保留拆分草稿');
      assert.equal(await page.locator('#scheduleAddInput').inputValue(),'保留顶层输入草稿');
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      assert.equal(overflow,false,`${width} zoom ${zoom} ${mode}: page overflow`);
      const geometry=await row(2).evaluate(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right};});
      assert(geometry.left>0&&geometry.right<=width+1,'Step remains inside viewport');
      layouts.push({width,zoom,mode,...geometry});
      if(artifacts)await page.screenshot({path:path.join(artifacts,`${width}-${zoom}-${mode}.png`),fullPage:true});
    }
    await parent.locator('[data-act="expand"]').click();
    await parent.locator('[data-act="split"]').click();
  }
  check('四种展开状态在宽屏、半屏、手机和150%放大下均保留层级且无溢出',layouts.length===20);
  await page.evaluate(()=>document.documentElement.style.zoom='1');
  await page.setViewportSize({width:390,height:1100});
  await row(1).locator('[data-act="split"]').click();
  await row(1).locator('[data-split-input]').fill('填写申请表');
  await row(1).locator('[data-act="split-save"]').click();
  await row(10).waitFor();
  check('再次拆分发送正确父任务id并更新数量',writes.at(-1).body.parent_id===1&&(await group(1).innerText()).includes('拆分步骤 · 2 项'));
  await row(2).locator('[data-act="split"]').click();
  await row(2).locator('[data-split-input]').fill('确认打印店营业时间');
  await row(2).locator('[data-split-input]').press('Enter');
  await row(11).waitFor();
  check('继续拆分形成下一层且请求归属正确',await group(2).locator('[data-task-id="11"]').count()===1&&writes.at(-1).body.parent_id===2);
  await row(11).locator('[data-act="toggle"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-task-id="11"]').classList.contains('is-done'));
  check('完成操作只向所点步骤发请求，显示服务端返回的父任务状态',writes.at(-1).path==='/api/schedule/tasks/11'&&writes.at(-1).body.completed===true&&await row(2).evaluate(el=>el.classList.contains('is-done'))&&await row(1).evaluate(el=>!el.classList.contains('is-done')));
  await row(11).locator('[data-act="toggle"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-task-id="11"]').classList.contains('is-done'));
  await row(2).locator('.flow-task-text').click();
  await row(2).locator('[data-act="text"]').fill('图书馆一楼打印两份申请表');
  await row(2).locator('[data-act="text"]').press('Enter');
  await page.waitForFunction(()=>document.querySelector('[data-task-id="2"] .flow-task-text')?.textContent.includes('两份'));
  check('修改父步骤后下层归属文字同步更新',(await group(2).locator(':scope > .flow-children-heading').innerText()).includes('图书馆一楼打印两份申请表'));
  await row(11).locator('[data-act="fam"][data-value="familiar"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-task-id="11"] [data-value="familiar"]').getAttribute('aria-pressed')==='true');
  check('子步骤属性操作不串到父任务',writes.at(-1).path==='/api/schedule/tasks/11'&&writes.at(-1).body.familiarity==='familiar');
  await row(11).locator('.schedule-color summary').click();
  await row(11).getByRole('button',{name:'珊瑚橙',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[data-task-id="11"]').hasAttribute('data-has-color'));
  check('自选任务颜色保留且不替代父子连接线',await group(2).evaluate(el=>getComputedStyle(el).borderLeftWidth==='2px')&&await row(11).evaluate(el=>getComputedStyle(el).paddingLeft==='14px'));
  await page.evaluate(()=>window.shuranI18n.setLanguage('en'));
  check('切换英文后步骤数量和归属即时翻译',(await group(1).locator(':scope > .flow-children-heading').innerText()).includes('Steps · 2\nPart of “'+initialTitle+'”'));
  await page.locator('#scheduleFlowBtn').click();
  check('流程视图显示完整的多层来源路径',(await row(11).locator('..').locator('..').innerText()).includes(initialTitle+' › 图书馆一楼打印两份申请表'));
  // Parallel layout keeps each step and its origin in the same grid cell.
  Object.assign(all().find(t=>t.id===11),{parallel_group:7,flow_order:0});
  Object.assign(all().find(t=>t.id===3),{parallel_group:7,flow_order:1});
  await page.evaluate(()=>window.loadDailySchedule());
  check('并行流程中归属文字和任务保持在同一格',await page.locator('.flow-parallel .flow-task-node').filter({has:row(11)}).count()===1);
  check('并行视图手机宽度无横向溢出',!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));
  await page.locator('#scheduleFlowBtn').click();
  await page.locator('#scheduleSortBtn').click();
  check('设计流程仍显示原有父任务路径',(await page.locator('.flow-parent-path').allTextContents()).some(text=>text.includes(initialTitle+' / 图书馆一楼打印两份申请表')));
  await page.locator('#scheduleSortBtn').click();
  await page.evaluate(()=>window.shuranI18n.setLanguage('zh-CN'));
  await row(11).locator('[data-act="expand"]').click();
  await row(11).locator('[data-act="delete"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-task-id="11"]'));
  check('删除最后一个下层步骤后空分组消失且上层关系保留',await group(2).count()===0&&await group(1).locator('[data-task-id="2"]').count()===1);
  // Parent titles are data: markup must remain escaped, and changing them updates the group label.
  const hostile='申请 <img src=x onerror="window.hierarchyInjected=true"> & 材料';
  await row(1).locator('.flow-task-text').click();
  await row(1).locator('[data-act="text"]').fill(hostile);await row(1).locator('[data-act="text"]').press('Enter');
  await page.waitForFunction(title=>document.querySelector('[data-task-id="1"] .flow-task-text')?.textContent===title,hostile);
  check('父任务文字安全显示且归属同步变化',(await group(1).locator(':scope > .flow-children-heading').innerText()).includes(hostile)&&await page.locator('#scheduleList img').count()===0&&!await page.evaluate(()=>window.hierarchyInjected));
  check('重要性判断标准紧贴独立选项框',await page.locator('#schedule .flow-attribute-group').filter({has:page.locator('#scheduleNewImportanceLabel')}).evaluate(el=>{
    const chips=[...el.querySelectorAll('.flow-chip')];
    return chips.length===3&&chips.every(chip=>getComputedStyle(chip).borderLeftWidth==='1px')
      &&el.querySelector('.flow-importance-inline')?.textContent.includes('实现自己的目标');
  }));
  await page.locator('#scheduleAddInput').fill('刚写的任务');
  await page.locator('#scheduleAddHours').fill('1');
  await page.locator('#scheduleAddMinutes').fill('30');
  await page.locator('#scheduleAddBtn').click();
  await page.waitForFunction(()=>document.querySelector('#scheduleList .flow-task-text')?.textContent==='刚写的任务');
  check('新任务居上且小时分钟保存为总分钟',writes.at(-1).body.estimated_minutes===90
    &&await page.locator('#scheduleList .flow-task').first().getAttribute('data-task-id')==='12');
  check('完整反馈入口直接提示可记录实际结果',await row(12).locator('.flow-result-entry button').innerText()==='记录实际结果、进展与原因 →');
  await page.locator('#scheduleAddInput').fill('非法分钟');
  await page.locator('#scheduleAddMinutes').fill('61');
  const writesBefore=writes.length;
  await page.locator('#scheduleAddBtn').click();
  check('非法分钟不会创建任务',writes.length===writesBefore&&await page.locator('#scheduleAddInput').inputValue()==='非法分钟');
  check('没有重复id',await page.locator('#schedule [id]').evaluateAll(nodes=>new Set(nodes.map(n=>n.id)).size===nodes.length));
  check('无页面运行错误',errors.length===0);
  const report={passed:checks.length,checks,layouts,errors};
  if(artifacts)fs.writeFileSync(path.join(artifacts,'verification.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  await browser.close();
})().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});
