# -*- coding: utf-8 -*-
"""Local APK files must be real packages, never GitHub 404 text."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_APK_BYTES = 200_000
APK_MAGIC = b"PK"

GITHUB_APK_URLS = (
    "https://github.com/wu716/reading-feedback-app/releases/download/android-1.5.4/shuran.apk",
    "https://github.com/wu716/reading-feedback-app/releases/download/android-1.5.2/shuran.apk",
)


def is_valid_apk(path: Path | None) -> bool:
    if path is None or not path.is_file():
        return False
    try:
        size = path.stat().st_size
        if size < MIN_APK_BYTES:
            return False
        with path.open("rb") as fh:
            return fh.read(2) == APK_MAGIC
    except OSError:
        return False


def discard_invalid_apk(path: Path) -> None:
    if path.is_file() and not is_valid_apk(path):
        logger.warning("Removing invalid APK cache %s (%s bytes)", path, path.stat().st_size)
        try:
            path.unlink()
        except OSError:
            logger.exception("Could not delete invalid APK %s", path)


def download_apk_from_url(url: str, dest: Path) -> bool:
    tmp = dest.with_suffix(".apk.part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "shuran-apk-fetch"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < MIN_APK_BYTES or not data.startswith(APK_MAGIC):
            logger.error("Refusing non-APK from %s (%s bytes)", url, len(data))
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(dest)
        return is_valid_apk(dest)
    except urllib.error.HTTPError as exc:
        logger.warning("APK URL %s returned HTTP %s", url, exc.code)
        return False
    except Exception:
        logger.exception("Failed to download APK from %s", url)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
