"""The download endpoint must use the version inside the signed package."""

import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.apk_version import apk_meets_min, read_apk_version, sidecar_path
from app.routers.app_download import _cache_apk_from, build_info, download_apk, ensure_apk


FIXTURES = Path(__file__).parent / "fixtures"


def _package(directory: str, version: str, sidecar: int | None = None) -> Path:
    apk = Path(directory) / "shuran.apk"
    with ZipFile(apk, "w") as archive:
        archive.write(
            FIXTURES / f"android-manifest-{version}.axml", "AndroidManifest.xml"
        )
    if sidecar is not None:
        sidecar_path(apk).write_text(str(sidecar), encoding="utf-8")
    return apk


def _metadata(code: int = 50, name: str = "2.0.8") -> dict:
    return {
        "versionCode": code,
        "versionName": name,
        "filename": "shuran.apk",
        "notes": "",
        "minVersionCode": 20,
        "minVersionName": "1.5.4",
    }


class ApkReleaseGuardTests(TestCase):
    def _info_and_download(self, apk: Path, meta: dict):
        with patch("app.routers.app_download.find_apk", return_value=apk), patch(
            "app.routers.app_download.find_windows_exe", return_value=None
        ), patch("app.routers.app_download.load_latest_meta", return_value=meta):
            info = build_info()
            try:
                response = asyncio.run(download_apk(SimpleNamespace(headers={})))
            except HTTPException as error:
                response = error
        return info, response

    def test_reads_versions_from_real_android_manifests(self):
        with TemporaryDirectory() as directory:
            old = _package(directory, "2.0")
            self.assertEqual(read_apk_version(old), (42, "2.0"))
        with TemporaryDirectory() as directory:
            new = _package(directory, "2.0.8")
            self.assertEqual(read_apk_version(new), (50, "2.0.8"))

    def test_forged_sidecar_cannot_promote_old_package(self):
        with TemporaryDirectory() as directory:
            old = _package(directory, "2.0", sidecar=50)
            self.assertIsNone(read_apk_version(old))
            self.assertFalse(apk_meets_min(old, 20))
            info, response = self._info_and_download(old, _metadata())
            self.assertFalse(info["available"])
            self.assertEqual(info["versionCode"], 0)
            self.assertEqual(info["versionName"], "")
            self.assertIsInstance(response, HTTPException)
            self.assertEqual(response.status_code, 503)

    def test_new_package_is_advertised_and_served(self):
        with TemporaryDirectory() as directory:
            new = _package(directory, "2.0.8", sidecar=50)
            info, response = self._info_and_download(new, _metadata())
            self.assertTrue(info["available"])
            self.assertEqual(info["versionCode"], 50)
            self.assertEqual(info["versionName"], "2.0.8")
            self.assertIsInstance(response, FileResponse)

    def test_matching_code_with_wrong_name_is_rejected(self):
        with TemporaryDirectory() as directory:
            new = _package(directory, "2.0.8", sidecar=50)
            info, response = self._info_and_download(new, _metadata(name="2.0.1"))
            self.assertFalse(info["available"])
            self.assertIsInstance(response, HTTPException)
            self.assertEqual(response.status_code, 503)

    def test_unreadable_package_is_not_trusted_from_sidecar(self):
        with TemporaryDirectory() as directory:
            apk = Path(directory) / "shuran.apk"
            apk.write_bytes(b"A" * 2048)
            sidecar_path(apk).write_text("50", encoding="utf-8")
            self.assertIsNone(read_apk_version(apk))
            self.assertFalse(apk_meets_min(apk, 20))

    def test_mismatched_package_is_preserved_for_repair(self):
        with TemporaryDirectory() as directory:
            old = _package(directory, "2.0", sidecar=50)
            original = old.read_bytes()
            with patch("app.routers.app_download.RELEASE_DIR", Path(directory)), patch(
                "app.routers.app_download.APK_CANDIDATES", [old]
            ):
                self.assertIsNone(ensure_apk())
            self.assertEqual(old.read_bytes(), original)
            self.assertEqual(sidecar_path(old).read_text(encoding="utf-8"), "50")

    def test_missing_package_uses_release_from_metadata(self):
        with TemporaryDirectory() as directory:
            dest = Path(directory) / "shuran.apk"
            with patch("app.routers.app_download.RELEASE_DIR", Path(directory)), patch(
                "app.routers.app_download.APK_CANDIDATES", [dest]
            ), patch(
                "app.routers.app_download.load_latest_meta",
                return_value=_metadata(code=56, name="2.0.14"),
            ), patch("app.routers.app_download._cache_apk_from") as cache:
                ensure_apk()
            cache.assert_called_once_with(
                "https://github.com/wu716/reading-feedback-app/releases/download/android-2.0.14/shuran.apk",
                dest,
                expect_code=56,
                expected_version=(56, "2.0.14"),
            )

    def test_auto_download_rejects_package_from_other_release(self):
        with TemporaryDirectory() as directory:
            source = _package(directory, "2.0.8")
            with ZipFile(source, "a") as archive:
                archive.writestr("padding.bin", b"0" * 2048)
            dest = Path(directory) / "cached.apk"
            with patch("app.routers.app_download.RELEASE_DIR", Path(directory)), patch(
                "app.routers.app_download.urllib.request.urlopen",
                return_value=BytesIO(source.read_bytes()),
            ):
                self.assertIsNone(
                    _cache_apk_from(
                        "https://example.invalid/shuran.apk",
                        dest,
                        expect_code=56,
                        expected_version=(56, "2.0.14"),
                    )
                )
            self.assertFalse(dest.exists())
