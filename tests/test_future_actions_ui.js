// Run with a Playwright installation: PLAYWRIGHT_PACKAGE=<package path> node tests/test_future_actions_ui.js
// Uses the real capture markup, styles and module, with synthetic API responses only.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');
const capture = source.match(/<section id="capture"[\s\S]*?<\/section>/)[0].replace('class="content-section"', 'class="content-section active"');
const collection = source.match(/<section id="future-actions"[\s\S]*?<\/section>/)[0];
const composer = source.match(/<dialog id="scheduleLaterDialog"[\s\S]*?<\/dialog>/)[0];
const styles = [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(match => match[1]).join('\n') + ['app-tabbar.css','schedule-log.css','desktop-split.css','paper-shell.css','workspace.css'].map(name => fs.readFileSync(path.join(root,'static/css',name),'utf8')).join('\n');
const moduleSource = fs.readFileSync(path.join(root,'static/js/future-actions.js'),'utf8');
const navigation = source.slice(source.indexOf('const PRIMARY_TABS_DESKTOP'), source.indexOf('// 页面加载时根据hash显示对应区域'));
const shell = ['app-tabbar.js','workspace-shell.js'].map(name=>fs.readFileSync(path.join(root,'static/js',name),'utf8')).join('\n');
const fixture = `<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${styles}</style></head><body class="workspace-layout"><header class="app-header"><button id="headerBackBtn">返回</button></header><main class="app-main">${capture}${collection}${composer}</main><script>window.apiRequest=async(path,options)=>{const r=await fetch(path,options);const data=await r.json();if(!r.ok)throw new Error(data.detail);return data;};window.loadDailySchedule=()=>Promise.resolve();function isMobileNav(){return innerWidth<=768;}function currentSectionId(){return document.querySelector('.content-section.active')?.id;}function closeMobileSidebar(){}${navigation}</script><script>${moduleSource}\n${shell}</script></body></html>`;
let browser;
const checks = [];
const check = (name, value) => {assert(value,name);checks.push(name);};
(async () => {
  browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge',headless:true});
  const context = await browser.newContext({viewport:{width:1280,height:1000}});
  const page = await context.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>localStorage.setItem('authToken','synthetic-token'));
  let items=[{id:2,text:'合成想法二'},{id:1,text:'合成想法一'}], nextId=3, removed;
  let failSave=false, failRead=false, holdRead=false, releaseRead, readCaptured;
  let postCalls=0;
  const scheduled=[];
  await page.route('http://shuran.test/**',async route=>{
    const request=route.request(),url=new URL(request.url()),method=request.method();
    const reply=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fixture});
    const match=url.pathname.match(/^\/api\/schedule\/future(?:\/(\d+))?(?:\/(schedule|restore))?$/);
    assert(match,'Unexpected request '+url.pathname);
    const id=Number(match[1]);
    const body=request.postDataJSON();
    if(method==='GET') {
      if(failRead){failRead=false;return reply({detail:'模拟读取失败'},503);}
      const snapshot=items.map(item=>({...item}));
      if(holdRead){holdRead=false;readCaptured?.();await new Promise(resolve=>{releaseRead=resolve;});}
      return reply({items:snapshot});
    }
    if(method==='POST'&&!id) {
      ++postCalls;
      if(failSave){failSave=false;return reply({detail:'模拟断网，稍后重试'},503);}
      await new Promise(resolve=>setTimeout(resolve,150));
      items.unshift({id:nextId++,text:body.text});
    } else if(method==='PATCH')items=items.map(item=>item.id===id?{...item,text:body.text}:item);
    else if(method==='DELETE'){removed=items.find(item=>item.id===id);items=items.filter(item=>item.id!==id);return reply({items,undo_token:'synthetic-receipt'});}
    else if(match[2]==='restore'){assert.equal(body.undo_token,'synthetic-receipt');items.push(removed);items.sort((a,b)=>b.id-a.id);}
    else if(match[2]==='schedule'){scheduled.push(body.task_date);items=items.filter(item=>item.id!==id);return reply({date:body.task_date,tasks:[]});}
    return reply({items});
  });
  await page.goto('http://shuran.test/');
  await page.evaluate(()=>window.loadFutureActions());
  const input=page.locator('#scheduleLaterInput'), count=page.locator('#scheduleLaterSummary');
  const waitCount=n=>page.waitForFunction(n=>document.getElementById('scheduleLaterSummary').textContent.startsWith(String(n)),n);
  const idle=()=>page.waitForFunction(()=>!document.getElementById('scheduleLater').hasAttribute('aria-busy'));
  check('三个同级写入入口可见',await page.getByRole('button',{name:'记下此刻',exact:true}).isVisible()&&await page.getByRole('button',{name:'记下 idea',exact:true}).isVisible()&&await page.locator('#scheduleLaterWrite').isVisible());
  check('首页不展开输入或历史列表',!(await input.isVisible())&&!(await page.locator('#scheduleLaterBody').isVisible()));
  await page.locator('#scheduleLaterWrite').click();
  check('录入使用独立模态框',await page.locator('#scheduleLaterDialog').evaluate(el=>el.open&&el.matches(':modal')));
  await page.locator('#scheduleLaterAddBtn').click();
  check('空白不提交',postCalls===0&&(await page.locator('#scheduleLaterComposerStatus').textContent()).includes('先写下'));
  await input.fill('输入法选字');
  await input.dispatchEvent('keydown',{key:'Enter',keyCode:229,isComposing:true,bubbles:true,cancelable:true});
  check('中文输入法确认键不提交',postCalls===0);
  await input.press('Shift+Enter');
  check('Shift+Enter换行',(await input.inputValue()).includes('\n')&&postCalls===0);
  await input.press('Escape');
  check('关闭填写框恢复入口焦点',await page.locator('#scheduleLaterWrite').evaluate(el=>el===document.activeElement));
  await page.locator('#scheduleLaterWrite').click();
  check('收起再打开保留草稿',(await input.inputValue()).includes('输入法选字'));
  failSave=true;
  await input.fill('失败也不能丢的内容');
  await input.press('Enter');
  await page.getByText('模拟断网，稍后重试',{exact:true}).waitFor();await idle();
  check('保存失败保留输入',await input.inputValue()==='失败也不能丢的内容');
  const before=postCalls;
  await input.press('Enter');await input.press('Enter');await input.press('Enter');
  await waitCount(3);await idle();
  check('重复确认只创建一次',postCalls===before+1&&await input.inputValue()==='');
  check('首页保存后关闭填写框并保留独立列表',!(await input.isVisible())&&!(await page.locator('#scheduleLaterBody').isVisible()));
  check('保存后恢复入口焦点',await page.locator('#scheduleLaterWrite').evaluate(el=>el===document.activeElement));
  await page.locator('#scheduleLaterToggle').click();await idle();
  check('查看进入独立页面',await page.locator('#future-actions').evaluate(el=>el.classList.contains('active'))&&await page.evaluate(()=>location.hash==='#future-actions'));
  check('独立列表仍归属记',await page.locator('[data-workspace-route="capture"]').first().getAttribute('aria-current')==='page'&&await page.locator('#appTabbar [data-tab="capture"]').evaluate(el=>el.classList.contains('active')));
  check('返回路径指向记',await page.evaluate(()=>sectionParentOf('future-actions'))==='capture');
  await page.locator('.capture-later-title').first().click();
  await page.locator('[data-later-act="text"]').fill('尚未保存的编辑');
  await page.locator('#scheduleLaterWriteFromList').click();
  await input.fill('新增不会覆盖编辑草稿');await input.press('Enter');await waitCount(4);await idle();
  check('新增不覆盖编辑草稿',await page.locator('[data-later-act="text"]').inputValue()==='尚未保存的编辑');
  await page.locator('#scheduleLaterBack').click();
  await page.locator('#scheduleLaterToggle').click();
  check('返回再进入保留编辑草稿',await page.locator('[data-later-act="text"]').inputValue()==='尚未保存的编辑');
  await page.locator('[data-later-act="save"]').click();await idle();
  check('编辑保存到原记录',items.some(item=>item.text==='尚未保存的编辑'));
  await page.locator('[data-later-act="delete"]').first().click();await waitCount(3);await idle();
  check('删除后键盘焦点落在撤销按钮',await page.locator('#scheduleLaterUndo').evaluate(el=>document.activeElement===el));
  await page.locator('#scheduleLaterUndo').click();await waitCount(4);await idle();
  check('删除可撤销并恢复原标识',items.some(item=>item.id===4));
  await page.locator('[data-later-act="arrange"]').first().click();
  await page.locator('input[data-later-act="date"]').fill('2026-11-07');
  await page.locator('[data-later-act="confirm"]').click();await waitCount(3);await idle();
  check('按明确选择的日期安排',scheduled[0]==='2026-11-07');
  holdRead=true;
  const captured=new Promise(resolve=>{readCaptured=resolve;});
  await page.evaluate(()=>{window.loadFutureActions();});await captured;
  await page.locator('#scheduleLaterWriteFromList').click();
  await input.fill('<img src=x onerror=alert(1)>');await input.press('Enter');await waitCount(4);await idle();
  releaseRead();await page.waitForTimeout(50);
  check('旧读取响应不能覆盖新保存',await count.textContent()==='4 个');
  check('内容作为纯文本显示',await page.locator('.capture-later-title').first().textContent()==='<img src=x onerror=alert(1)>'&&await page.locator('#scheduleLater img').count()===0);
  failRead=true;await page.evaluate(()=>window.loadFutureActions());
  check('读取失败提供重试入口',await page.locator('#scheduleLaterRetry').isVisible());
  await page.locator('#scheduleLaterRetry').click();
  await page.waitForFunction(()=>document.getElementById('scheduleLaterRetry').hidden);
  await page.locator('#scheduleLaterWriteFromList').click();
  check('手机返回优先关闭填写框',await page.evaluate(()=>window.handleAppBack())==='consumed'&&!(await input.isVisible())&&await page.locator('#future-actions').evaluate(el=>el.classList.contains('active')));
  check('手机返回从列表回到记',await page.evaluate(()=>window.handleAppBack())==='consumed'&&await page.locator('#capture').evaluate(el=>el.classList.contains('active')));
  const layouts=[];
  for(const width of [1440,775,390,320]) {
    await page.setViewportSize({width,height:1000});
    const geometry=await page.locator('#capture').evaluate(el=>{
      const bounds=el.getBoundingClientRect();
      const cards=[...el.querySelectorAll('.capture-entry-grid > .card')].map(card=>{const r=card.getBoundingClientRect();return{width:r.width,top:r.top,buttons:[...card.querySelectorAll('button')].map(b=>b.getBoundingClientRect().top)};});
      const overflow=[...el.querySelectorAll('*')].filter(node=>{const r=node.getBoundingClientRect();return r.width>0&&(r.right>bounds.right+1||r.left<bounds.left-1);}).map(node=>node.id||node.className);
      return{cards,overflow};
    });
    check(`${width}px没有横向溢出`,geometry.overflow.length===0);
    if(width>=775)check(`${width}px三者等宽同排`,geometry.cards.every(card=>Math.abs(card.width-geometry.cards[0].width)<1&&Math.abs(card.top-geometry.cards[0].top)<1));
    if(width>=775)check(`${width}px两行按钮位置对齐`,geometry.cards.every(card=>card.buttons.every((top,i)=>Math.abs(top-geometry.cards[0].buttons[i])<1)));
    if(process.env.FUTURE_UI_ARTIFACTS){fs.mkdirSync(process.env.FUTURE_UI_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.FUTURE_UI_ARTIFACTS,`capture-${width}.png`),fullPage:true});}
    await page.locator('#scheduleLaterWrite').click();
    const dialogBounds=await page.locator('#scheduleLaterDialog').evaluate(el=>{const r=el.getBoundingClientRect();return{left:r.left,right:r.right,width:innerWidth,overflow:el.scrollWidth>el.clientWidth};});
    check(`${width}px填写框无横向溢出`,dialogBounds.left>=0&&dialogBounds.right<=dialogBounds.width&&!dialogBounds.overflow);
    if(process.env.FUTURE_UI_ARTIFACTS)await page.screenshot({path:path.join(process.env.FUTURE_UI_ARTIFACTS,`compose-${width}.png`),fullPage:true});
    await page.locator('#scheduleLaterCancel').click();
    await page.locator('#scheduleLaterToggle').click();
    check(`${width}px列表无横向溢出`,await page.locator('#future-actions').evaluate(el=>el.scrollWidth<=el.clientWidth));
    if(process.env.FUTURE_UI_ARTIFACTS)await page.screenshot({path:path.join(process.env.FUTURE_UI_ARTIFACTS,`list-${width}.png`),fullPage:true});
    await page.locator('#scheduleLaterBack').click();
    layouts.push({width,...geometry});
  }
  await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>document.documentElement.style.zoom='1.25');
  await page.locator('#scheduleLaterWrite').click();await input.press('Shift+Tab');
  check('放大后填写框键盘焦点留在对话框内',await page.locator('#scheduleLaterDialog').evaluate(el=>el.contains(document.activeElement)));
  await input.press('Escape');
  await page.evaluate(()=>document.documentElement.style.zoom='1');
  check('无页面运行错误',errors.length===0);
  const report={passed:checks.length,checks,layouts,errors};
  if(process.env.FUTURE_UI_ARTIFACTS)fs.writeFileSync(path.join(process.env.FUTURE_UI_ARTIFACTS,'verification.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  await browser.close();
})().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});
