// Requires Node >= 20 and Playwright. No production services or data are used.
// Optional: BROWSER_EXE, SHURAN_BROWSER_ARTIFACTS, TEMP/TMP (browser profile location).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');
function sourceBetween(start, end) {
    const from = html.indexOf(start), to = html.indexOf(end, from);
    assert(from >= 0 && to > from, `Missing source boundary: ${start}`);
    return html.slice(from, to);
}
const accountCode = sourceBetween('        function initializeUserCenter()', '        // 显示个人中心弹窗');
const reminderCode = sourceBetween('        const reminderControlIds =', '        // 显示编辑昵称模态框');
const groups = ['meAccountGroup', 'meSecurityGroup', 'meDataGroup', 'meLanguageGroup', 'meReminderGroup'];
const fixture = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');

(async () => {
    const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
    const executablePath = process.env.BROWSER_EXE || (fs.existsSync(edge) ? edge : undefined);
    const browser = await chromium.launch({ executablePath, headless: true });
    try {
        const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await context.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://shuran.test') return route.abort();
            if (url.pathname === '/me-groups') return route.fulfill({ contentType: 'text/html', body: fixture });
            if (url.pathname === '/full-page') return route.fulfill({ contentType: 'text/html', body: html });
            if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/api/') || url.pathname === '/health') {
                let data = {};
                if (url.pathname === '/auth/me') data = { id: 1, name: '合成账号', email: 'synthetic@example.invalid', plan: 'free', is_owner: false };
                if (url.pathname === '/api/reminders/settings') data = {
                    is_enabled: true, browser_notification: true, email_notification: true,
                    record_reminder_enabled: true, record_reminder_time: '18:22'
                };
                return route.fulfill({ json: data });
            }
            const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
            if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
                return route.fulfill({ status: 404, body: '' });
            }
            const contentType = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : 'application/octet-stream';
            return route.fulfill({ contentType, body: fs.readFileSync(file) });
        });
        await page.goto('http://shuran.test/me-groups');
        await page.evaluate(() => {
            const center = document.getElementById('user-center');
            document.body.replaceChildren(center, document.getElementById('editNameModal'));
            document.body.className = 'workspace-layout';
            center.classList.add('active');
            localStorage.setItem('authToken', 'synthetic-account');
            window.savedSettings = [];
            window.exportClicks = 0;
            window.downloadMyData = () => window.exportClicks++;
            window.handleEditNameSubmit = () => {};
            window.validateNickname = () => {};
            window.fetch = async (_url, options = {}) => {
                const settings = options.body ? JSON.parse(options.body) : {
                    is_enabled: true, browser_notification: true, email_notification: true,
                    record_reminder_enabled: true, record_reminder_time: '18:22'
                };
                if (options.body) window.savedSettings.push(settings);
                return { ok: true, json: async () => settings };
            };
        });
        await page.addStyleTag({ content: '#user-center{display:block!important;padding:16px;margin:0}#editNameModal{display:none!important}' });
        await page.addScriptTag({ path: path.join(root, 'static/js/i18n.js') });
        await page.addScriptTag({ content: `const API_BASE=''; function shuranText(key,fallback){return window.shuranI18n.t(key,fallback);}\n${accountCode}\n${reminderCode}\ninitializeUserCenter();` });
        await page.addScriptTag({ path: path.join(root, 'static/js/time-picker.js') });
        await page.evaluate(async () => {
            shuranI18n.setLanguage('zh-CN');
            await loadReminderSettings();
            // Navigation applies translations again after account initialization.
            shuranI18n.apply(document);
        });

        assert.equal(await page.locator('#user-center .me-group-toggle').count(), 5,
            'translation refresh must preserve all five real group buttons');
        assert.match(await page.locator('#meReminderGroup .me-group-summary').innerText(), /18:22/,
            'translation refresh preserves the live reminder summary');
        for (const id of groups) {
            const button = page.locator(`#${id} .me-group-toggle`);
            const content = page.locator(`#${id} .me-group-content`);
            assert.equal(await button.getAttribute('aria-expanded'), 'false');
            assert.equal(await content.isVisible(), false);
            await button.tap();
            assert.equal(await content.isVisible(), true, `${id} expands on tap`);
            await page.locator(`#${id} .me-group-summary`).tap();
            assert.equal(await content.isVisible(), false, `${id} summary is part of its button`);
            await button.focus();
            await page.keyboard.press('Enter');
            assert.equal(await content.isVisible(), true, `${id} expands with Enter`);
            await page.keyboard.press('Space');
            assert.equal(await content.isVisible(), false, `${id} collapses with Space`);
        }

        await page.locator('#meSecurityGroup .me-group-toggle').click();
        await page.locator('#mePasswordDetails > summary').click();
        await page.locator('#oldPasswordInput').fill('synthetic-old');
        await page.locator('#newPasswordInput').fill('synthetic-new');
        await page.locator('#meSecurityGroup .me-group-toggle').click();
        await page.locator('#meSecurityGroup .me-group-toggle').click();
        assert.equal(await page.locator('#newPasswordInput').inputValue(), 'synthetic-new', 'collapse preserves unsaved input');
        await page.locator('#meDataGroup .me-group-toggle').click();
        await page.locator('#meExportBtn').click();
        assert.equal(await page.evaluate(() => window.exportClicks), 1, 'existing export action remains reachable');

        await page.locator('#meLanguageGroup .me-group-toggle').click();
        await page.locator('input[name="languageChoice"][value="en"]').locator('..').click();
        assert.equal(await page.locator('input[name="languageChoice"][value="en"]').isChecked(), true);
        assert.equal(await page.locator('#meSecurityGroup .me-group-toggle').innerText().then(s => s.includes('Account and security')), true);
        assert.equal(await page.locator('#user-center .me-group-toggle').count(), 5, 'language switch preserves buttons');
        await page.locator('input[name="languageChoice"][value="zh-CN"]').locator('..').click();
        await page.evaluate(() => { for (let i = 0; i < 3; i++) shuranI18n.apply(document); });
        await page.locator('#meLanguageGroup .me-group-toggle').click();
        assert.equal(await page.locator('#meLanguageGroup .me-group-content').isVisible(), false);

        await page.locator('#meReminderGroup .me-group-toggle').click();
        await page.locator('#recordReminderSwitch').locator('..').click();
        assert.equal(await page.locator('#recordReminderSwitch').isChecked(), false);
        assert.match(await page.locator('#meReminderGroup .me-group-summary').innerText(), /已关闭/);
        await page.locator('#recordReminderSwitch').locator('..').click();
        await page.locator('#recordReminderTime').locator('..').locator('.tp-field-btn').click();
        assert.deepEqual(errors, [], 'opening the time picker must not throw');
        await page.locator('#tpOverlay .tp-preset[data-time="21:00"]').click();
        await page.locator('#tpOverlay .tp-footer-ok').click();
        await page.waitForFunction(() => window.savedSettings.at(-1)?.record_reminder_time === '21:00');
        assert.match(await page.locator('#meReminderGroup .me-group-summary').innerText(), /21:00/);
        assert.equal(await page.locator('#newPasswordInput').inputValue(), 'synthetic-new');

        await page.evaluate(() => { document.getElementById('recordReminderTime').value = '23:59'; });
        await page.locator('#recordReminderTime').locator('..').locator('.tp-field-btn').click();
        await page.waitForFunction(() => document.getElementById('tpSelectedTime').textContent === '23:59');
        const scrollWheels = delta => page.evaluate(top => {
            for (const id of ['tpHourCol', 'tpMinuteCol']) document.getElementById(id).scrollBy({ top, behavior: 'auto' });
        }, delta);
        await scrollWheels(44);
        await page.waitForFunction(() => document.getElementById('tpSelectedTime').textContent === '00:00');
        await scrollWheels(-44);
        await page.waitForFunction(() => document.getElementById('tpSelectedTime').textContent === '23:59');
        await scrollWheels(44);
        await page.waitForFunction(() => document.getElementById('tpSelectedTime').textContent === '00:00');
        await page.locator('#tpOverlay .tp-footer-ok').click();
        await page.waitForFunction(() => window.savedSettings.at(-1)?.record_reminder_time === '00:00');

        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.waitForFunction(() => [...document.querySelectorAll('.me-group-toggle')].every(button => button.getAttribute('aria-expanded') === 'true'));
        for (const id of groups) assert.equal(await page.locator(`#${id} .me-group-content`).isVisible(), true, `${id} remains visible on desktop`);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForFunction(() => document.querySelector('#meDataGroup .me-group-toggle').getAttribute('aria-expanded') === 'false');
        await page.locator('#meDataGroup .me-group-toggle').click();
        assert.equal(await page.locator('#meExportBtn').isVisible(), true, 'tap still works after resize');
        for (const width of [320, 768]) {
            await page.setViewportSize({ width, height: 900 });
            for (const id of groups) {
                const button = page.locator(`#${id} .me-group-toggle`);
                const expanded = await button.getAttribute('aria-expanded') === 'true';
                await button.tap();
                assert.equal(await page.locator(`#${id} .me-group-content`).isVisible(), !expanded, `${id} responds at ${width}px`);
            }
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `no horizontal overflow at ${width}px`);
        }
        await page.setViewportSize({ width: 390, height: 844 });
        assert.deepEqual(errors, [], 'no uncaught browser exceptions');
        if (process.env.SHURAN_BROWSER_ARTIFACTS) {
            fs.mkdirSync(process.env.SHURAN_BROWSER_ARTIFACTS, { recursive: true });
            await page.locator('#user-center').screenshot({ path: path.join(process.env.SHURAN_BROWSER_ARTIFACTS, 'me-groups-functional.png') });
        }
        // Also exercise the unchanged real bootstrap and all production scripts together.
        await page.evaluate(() => localStorage.clear());
        const fullPage = await context.newPage();
        const fullErrors = [];
        fullPage.on('pageerror', error => fullErrors.push(error.message));
        await fullPage.goto('http://shuran.test/full-page#user-center');
        await fullPage.waitForFunction(() => window.authCheckSettled === true);
        await fullPage.evaluate(() => { closeAuthModal(); shuranI18n.apply(document); });
        assert.equal(await fullPage.locator('#user-center .me-group-toggle').count(), 5, 'real page bootstrap preserves five buttons');
        for (const id of groups) {
            await fullPage.locator(`#${id} .me-group-toggle`).tap();
            assert.equal(await fullPage.locator(`#${id} .me-group-content`).isVisible(), true, `real page ${id} opens`);
        }
        await fullPage.locator('input[name="languageChoice"][value="en"]').locator('..').click();
        await fullPage.evaluate(() => { navigateTo('user-center'); shuranI18n.apply(document); });
        await fullPage.locator('#meDataGroup .me-group-toggle').tap();
        assert.equal(await fullPage.locator('#meDataGroup .me-group-content').isVisible(), false, 'real navigation and language refresh retain events');
        await fullPage.locator('#recordReminderTime').locator('..').locator('.tp-field-btn').click();
        assert.equal(await fullPage.locator('#tpOverlay.is-open').count(), 1, 'time picker opens in the real page');
        await fullPage.locator('#tpOverlay .tp-footer-cancel').click();
        assert.deepEqual(fullErrors, [], 'real page has no uncaught browser exceptions');
        console.log('PASS: full page bootstrap/navigation; five groups, translation refresh, touch, keyboard, preserved input, export, language, reminder save, 23/59 wrapping both ways and 320/390/768/1440px layout');
        await context.close();
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
