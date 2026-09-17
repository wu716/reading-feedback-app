# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest import TestCase

from app.legacy_origin import (
    CANONICAL_ORIGIN,
    canonical_url,
    is_legacy_singapore,
    keep_on_legacy_origin,
    request_host_name,
)
from app.routers.app_download import MIN_SHELL_VERSION_CODE, MIN_SHELL_VERSION_NAME, build_info, load_latest_meta


def _request(host: str, forwarded: str = "") -> SimpleNamespace:
    headers = {"host": host}
    if forwarded:
        headers["x-forwarded-host"] = forwarded
    return SimpleNamespace(headers=headers)


class LegacyOriginTests(TestCase):
    def test_singapore_host_is_legacy(self):
        self.assertTrue(is_legacy_singapore(_request("47.236.122.207:8000")))
        self.assertEqual(request_host_name(_request("47.236.122.207")), "47.236.122.207")

    def test_hong_kong_is_not_legacy(self):
        self.assertFalse(is_legacy_singapore(_request("43.161.238.165:8000")))

    def test_keeps_backup_api_and_update_info(self):
        self.assertTrue(keep_on_legacy_origin("/health"))
        self.assertTrue(keep_on_legacy_origin("/download/info"))
        self.assertTrue(keep_on_legacy_origin("/download/apk"))
        self.assertTrue(keep_on_legacy_origin("/api/auth/me"))
        self.assertFalse(keep_on_legacy_origin("/"))
        self.assertFalse(keep_on_legacy_origin("/download"))
        self.assertFalse(keep_on_legacy_origin("/static/index.html"))

    def test_canonical_url_points_at_hong_kong(self):
        self.assertEqual(
            canonical_url("/download/apk"),
            CANONICAL_ORIGIN + "/download/apk",
        )

    def test_latest_json_forces_1_3_4_up(self):
        meta = load_latest_meta()
        self.assertGreaterEqual(int(meta.get("versionCode") or 0), MIN_SHELL_VERSION_CODE)
        self.assertGreaterEqual(int(meta.get("minVersionCode") or 0), MIN_SHELL_VERSION_CODE)
        self.assertTrue(bool(meta.get("force")))
        self.assertEqual(MIN_SHELL_VERSION_NAME, "1.5.4")
        self.assertEqual(MIN_SHELL_VERSION_CODE, 20)

    def test_build_info_min_is_floor_not_latest(self):
        from unittest.mock import patch

        request = SimpleNamespace(
            headers={"host": "43.161.238.165:8000"},
            base_url="http://43.161.238.165:8000/",
        )
        meta = {
            "versionCode": 21,
            "versionName": "1.5.5",
            "filename": "shuran.apk",
            "notes": "",
            "require_shell": True,
            "force": True,
            "minVersionCode": 20,
            "minVersionName": "1.5.4",
        }
        with patch("app.routers.app_download.load_latest_meta", return_value=meta), patch(
            "app.routers.app_download.find_apk", return_value=None
        ), patch("app.routers.app_download.find_windows_exe", return_value=None), patch(
            "app.routers.app_download.read_apk_version_code", return_value=None
        ):
            info = build_info(request)
        self.assertEqual(int(info["versionCode"]), 21)
        self.assertEqual(int(info["minVersionCode"]), 20)
        self.assertEqual(info["minVersionName"], "1.5.4")

    def test_singapore_update_info_stays_on_singapore(self):
        from unittest.mock import patch

        request = SimpleNamespace(
            headers={"host": "47.236.122.207:8000"},
            base_url="http://47.236.122.207:8000/",
        )
        with patch("app.routers.app_download.ensure_apk", return_value=None), patch(
            "app.routers.app_download.find_apk", return_value=None
        ), patch("app.routers.app_download.find_windows_exe", return_value=None):
            info = build_info(request)
        self.assertFalse(info["available"])
        self.assertGreaterEqual(int(info["versionCode"]), MIN_SHELL_VERSION_CODE)
        self.assertIn("/download/apk", info["download_url"])
        self.assertNotIn("github.com", info["download_url"])
        self.assertIn("47.236.122.207", info["download_url"])
        self.assertEqual(info["size_bytes"], 0)
