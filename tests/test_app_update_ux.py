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
        self.assertNotIn("location.href = pageUrl", body)
        self.assertNotIn("from=app", body)

    def test_old_shell_opens_system_browser_for_apk(self):
        self.assertIn("function shuranAndroidIntentUrl", UPDATE_JS)
        self.assertIn("intent://", UPDATE_JS)
        self.assertIn("android.intent.action.VIEW", UPDATE_JS)
        self.assertIn("shuranOpenSystemBrowser(apkUrl)", UPDATE_JS)

    def test_in_app_download_page_returns_home(self):
        self.assertIn("window.location.replace(next)", DOWNLOAD_HTML)
        self.assertIn('"/?update=1"', DOWNLOAD_HTML)
        self.assertIn("inShuranApp", DOWNLOAD_HTML)

    def test_current_shell_can_dismiss_update_gate(self):
        self.assertIn("window.SHURAN_SHELL_GATE_LOCKED = false", UPDATE_JS)
        self.assertIn("existing.remove()", UPDATE_JS)
        self.assertNotIn("data-locked') === '1'", UPDATE_JS)

    def test_ui_cache_version_bumped(self):
        self.assertIn('STATIC_UI_VERSION = "20260917upd8"', MAIN_PY)
        self.assertIn("20260917upd8", UPDATE_JS)
