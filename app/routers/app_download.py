# -*- coding: utf-8 -*-
"""Android 安装包下载与版本检查：覆盖更新，不必卸载重装。"""
import json
import logging
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.legacy_origin import canonical_url, is_legacy_singapore

logger = logging.getLogger(__name__)

GITHUB_APK_URL = (
    "https://github.com/wu716/reading-feedback-app/releases/download/"
    "android-1.5.4/shuran.apk"
)
# 线上 latest.json 若过旧，1.3.4 会误以为已是最新。接口永不低于此门槛。
MIN_SHELL_VERSION_CODE = 20
MIN_SHELL_VERSION_NAME = "1.5.4"

router = APIRouter(tags=["app-download"])

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO_ROOT / "releases"
LATEST_META = RELEASE_DIR / "latest.json"
APK_CANDIDATES = [
    RELEASE_DIR / "shuran.apk",
    REPO_ROOT / "mobile" / "android" / "dist" / "shuran-1.0.0.apk",
    REPO_ROOT / "static" / "releases" / "shuran.apk",
]
WINDOWS_CANDIDATES = [
    RELEASE_DIR / "shuran-windows.exe",
    RELEASE_DIR / "Shuran.exe",
]


def find_windows_exe() -> Path | None:
    for path in WINDOWS_CANDIDATES:
        if path.is_file():
            return path
    if RELEASE_DIR.is_dir():
        exes = sorted(
            RELEASE_DIR.glob("*.exe"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if exes:
            return exes[0]
    return None


def find_apk() -> Path | None:
    for path in APK_CANDIDATES:
        if path.is_file():
            return path
    if RELEASE_DIR.is_dir():
        apks = sorted(
            RELEASE_DIR.glob("*.apk"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if apks:
            return apks[0]
    return None


def ensure_apk() -> Path | None:
    local = find_apk()
    if local:
        return local
    dest = RELEASE_DIR / "shuran.apk"
    try:
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading Android package from GitHub Releases")
        urllib.request.urlretrieve(GITHUB_APK_URL, dest)
    except Exception:
        logger.exception("Failed to cache APK from GitHub")
        return None
    return dest if dest.is_file() else None


def _version_tuple(name: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(name or "").replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts) or (0,)


def _version_less(current: str, latest: str) -> bool:
    pa, pb = _version_tuple(current), _version_tuple(latest)
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    return pa < pb


def load_latest_meta() -> dict:
    defaults = {
        "versionCode": 0,
        "versionName": "",
        "filename": "shuran.apk",
        "notes": "覆盖安装即可更新，登录数据会保留，不必卸载重装。",
        "require_shell": False,
        "force": True,
        "minVersionCode": 0,
        "minVersionName": MIN_SHELL_VERSION_NAME,
    }
    if not LATEST_META.is_file():
        return defaults
    try:
        data = json.loads(LATEST_META.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults
        version_code = data.get("versionCode", defaults["versionCode"])
        try:
            version_code = int(version_code)
        except (TypeError, ValueError):
            version_code = 0
        notes = data.get("notes") or defaults["notes"]
        try:
            min_code = int(data.get("minVersionCode") or version_code or 0)
        except (TypeError, ValueError):
            min_code = version_code
        return {
            "versionCode": version_code,
            "versionName": str(data.get("versionName") or ""),
            "filename": str(data.get("filename") or defaults["filename"]),
            "notes": str(notes),
            "require_shell": True,
            "force": bool(data.get("force", True)),
            "minVersionCode": min_code,
            "minVersionName": str(data.get("minVersionName") or MIN_SHELL_VERSION_NAME),
        }
    except Exception:
        return defaults


def build_info(request: Request | None = None) -> dict:
    apk = ensure_apk() or find_apk()
    windows_exe = find_windows_exe()
    meta = load_latest_meta()
    download_url = "/download/apk"
    windows_download_url = "/download/windows"
    if request is not None:
        origin = str(request.base_url).rstrip("/")
        download_url = origin + "/download/apk"
        windows_download_url = origin + "/download/windows"
    # 外壳落后时必须能发现新安装包。门槛取 json 与硬编码的较高值，避免旧 json 漏掉 1.3.4。
    reported_code = max(
        int(meta.get("versionCode") or 0),
        int(meta.get("minVersionCode") or 0),
        MIN_SHELL_VERSION_CODE,
    )
    reported_name = str(meta.get("versionName") or "") or MIN_SHELL_VERSION_NAME
    if _version_less(reported_name, MIN_SHELL_VERSION_NAME):
        reported_name = MIN_SHELL_VERSION_NAME
    min_name = str(meta.get("minVersionName") or "") or MIN_SHELL_VERSION_NAME
    if _version_less(min_name, MIN_SHELL_VERSION_NAME):
        min_name = MIN_SHELL_VERSION_NAME
    if request is not None and is_legacy_singapore(request):
        download_url = canonical_url("/download/apk")
        windows_download_url = canonical_url("/download/windows")
    info = {
        "available": True,
        "filename": meta["filename"],
        "versionCode": reported_code,
        "versionName": reported_name,
        "notes": meta["notes"],
        "require_shell": True,
        "force": True,
        "minVersionCode": reported_code,
        "minVersionName": min_name,
        "download_url": download_url,
        "update_in_place": True,
        "windows_available": windows_exe is not None,
        "windows_filename": "shuran-windows.exe",
        "windows_download_url": windows_download_url,
    }
    if apk is not None:
        size = apk.stat().st_size
        info["size_bytes"] = size
        info["size_mb"] = round(size / (1024 * 1024), 1)
    else:
        info["available"] = True
        info["size_bytes"] = 1810063
        info["size_mb"] = 1.7
        info["download_url"] = GITHUB_APK_URL
    if windows_exe is not None:
        wsize = windows_exe.stat().st_size
        info["windows_size_bytes"] = wsize
        info["windows_size_mb"] = round(wsize / (1024 * 1024), 1)
    else:
        info["windows_size_bytes"] = 0
        info["windows_size_mb"] = 0
    return info


@router.get("/download/info")
async def download_info(request: Request):
    return build_info(request)


@router.get("/download/apk")
async def download_apk(request: Request):
    if is_legacy_singapore(request):
        return RedirectResponse(
            canonical_url("/download/apk"),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )
    apk = ensure_apk()
    if apk:
        return FileResponse(
            path=str(apk),
            media_type="application/vnd.android.package-archive",
            filename="shuran.apk",
            headers={"Cache-Control": "no-store"},
        )
    return RedirectResponse(GITHUB_APK_URL, status_code=302)


@router.get("/download/windows")
async def download_windows():
    exe = find_windows_exe()
    if not exe:
        raise HTTPException(status_code=404, detail="Windows 应用尚未上传")

    return FileResponse(
        path=str(exe),
        media_type="application/vnd.microsoft.portable-executable",
        filename="shuran-windows.exe",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/download")
async def download_page():
    page = REPO_ROOT / "static" / "download.html"
    if not page.is_file():
        return JSONResponse({"detail": "下载页缺失"}, status_code=404)
    return FileResponse(
        str(page),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
