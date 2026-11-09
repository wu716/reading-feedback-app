// PLAYWRIGHT_PACKAGE=<package path> node tests/test_mobile_long_term_navigation_ui.js
// Uses real navigation, page markup, page mounting, translations and styles; no business requests.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const root = path.resolve(__dirname, '..');
const read = name => process.env.SHURAN_TEST_GIT_INDEX
  ? execFileSync('git', ['show', ':' + name], {cwd:root,encoding:'utf8',env:{...process.env,GIT_INDEX_FILE:process.env.SHURAN_TEST_GIT_INDEX}})
  : fs.readFileSync(path.join(root,name),'utf8');
const index = read('static/index.html');
const first = index.indexOf('<section id="daily-feedback"');
const last = index.indexOf('<section id="time-log"',first);
assert(first>=0 && last>first,'Real long-term and feedback markup is present');
const markup = index.slice(first,last);
const navStart = index.indexOf('const PRIMARY_TABS_DESKTOP');
const startupMarker = index.indexOf('// 页面加载时根据hash显示对应区域',navStart);
const navigation = index.slice(navStart,startupMarker);
const startupStart = index.indexOf("window.addEventListener('DOMContentLoaded', async () => {",startupMarker);
const startupEnd = index.indexOf('            updateHeaderBackButton();',startupStart);
const startup = index.slice(startupStart,startupEnd)+'});';
const longTerm = read('static/js/long-term.js');
const prepare = longTerm.slice(longTerm.indexOf('window.prepareDailyFeedback = function'),longTerm.indexOf('window.loadLongTerm = async function'));
// Preserve the real cascade, including mobile-review.css after workspace.css.
const css = [...index.matchAll(/<style[^>]*>([\s\S]*?)<\/style>|<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g)]
  .map(m=>m[1] || (m[2]?.startsWith('/static/') ? read(m[2].split('?')[0].slice(1)) : '')).join('\n');
