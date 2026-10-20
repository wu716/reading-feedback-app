// Run with: node tests/test_projects_ui.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) {
    const listeners = new Map();
    elements.set(selector, {value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,
      classList:{toggle() {}},scrollIntoView() {},
      addEventListener(type,listener) {listeners.set(type,listener);},listeners});
  }
  return elements.get(selector);
}
element('#focusFinished').hidden = true;
element('#focusReminderSettings').hidden = true;
const posted = [], sessions = [];
const alarms = [], saved = new Map();
let ticker;
let simulatedNow;
let plan = {queue:[],daily_tasks:[],work_minutes:20,break_minutes:5,paused:null,remaining_seconds:null};
const overview = {goals:[],projects:[{id:1,title:'项目',outcome:'',stages:[],tasks:[
  {id:3,project_id:1,title:'已排入今天',state:'pending',can_start:true,blocked_by:[]},
  {id:4,project_id:1,title:'另一项',state:'pending',can_start:true,blocked_by:[]},
]}]};
const schedule = {tasks:[
  {id:7,text:'今天独立任务',completed:false,children:[],project_task_id:null},
  {id:8,text:'已排入今天',completed:false,children:[],project_task_id:3},
  {id:9,text:'已完成',completed:true,children:[],project_task_id:null},
]};
function start(body) {
  const row={...body,id:sessions.length+1,source:'timer',started_at:new Date().toISOString(),ended_at:null,
    planned_seconds:body.planned_seconds || body.planned_minutes*60,
    deadline_at:new Date(Date.now()+(body.planned_seconds || body.planned_minutes*60)*1000).toISOString()};
  sessions.unshift(row);plan.paused=null;plan.remaining_seconds=null;return row;
}
const context = {
  Date:class extends Date { static now() { return simulatedNow ?? Date.now(); } },
  URLSearchParams,
  document:{querySelector:element,addEventListener() {},hidden:false},
  localStorage:{getItem:key=>key==='authToken' ? 'test-token' : saved.get(key) || null,
    setItem:(key,value)=>saved.set(key,value)},location:{href:'',search:''},
  ShuranNative:{hasPermission:()=>true,setFocusTimer:json=>alarms.push(JSON.parse(json))},
  setTimeout:()=>1,clearTimeout() {},setInterval:fn=>{ticker=fn;},
  fetch:async(url,options={})=>{
    const body=options.body ? JSON.parse(options.body) : null;
    if(options.method==='POST')posted.push({url,body});
    let data;
    if(url.endsWith('/execution') && options.method==='PUT'){plan={...plan,...body};data=plan;}
    else if(url.endsWith('/execution/resume')) {const old=plan.paused;data=start({...old,planned_seconds:plan.remaining_seconds});}
    else if(url.endsWith('/execution'))data=plan;
    else if(url.endsWith('/sessions/start'))data=start(body);
    else if(url.match(/\/sessions\/\d+\/stop$/)){
      const row=sessions.find(s=>s.id===Number(url.split('/').at(-2)));row.ended_at=new Date().toISOString();
      if(body.pause){plan.paused=row;plan.remaining_seconds=733;}data=row;
    }
    else if(url.includes('/overview'))data=overview;
    else if(url.includes('/templates'))data={items:[]};
    else if(url.includes('/sessions')){
      sessions.forEach(s=>{if(!s.ended_at && (simulatedNow ?? Date.now())>=Date.parse(s.deadline_at))s.ended_at=s.deadline_at;});
      data={items:sessions};
    }
    else if(url.includes('/api/schedule?'))data=schedule;
    else data={};
    return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};
  },
};
vm.runInNewContext(fs.readFileSync('static/js/projects.js','utf8'),context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(setImmediate);};
async function click(selector){element(selector).listeners.get('click')();await flush();}
(async()=>{
 await flush();
 const focus=element('#focusTask');
 assert.match(focus.innerHTML,/value="daily:7"[^>]*>今天独立任务/);
 assert.match(focus.innerHTML,/value="daily:8"[^>]*>已排入今天/);
 assert.doesNotMatch(focus.innerHTML,/value="project:3"/);
 assert.doesNotMatch(focus.innerHTML,/value="daily:9"/);
 assert.match(focus.innerHTML,/value="project:4"/);
 focus.value='project:4';
 await click('#addTodayQueue');
 assert.deepEqual(plan.queue,['daily:7','daily:8']);
 await click('#startWork');
 assert.equal(posted.at(-1).body.daily_task_id,7,'queue head determines the active task');
 assert.equal(posted.at(-1).body.project_task_id,null);
 await click('#switchWork');
 assert.equal(posted.at(-1).body.daily_task_id,8);
 assert.equal(posted.at(-1).body.project_task_id,3);
 assert.deepEqual(plan.queue,['daily:8','daily:7']);
 await click('#pauseWork');
 assert.equal(posted.at(-1).body.pause,true);
 assert.equal(element('#timerDisplay').textContent,'12:13');
 await click('#startWork');
 assert.match(posted.at(-1).url,/execution\/resume$/);
 assert.equal(sessions[0].planned_seconds,733);
 await click('#switchWork');
 assert.equal(posted.at(-1).body.daily_task_id,7,'A returns after B');
 assert.equal(alarms.at(-1).id,sessions[0].id,'an active slice schedules the native alarm');
 await click('#pauseWork');
 assert.equal(alarms.at(-1).id,undefined,'pausing cancels the native alarm');
 assert.equal(element('#focusFinished').hidden,true,'pausing does not show a completion reminder');
 await click('#startWork');
 simulatedNow=Date.parse(sessions[0].deadline_at)+1000;
 ticker(); await flush();
 assert.equal(element('#focusFinished').hidden,false,'expiry keeps a visible reminder');
 assert.equal(element('#focusFinishedTitle').textContent,'工作片到时');
 assert.equal(sessions[0].ended_at,sessions[0].deadline_at,'server settles the slice at the deadline');
 assert.equal(alarms.at(-1).completed,true,'natural expiry preserves the pending native reminder');
 await click('#focusAcknowledge');
 assert.equal(element('#focusFinished').hidden,true);
 ticker(); await flush();
 assert.equal(element('#focusFinished').hidden,true,'acknowledged slice does not remind twice');
 console.log('PASS queue selection, A → B → A rotation, and pause/resume remaining time');
})().catch(error=>{console.error(error);process.exitCode=1;});
