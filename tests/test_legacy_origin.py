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
from app.routers.app_download import MIN_SHELL_VERSION_CODE, MIN_SHELL_VERSION_NAME, load_latest_meta


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
        self.assertTrue(keep_on_legacy_origin("/api/auth/me"))
        self.assertFalse(keep_on_legacy_origin("/"))
        self.assertFalse(keep_on_legacy_origin("/download/apk"))
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
        self.assertEqual(MIN_SHELL_VERSION_NAME, "1.5.2")
        self.assertEqual(MIN_SHELL_VERSION_CODE, 18)