const headerStart=index.indexOf('<header class="app-header">');
const header=index.slice(headerStart,index.indexOf('</header>',headerStart)+9);
const sectionMarkup=(id,next)=>index.slice(index.indexOf(`<section id="${id}"`),index.indexOf(`<section id="${next}"`));
const relatedMarkup=sectionMarkup('schedule','user-center')+sectionMarkup('capture','future-actions')+sectionMarkup('user-center','owner');
const i18n = read('static/js/i18n.js'), tabbar=read('static/js/app-tabbar.js');
const fixture = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${css}</style></head><body class="workspace-layout">${header}<main class="app-main">${relatedMarkup}${markup}</main><script>const el=id=>document.getElementById(id);function isMobileNav(){return innerWidth<=768;}function currentSectionId(){return document.querySelector('.content-section.active')?.id;}function closeMobileSidebar(){}function loadUserInfo(){}function loadReminderSettings(){}window.loadLongTerm=()=>{};${prepare}${navigation}${startup}</script><script>${i18n}</script><script>${tabbar}</script><script>${read('static/js/workspace-shell.js')}</script></body></html>`;
const projectFixture = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>${css}</style></head><body class="workspace-layout"><main><h1>项目执行</h1></main><script>${i18n}</script><script>${tabbar}</script></body></html>`;
const checks=[],layouts=[],artifacts=process.env.MOBILE_LONG_TERM_ARTIFACTS;
const check=(name,value)=>{assert(value,name);checks.push(name);};
if(artifacts)fs.mkdirSync(artifacts,{recursive:true});
let browser;
(async()=>{
  browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.setDefaultTimeout(7000);page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('shuran.language','zh-CN'));
  await page.route('http://shuran.test/**',route=>{
    const url=new URL(route.request().url());
    assert(!url.pathname.startsWith('/api/'),'Navigation must not write business data');
    if(!url.pathname.endsWith('.html'))return route.fulfill({status:204,body:''});
    return route.fulfill({contentType:'text/html',body:url.pathname.endsWith('projects.html')?projectFixture:fixture});
  });
  const goal=page.locator('#appTabbar [data-tab="long-term"]');
  const section=()=>page.locator('.content-section.active').getAttribute('id');
  await page.goto('http://shuran.test/static/index.html#schedule');
  check('手机底栏完整显示长期目标且没有反馈替代项',(await goal.locator('.tab-text').innerText())==='长期目标'&&await page.locator('#appTabbar [data-tab="daily-feedback"]').count()===0);
  await goal.click();
  check('底栏进入长期目标页面并选中目标项',await section()==='long-term'&&(await goal.getAttribute('class')).includes('active')&&await page.locator('#ltPageTitle').innerText()==='长期目标');
  check('长期目标保留每日记录、统计报告和目标分类入口',await page.getByRole('button',{name:'每日记录',exact:true}).isVisible()&&await page.getByRole('button',{name:'统计报告',exact:true}).isVisible()&&await page.getByRole('button',{name:'目标与分类',exact:true}).isVisible());
  await page.locator('#ltDate').fill('2026-11-03');
  await page.locator('#ltFeedbackEntry').click();
  check('每日反馈仍可由明确的页内入口进入',await section()==='daily-feedback'&&await page.locator('#ltPageTitle').innerText()==='每日反馈');
  check('进入每日反馈时长期目标仍是所属主导航',(await goal.getAttribute('class')).includes('active'));
  await page.locator('#ltGoalsEntry').click();
  check('返回长期目标保持同一表单和日期值',await section()==='long-term'&&await page.locator('#long-term .lt-page').count()===1&&await page.locator('#ltDate').inputValue()==='2026-11-03'&&await page.locator('.lt-page').count()===1);
  for(const [width,zoom] of [[320,1],[369,1.3],[390,1],[768,1],[390,1.5],[390,2]]){
    await page.setViewportSize({width,height:844});await page.evaluate(scale=>document.documentElement.style.zoom=String(scale),zoom);
    await page.evaluate(()=>window.scrollTo(0,0));
    const geometry=await goal.evaluate(el=>{const b=el.getBoundingClientRect(),t=el.querySelector('.tab-text').getBoundingClientRect();return {left:b.left,right:b.right,textLeft:t.left,textRight:t.right};});
    const heading=await page.evaluate(()=>{const header=document.querySelector('.app-header').getBoundingClientRect(),eyebrow=document.querySelector('.lt-eyebrow').getBoundingClientRect(),title=document.querySelector('#ltPageTitle').getBoundingClientRect();return {headerBottom:header.bottom,eyebrowTop:eyebrow.top,titleTop:title.top};});
    check(`${width}px ${zoom}倍下页眉和标题位于导航下方`,heading.eyebrowTop>=heading.headerBottom&&heading.titleTop>=heading.headerBottom);
    check(`${width}px ${zoom}倍下长期目标文字完整且页面无横向溢出`,await goal.isVisible()&&geometry.textLeft>=geometry.left&&geometry.textRight<=geometry.right+1&&!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
    layouts.push({width,zoom,...geometry,...heading});if(artifacts)await page.screenshot({path:path.join(artifacts,`mobile-${width}-${zoom}.png`),fullPage:true});
  }
  await page.evaluate(()=>document.documentElement.style.zoom='1');await page.setViewportSize({width:390,height:844});
  for(const id of ['schedule','capture','user-center']){
    await page.locator(`#appTabbar [data-tab="${id}"]`).click();
    await page.waitForFunction(()=>scrollY===0);
    const sharedGeometry=await page.evaluate(()=>({mainTop:document.querySelector('.app-main').getBoundingClientRect().top,headerBottom:document.querySelector('.app-header').getBoundingClientRect().bottom,scrollY,sectionTop:document.querySelector('.content-section.active').getBoundingClientRect().top}));
    check(`${id}共用导航不遮挡正文 ${JSON.stringify(sharedGeometry)}`,sharedGeometry.mainTop>=sharedGeometry.headerBottom);
  }
  await goal.click();
  // Approximate Android text enlargement separately from whole-page zoom.
  for(const width of [320,369])for(const scale of [1.3,2]){
    await page.setViewportSize({width,height:844});await page.reload();
    await page.waitForFunction(()=>scrollY===0);
    await page.evaluate(scale=>{
      const fonts=[...document.querySelectorAll('body *')].filter(el=>el.getClientRects().length).map(el=>{const c=getComputedStyle(el);return [el,parseFloat(c.fontSize),c.lineHeight];});
      fonts.forEach(([el,size,line])=>{el.style.fontSize=size*scale+'px';if(line!=='normal')el.style.lineHeight=parseFloat(line)*scale+'px';});
    },scale);
    check(`${width}px文字放大${scale}倍后标题和页眉完整`,await page.evaluate(()=>document.querySelector('.lt-eyebrow').getBoundingClientRect().top>=document.querySelector('.app-header').getBoundingClientRect().bottom));
    check(`${width}px文字放大${scale}倍后三个视图标签没有越界`,await page.locator('.lt-view-tabs button').evaluateAll(buttons=>buttons.every(button=>{const range=document.createRange();range.selectNodeContents(button);const text=range.getBoundingClientRect(),box=button.getBoundingClientRect();return text.left>=box.left-1&&text.right<=box.right+1;})));
    if(artifacts)await page.screenshot({path:path.join(artifacts,`text-${width}-${scale}.png`)});
  }
  await page.setViewportSize({width:390,height:844});await page.reload();
  const reminderSource=read('static/reminder_notification.js');
  await page.addScriptTag({content:reminderSource.slice(0,reminderSource.indexOf('function shuranHasNativeMethod'))});
  await page.evaluate(()=>{window.reminderNotificationService.ensureUi();document.getElementById('reminderBellWrap').hidden=false;window.scrollTo(0,200);});
  check('滚动时顶部导航继续吸顶',await page.locator('.app-header').evaluate(el=>Math.abs(el.getBoundingClientRect().top)<1));
  await page.locator('#reminderBellBtn').click();
  check('吸顶导航中的铃铛仍可展开',await page.locator('#reminderDropdown').isVisible());
  check('消息浮层位于导航下方',await page.evaluate(()=>document.getElementById('reminderDropdown').getBoundingClientRect().top>=document.querySelector('.app-header').getBoundingClientRect().bottom));
  await page.locator('#reminderDropdownClose').click();
  check('消息收起后恢复页面滚动',!await page.locator('#reminderDropdown').isVisible()&&await page.evaluate(()=>document.body.style.overflow===''));
  await page.evaluate(()=>scrollTo(0,0));
  await page.evaluate(()=>window.shuranI18n.setLanguage('en'));
  check('语言切换更新目标入口且仍然可以点击',await goal.locator('.tab-text').innerText()==='Goals');
  await page.locator('#ltFeedbackEntry').click();await goal.focus();await goal.press('Enter');
  check('英文状态下键盘也能返回长期目标',await section()==='long-term');
  for(const query of ['record=today','record=2026-11-03&report=week','feedback=12','report=day']){
    await page.goto('http://shuran.test/static/index.html?'+query+'&keep=1#long-term');
    check('旧链接首次仍进入反馈：'+query,await section()==='daily-feedback');
    await goal.click();
    const url=new URL(page.url());
    check('主动打开长期目标清除旧反馈参数并保留其他参数：'+query,await section()==='long-term'&&['record','feedback','report'].every(key=>!url.searchParams.has(key))&&url.searchParams.get('keep')==='1');
    await page.reload();check('刷新不会被旧参数重新拉回反馈：'+query,await section()==='long-term');
  }
  await page.goto('http://shuran.test/static/index.html?feedback=12#daily-feedback');
  check('新的反馈通知深链接仍正常进入反馈页',await section()==='daily-feedback');
  await page.locator('#ltGoalsEntry').click();
  check('反馈页自身的查看长期目标按钮也不会被旧参数劫回',await section()==='long-term'&&!new URL(page.url()).searchParams.has('feedback'));
  await page.locator('#ltFeedbackEntry').click();await goal.click();await page.goBack();
  check('浏览器返回仍可回到反馈页',await section()==='daily-feedback');
  await page.goto('http://shuran.test/static/projects.html?view=execution');await goal.click();
  await page.waitForURL('http://shuran.test/static/index.html#long-term');
  check('项目与执行页的底栏也返回长期目标',await section()==='long-term');
  for(const width of [960,1280]){
    await page.setViewportSize({width,height:900});
    check(`${width}px桌面不会额外显示手机底栏`,!await goal.isVisible());
    check(`${width}px桌面导航仍位于正文之前`,await page.evaluate(()=>document.querySelector('.app-main').getBoundingClientRect().top>=document.querySelector('.app-header').getBoundingClientRect().bottom&&! (document.documentElement.scrollWidth>innerWidth)));
    if(artifacts)await page.screenshot({path:path.join(artifacts,`desktop-${width}.png`)});
  }
  check('没有页面运行错误',errors.length===0);
  const report={passed:checks.length,checks,layouts,errors};
  if(artifacts)fs.writeFileSync(path.join(artifacts,'verification.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));await browser.close();
})().catch(async error=>{console.error(error);await browser?.close();process.exitCode=1;});
