const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { JSDOM } = require(process.env.SHURAN_UI_TEST_MODULES ? path.join(process.env.SHURAN_UI_TEST_MODULES, 'jsdom') : 'jsdom');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'static/js/methods.js'), 'utf8');
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((resolve) => setTimeout(resolve, 0)); };

async function page() {
    const dom = new JSDOM(html, { url: 'http://shuran.example.test/#methods', runScripts: 'outside-only' });
    const w = dom.window;
    await new Promise((resolve) => w.addEventListener('load', resolve, { once: true }));
    const requests = [], notices = [], serverCards = [];
    let failCreateAt = 0, createCalls = 0, feedbackFails = false, heldList = null;
    w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    w.HTMLDialogElement.prototype.close = function () { this.open = false; };
    w.confirm = () => true;
    w.showMessage = (message, type) => notices.push({ message, type });
    w.showAuthModal = () => notices.push({ message: 'login requested' });
    w.clearAuthSession = () => { w.localStorage.removeItem('authToken'); w.dispatchEvent(new w.Event('shuran-auth-change')); };
    w.fetch = async (url, options = {}) => {
        const body = options.body ? JSON.parse(options.body) : null;
        requests.push({ url, options, body });
        const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
        if (url.endsWith('/visits')) return response({ recorded: true }, 201);
        if (url.endsWith('/product-feedback')) return feedbackFails ? response({ detail: '暂时未发送成功' }, 503) : response({ message: '收到' }, 201);
        if (url.includes('/sources')) return response({ items: [] });
        if (url.includes('?state=all')) {
            if (heldList) return await heldList;
            return response({ items: serverCards, total: serverCards.length });
        }
        if (url === '/api/methods' && options.method === 'POST') {
            createCalls++;
            if (createCalls === failCreateAt) return response({ detail: '连接中断，请重试' }, 503);
            let saved = serverCards.find((card) => card.client_key === body.client_key);
            if (!saved) {
                saved = { ...body, id: serverCards.length + 1, state: 'active', tried_count: 0, helpful_count: 0, pending_use: null, recent_uses: [] };
                serverCards.push(saved);
            }
            return response(saved, 201);
        }
        throw new Error('Unexpected request: ' + url);
    };
    w.eval(script);
    await flush();
    const $ = (id) => w.document.getElementById(id);
    const click = (selector) => { const element = w.document.querySelector(selector); assert.ok(element, selector); element.click(); };
    const submit = (id) => $(id).dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    async function create(situation = '图书馆打开材料后又刷手机', step = '把手机放进包里，只读第一段') {
        $('methodNewBtn').click(); $('methodSituation').value = situation; $('methodFirstStep').value = step;
        submit('methodEditorForm'); await flush();
    }
    return { w, $, click, submit, create, requests, notices, serverCards,
        failCreateAt: (value) => { failCreateAt = value; },
        feedbackFails: (value) => { feedbackFails = value; },
        holdList: (value) => { heldList = value; }, close: () => w.close() };
}

test('visitor can save two fields; rendered text is escaped and metrics exclude private content', async () => {
    const p = await page();
    try {
        await p.create('自己的私有情境', '<img src=x onerror="alert(1)">只打开一页');
        assert.equal(p.$('methodEditor').open, false);
        assert.equal(p.w.document.querySelectorAll('.method-card').length, 1);
        assert.equal(p.w.document.querySelector('.method-card img'), null);
        assert.ok(p.w.document.querySelector('.method-step').textContent.includes('<img'));
        const telemetry = p.requests.filter((request) => request.url.endsWith('/visits'));
        assert.ok(telemetry.length >= 2);
        assert.ok(telemetry.every((request) => Object.keys(request.body).sort().join(',') === 'event_name,session_key'));
        assert.ok(telemetry.every((request) => request.options.credentials === 'omit'));
        assert.ok(!p.notices.some((notice) => notice.message === 'login requested'));
    } finally { p.close(); }
});

