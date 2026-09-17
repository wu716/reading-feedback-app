# -*- coding: utf-8 -*-
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app.apk_file import GITHUB_APK_URLS, discard_invalid_apk, download_apk_from_url, is_valid_apk


class ApkFileTests(TestCase):
    def test_rejects_github_not_found_text(self):
        with TemporaryDirectory() as tmp:
            poison = Path(tmp) / "shuran.apk"
            poison.write_text("Not Found", encoding="ascii")
            self.assertFalse(is_valid_apk(poison))
            discard_invalid_apk(poison)
            self.assertFalse(poison.exists())

    def test_rejects_missing_and_tiny_zip_header(self):
        self.assertFalse(is_valid_apk(None))
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.apk"
            self.assertFalse(is_valid_apk(missing))
            tiny = Path(tmp) / "tiny.apk"
            tiny.write_bytes(b"PK\x03\x04" + b"\x00" * 10)
            self.assertFalse(is_valid_apk(tiny))

    def test_accepts_zip_magic_with_enough_bytes(self):
        with TemporaryDirectory() as tmp:
            apk = Path(tmp) / "shuran.apk"
            apk.write_bytes(b"PK\x03\x04" + b"\x00" * 200_000)
            self.assertTrue(is_valid_apk(apk))

    def test_published_fallback_is_1_5_2(self):
        self.assertTrue(any(url.endswith("android-1.5.2/shuran.apk") for url in GITHUB_APK_URLS))

    def test_download_refuses_not_found_body(self):
        class FakeResp:
            def read(self):
                return b"Not Found"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "shuran.apk"
            with patch("app.apk_file.urllib.request.urlopen", return_value=FakeResp()):
                self.assertFalse(download_apk_from_url("http://example/missing.apk", dest))
            self.assertFalse(dest.exists())
