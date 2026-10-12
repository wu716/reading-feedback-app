"""The download endpoint must never serve an APK older than the release metadata."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.routers.app_download import download_apk


class ApkReleaseGuardTests(TestCase):
    def _download_for_code(self, code: int):
        with TemporaryDirectory() as directory:
            apk = Path(directory) / "shuran.apk"
            apk.write_bytes(b"A" * 2048)
            meta = {"versionCode": 42, "minVersionCode": 20}

            with patch("app.routers.app_download.find_apk", return_value=apk), patch(
                "app.routers.app_download.load_latest_meta", return_value=meta
            ), patch("app.routers.app_download.read_apk_version_code", return_value=code):
                return asyncio.run(download_apk(SimpleNamespace(headers={})))

    def test_rejects_old_apk_after_metadata_bump(self):
        with self.assertRaises(HTTPException) as error:
            self._download_for_code(24)
        self.assertEqual(error.exception.status_code, 503)

    def test_serves_matching_apk(self):
        response = self._download_for_code(42)
        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.status_code, 200)
