// Run with: node tests/test_record_reminders_ui.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let token = 'account-a';
const schedules = [], dismissed = [], opened = [];
let payload;
const host = {appendChild: element => { host.lastToast = element; element.parentElement = host; }};
class FakeElement {
    constructor() { this.dataset = {}; this.children = {}; this.parentElement = null; }
    set className(value) { this._className = value; }
    set innerHTML(value) { this._innerHTML = value; }
    querySelector(selector) {
        const key = selector.match(/\[data-(\w+)\]/)?.[1];
        return this.children[key] ||= {onclick: null};
    }
    remove() { this.parentElement = null; }
}
const context = vm.createContext({
    console, setTimeout, clearTimeout, URL,
    localStorage: {getItem: () => token},
    window: {ShuranNative: {scheduleReminders: raw => schedules.push(JSON.parse(raw)), requestPermission() {}, pollNow() {}},
        openLongTermToday: () => opened.push('today')},
    document: {
        getElementById: id => id === 'inAppReminderToastHost' ? host : null,
        createElement: () => new FakeElement(),
    },
    fetch: async () => ({ok: true, json: async () => payload}),
});
const source = fs.readFileSync('static/reminder_notification.js', 'utf8').split('window.reminderNotificationService =')[0];
vm.runInContext(source + '\nthis.service = new ReminderNotificationService();', context);
const service = context.service;
service.isNativeApp = () => true;
service.syncNativeSession = () => {};
service.syncNativeTodos = () => {};
service.refreshReliabilityHints = () => {};
service.ensureUi = () => {};
service.renderAll = () => {};
service.closeDropdown = () => {};
service.dismissReminder = (...args) => dismissed.push(args);

(async () => {
    payload = {is_enabled:true, record_reminder_enabled:true, record_reminder_time:'22:15', record_date:'2026-10-22', record_complete:true};
    await service.syncNativeSchedule();
    assert.equal(schedules[0].recordTime, '22:15');
    assert.equal(schedules[0].recordComplete, true);
    assert.equal(schedules[0].dailyEnabled, false);
    assert.equal(schedules[0].recordDate, '2026-10-22');
    payload = {notifications:[], record_reminder_enabled:true, record_reminder_time:'21:00', record_date:'2026-10-23', record_complete:false};
    await service.checkPendingReminders();
    assert.equal(schedules[1].recordDate, '2026-10-23');
    assert.equal(schedules[1].recordComplete, false);
    service.goToAction({reminder_type:'daily_record',log_id:9}, true);
    assert.deepEqual(opened, ['today']);
    assert.deepEqual(dismissed, [[9,true]]);
    let inPage = 0, native = 0;
    const showInPageToast = service.showInPageToast.bind(service);
    service.showInPageToast = (...args) => { inPage++; return showInPageToast(...args); };
    service.showNativeNotification = () => native++;
    service.announceNew({system_notification:false});
    assert.equal(inPage, 1); assert.equal(native, 0);
    service.shownToastIds.clear();
    service.showInPageToast({log_id:42,title:'提交项目反馈',message:'反馈内容'});
    const toast = host.lastToast;
    toast.querySelector('[data-close]').onclick();
    assert.equal(toast.parentElement, null);
    assert.deepEqual(dismissed.at(-1), [42,false], 'closing the toast dismisses the reminder persistently');
    service.shownToastIds.clear();
    service.showInPageToast({log_id:43,title:'提交项目反馈',message:'反馈内容'});
    const laterToast = host.lastToast;
    laterToast.querySelector('[data-later]').onclick();
    assert.deepEqual(dismissed.at(-1), [43,false], 'choosing later dismisses the reminder persistently');
    // Responses from the previous account cannot update the current account's alarms.
    context.fetch = async () => {token = 'account-b'; return {ok:true,json:async()=>payload};};
    const before = schedules.length;
    await service.checkPendingReminders();
    assert.equal(schedules.length, before);
    console.log('Daily record reminder UI behavior passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