test('start is pending; feedback can be corrected and several trials in a day remain separate', async () => {
    const p = await page();
    try {
        await p.create();
        p.click('[data-card-action="start"]'); await flush();
        assert.equal(p.$('methodUseDialog').open, true);
        assert.equal(p.$('methodUseDetailsForm').hidden, true);
        p.click('[data-outcome="not_used"]'); await flush();
        assert.ok(p.$('methodStats').textContent.includes('0次试过'));
        assert.equal(p.$('methodUseDetailsForm').hidden, false);
        p.$('methodBarrier').value = 'forgot'; p.submit('methodUseDetailsForm'); await flush();
        p.click('[data-use-edit]'); p.click('[data-outcome="helpful"]'); await flush();
        assert.ok(p.$('methodStats').textContent.includes('1次试过'));
        assert.equal(p.$('methodUseDialog').open, false);
        p.click('[data-card-action="start"]'); await flush();
        p.click('[data-outcome="not_helpful"]'); await flush();
        assert.ok(p.$('methodStats').textContent.includes('2次试过'));
        const saved = JSON.parse(p.w.localStorage.getItem('shuran.methods.demo.v1'));
        assert.equal(saved[0].uses.length, 2);
        assert.equal(saved[0].uses[1].barrier, null);
    } finally { p.close(); }
});

test('failed product feedback retains the message and a successful retry acknowledges delivery', async () => {
    const p = await page();
    try {
        p.$('methodFeedbackBtn').click(); p.$('methodFeedbackMessage').value = '保存后找不到使用入口';
        p.feedbackFails(true); p.submit('methodProductFeedbackForm'); await flush();
        assert.equal(p.$('methodFeedbackDialog').open, true);
        assert.equal(p.$('methodFeedbackMessage').value, '保存后找不到使用入口');
        assert.ok(p.$('methodFeedbackError').textContent.includes('未发送成功'));
        p.feedbackFails(false); p.submit('methodProductFeedbackForm'); await flush();
        assert.equal(p.$('methodFeedbackDialog').open, false);
        assert.equal(p.$('methodFeedbackMessage').value, '');
        assert.ok(p.notices.some((notice) => notice.message.includes('已发送给开发者')));
    } finally { p.close(); }
});

test('partial imports can be retried and late responses cannot reveal the previous account', async () => {
    const p = await page();
    try {
        await p.create('第一种情境', '第一步'); await p.create('第二种情境', '第二步');
        p.w.localStorage.setItem('authToken', 'test-reader'); p.w.dispatchEvent(new p.w.Event('shuran-auth-change')); await flush();
        p.failCreateAt(2); p.$('methodDemoAction').click(); await flush();
        assert.equal(p.serverCards.length, 1);
        assert.equal(JSON.parse(p.w.localStorage.getItem('shuran.methods.demo.v1')).length, 1);
        p.failCreateAt(0); p.$('methodDemoAction').click(); await flush();
        assert.equal(p.serverCards.length, 2);
        assert.equal(JSON.parse(p.w.localStorage.getItem('shuran.methods.demo.v1')).length, 0);
        assert.ok(p.requests.filter((r) => r.url === '/api/methods' && r.options.method === 'POST').every((r) => !('uses' in r.body)));
        let resolve;
        const held = new Promise((done) => { resolve = done; }); p.holdList(held);
        const pending = p.w.ShuranMethods.load();
        p.w.localStorage.removeItem('authToken'); p.w.dispatchEvent(new p.w.Event('shuran-auth-change')); await flush();
        resolve({ ok: true, status: 200, json: async () => ({ items: [{ id: 99, title: '前一账号的私有内容', situation: '私有情境', first_step: '私有动作', state: 'active' }] }) });
        await pending; await flush();
        assert.ok(!p.$('methodGrid').textContent.includes('前一账号的私有内容'));
    } finally { p.close(); }
});
