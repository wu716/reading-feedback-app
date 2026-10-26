const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ids = ['reminderMasterSwitch','reminderBrowserSwitch','reminderEmailSwitch','recordReminderSwitch','recordReminderTime'];
const elements = Object.fromEntries([...ids, 'reminderSaveStatus','reminderSaveRetry'].map(id => [id, {checked:true, value:'21:00', disabled:false}]));
let token = 'account-a', fail = false, failLoad = false, nativeResult = 'ok';
const writes = [], nativeWrites = [];
const service = {settingsRevision:0, settingsSaving:false, refreshReliabilityHints(){}, isNativeApp:()=>true,
    applySavedSettings(settings) { nativeWrites.push(settings); return nativeResult; }};
const context = vm.createContext({console:{error(){}},setTimeout,clearTimeout,
    localStorage:{getItem:()=>token}, API_BASE:'',
    window:{reminderNotificationService:service},
    document:{getElementById:id=>elements[id]},
    fetch:async (_url, options={}) => {
        if (!options.method) {
            if (failLoad) throw Error('offline');
            return {ok:true,json:async()=>({is_enabled:true,browser_notification:true,record_reminder_enabled:true,record_reminder_time:'21:00'})};
        }
        if (fail) throw Error('offline');
        const saved = JSON.parse(options.body); writes.push(saved);
        return {ok:true,json:async()=>saved};
    },
});
const html = fs.readFileSync('static/index.html','utf8');
vm.runInContext(html.slice(html.indexOf('        const reminderControlIds ='), html.indexOf('        // 显示编辑昵称模态框')),context);
const wait = () => new Promise(resolve=>setTimeout(resolve,420));
(async()=>{
    await context.loadReminderSettings();
    assert.equal(elements.recordReminderTime.value,'21:00');
    elements.recordReminderTime.value='17:59'; context.queueReminderSettingsSave();
    elements.recordReminderTime.value='18:05'; context.queueReminderSettingsSave();
    await wait();
    assert.equal(writes.length,1,'rapid changes coalesce');
    assert.equal(writes[0].record_reminder_time,'18:05');
    assert.equal(nativeWrites[0].record_reminder_time,'18:05');
    assert.match(elements.reminderSaveStatus.textContent,/已保存并同步/);
    fail = true; elements.recordReminderTime.value='18:10'; context.queueReminderSettingsSave(); await wait();
    assert.equal(elements.recordReminderTime.value,'18:10','failure preserves user input');
    assert.equal(elements.reminderSaveRetry.hidden,false);
    assert.equal(nativeWrites.length,1,'failed server write does not change local alarms');
    fail = false; nativeResult='error'; context.retryReminderSettings(); await wait();
    assert.match(elements.reminderSaveStatus.textContent,/手机同步失败/);
    nativeResult='ok'; context.retryReminderSettings(); await wait();
    assert.equal(service.settingsSaving,false);
    elements.recordReminderTime.value='18:15'; context.queueReminderSettingsSave(); token='account-b'; await wait();
    assert.equal(writes.length,3,'queued save cannot cross accounts');
    service.settingsSaving=false; failLoad=true; await context.loadReminderSettings();
    assert.equal(elements.recordReminderSwitch.checked,true,'load failure cannot display a false opt-out');
    assert.equal(elements.recordReminderTime.value,'18:15');
    assert.equal(elements.recordReminderSwitch.disabled,true);
    assert.match(elements.reminderSaveStatus.textContent,/读取失败/);
    console.log('Reminder autosave: coalescing, failures, retry, account isolation and failed load passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
