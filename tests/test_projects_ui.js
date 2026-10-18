// Run with: node tests/test_projects_ui.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) {
    const listeners = new Map();
    elements.set(selector, {
      value:'', innerHTML:'', textContent:'', hidden:false, disabled:false,
      classList:{toggle() {}},
      addEventListener(type, listener) { listeners.set(type, listener); },
      listeners,
    });
  }
  return elements.get(selector);
}

const posted = [];
const overview = {goals:[], projects:[{id:1, title:'项目', outcome:'', stages:[], tasks:[
  {id:3, title:'已排入今天', state:'pending', can_start:true, blocked_by:[]},
  {id:4, title:'另一项', state:'pending', can_start:true, blocked_by:[]},
]}]};
const schedule = {tasks:[
  {id:7, text:'今天独立任务', completed:false, children:[], project_task_id:null},
  {id:8, text:'已排入今天', completed:false, children:[], project_task_id:3},
  {id:9, text:'已完成', completed:true, children:[], project_task_id:null},
]};
const context = {
  document:{querySelector:element, addEventListener() {}},
  localStorage:{getItem:() => 'test-token'},
  location:{href:''},
  setTimeout:() => 1, clearTimeout() {}, setInterval() {},
  fetch:async (url, options = {}) => {
    if (options.method === 'POST') posted.push({url, body:JSON.parse(options.body)});
    const data = url.includes('/overview') ? overview
      : url.includes('/templates') ? {items:[]}
      : url.includes('/sessions') ? {items:[]}
      : url.includes('/api/schedule?') ? schedule : {};
    return {ok:true, json:async () => data};
  },
};

vm.runInNewContext(fs.readFileSync('static/js/projects.js', 'utf8'), context);
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };

(async () => {
  await flush();
  const focus = element('#focusTask');
  assert.match(focus.innerHTML, /value="daily:7"[^>]*>今天独立任务/);
  assert.match(focus.innerHTML, /value="daily:8"[^>]*>已排入今天/);
  assert.doesNotMatch(focus.innerHTML, /value="project:3"/);
  assert.doesNotMatch(focus.innerHTML, /value="daily:9"/);
  assert.match(focus.innerHTML, /value="project:4"/);

  focus.value = 'daily:7';
  element('#startWork').listeners.get('click')();
  await flush();
  assert.deepEqual(posted[0].body.daily_task_id, 7);
  assert.equal(posted[0].body.project_task_id, null);

  focus.value = 'daily:8';
  element('#startWork').listeners.get('click')();
  await flush();
  assert.equal(posted[1].body.daily_task_id, 8);
  assert.equal(posted[1].body.project_task_id, 3);
  console.log('projects UI task selection OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
