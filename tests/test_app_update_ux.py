# -*- coding: utf-8 -*-
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
UPDATE_JS = (ROOT / "static" / "reminder_notification.js").read_text(encoding="utf-8")
DOWNLOAD_HTML = (ROOT / "static" / "download.html").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "main.py").read_text(encoding="utf-8")


class AppUpdateUxTests(TestCase):
    def test_native_updater_does_not_bounce_to_download_page(self):
        start = UPDATE_JS.index("function shuranStartAppUpdate()")
        body = UPDATE_JS[start:UPDATE_JS.index("window.SHURAN_VERSION", start)]
        self.assertIn("if (shell.hasUpdater)", body)
        self.assertIn("checkUpdate()", body)
        self.assertNotIn("copied=1", body)
        self.assertLess(body.index("return;"), body.index("shuranOpenSystemBrowser"))

    def test_old_shell_opens_system_browser_for_apk(self):
        self.assertIn("function shuranAndroidIntentUrl", UPDATE_JS)
        self.assertIn("intent://", UPDATE_JS)
        self.assertIn("android.intent.action.VIEW", UPDATE_JS)
        self.assertIn("shuranOpenSystemBrowser(apkUrl)", UPDATE_JS)

    def test_download_page_prefers_browser_handoff_over_copy_paste(self):
        self.assertIn("用浏览器下载", DOWNLOAD_HTML)
        self.assertIn("openSystemBrowser(apkUrl)", DOWNLOAD_HTML)
        self.assertIn("android.intent.action.VIEW", DOWNLOAD_HTML)
        self.assertNotIn("点击「复制下载链接」", DOWNLOAD_HTML)

    def test_ui_cache_version_bumped(self):
        self.assertIn('STATIC_UI_VERSION = "20260917upd6"', MAIN_PY)
        self.assertIn("20260917upd6", UPDATE_JS)
