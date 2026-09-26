# -*- coding: utf-8 -*-
"""Android 安装包下载与版本检查：覆盖更新，不必卸载重装。"""
import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.apk_version import apk_meets_min, read_apk_version_code, write_version_sidecar
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
WINDOWS_PROJECT = REPO_ROOT / "desktop" / "windows" / "Shuran.Desktop" / "Shuran.Desktop.csproj"


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


def windows_version_name() -> str:
    """Read the desktop shell version shipped with the repository."""
    if not WINDOWS_PROJECT.is_file():
        return ""
    try:
        root = ET.parse(WINDOWS_PROJECT).getroot()
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] == "Version" and (node.text or "").strip():
                return (node.text or "").strip()
    except (OSError, ET.ParseError):
        logger.exception("Failed to read Windows desktop version")
    return ""


def _iter_apk_candidates() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for path in APK_CANDIDATES:
        if path.is_file() and path not in seen:
            found.append(path)
            seen.add(path)
    if RELEASE_DIR.is_dir():
        apks = sorted(
            RELEASE_DIR.glob("*.apk"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in apks:
            # Probe / temp downloads must never be served.
            if path.name.startswith("_"):
                continue
            if path not in seen:
                found.append(path)
                seen.add(path)
    return found


def find_apk() -> Path | None:
    """Return a usable APK at/above MIN_SHELL_VERSION_CODE, else None."""
    for path in _iter_apk_candidates():
        if apk_meets_min(path, MIN_SHELL_VERSION_CODE):
            return path
        code = read_apk_version_code(path)
        logger.warning(
            "Ignoring stale or unusable APK %s size=%s versionCode=%s",
            path,
            path.stat().st_size if path.is_file() else 0,
            code,
        )
    return None


def _apk_file_ok(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 1024


def _remove_if_stale(path: Path) -> None:
    if not path.is_file():
        return
    if apk_meets_min(path, MIN_SHELL_VERSION_CODE):
        return
    try:
        path.unlink()
        side = path.with_name(path.name + ".versioncode")
        if side.is_file():
            side.unlink()
        logger.warning("Removed stale APK %s", path)
    except OSError:
        logger.exception("Failed to remove stale APK %s", path)


def _cache_apk_from(url: str, dest: Path, expect_code: int | None = None) -> Path | None:
    try:
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading Android package from %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "shuran-app"})
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        logger.exception("Failed to cache APK from %s", url)
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        return None
    if not _apk_file_ok(dest):
        return None
    if not apk_meets_min(dest, MIN_SHELL_VERSION_CODE):
        logger.warning("Cached APK from %s still below min shell; discarding", url)
        try:
            dest.unlink()
        except OSError:
            pass
        return None
    code = expect_code or read_apk_version_code(dest) or MIN_SHELL_VERSION_CODE
    write_version_sidecar(dest, code)
    return dest


def ensure_apk() -> Path | None:
    local = find_apk()
    if local:
        return local
    dest = RELEASE_DIR / "shuran.apk"
    _remove_if_stale(dest)
    return _cache_apk_from(GITHUB_APK_URL, dest, expect_code=MIN_SHELL_VERSION_CODE)


def fetch_apk_from_canonical() -> Path | None:
    dest = RELEASE_DIR / "shuran.apk"
    _remove_if_stale(dest)
    return _cache_apk_from(
        canonical_url("/download/apk"),
        dest,
        expect_code=MIN_SHELL_VERSION_CODE,
    )


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
    apk = find_apk()
    windows_exe = find_windows_exe()
    meta = load_latest_meta()
    download_url = "/download/apk"
    windows_download_url = "/download/windows"
    if request is not None:
        origin = str(request.base_url).rstrip("/")
        download_url = origin + "/download/apk"
        windows_download_url = origin + "/download/windows"
    # latest = 可下载的新包；min = 兼容门槛。二者不能混用，否则每发一版都会把全员锁进强制更新页。
    apk_code = read_apk_version_code(apk) if apk is not None else None
    min_code = max(
        int(meta.get("minVersionCode") or 0),
        MIN_SHELL_VERSION_CODE,
    )
    metadata_code = int(meta.get("versionCode") or 0)
    package_code = int(apk_code or 0)
    package_ready = apk is not None and package_code >= max(metadata_code, min_code)
    # Never advertise metadata for a different (usually older) APK file.
    reported_code = package_code if apk is not None else 0
    reported_name = (
        str(meta.get("versionName") or "") or MIN_SHELL_VERSION_NAME
    ) if package_ready else ""
    if _version_less(reported_name, MIN_SHELL_VERSION_NAME):
        reported_name = MIN_SHELL_VERSION_NAME
    min_name = str(meta.get("minVersionName") or "") or MIN_SHELL_VERSION_NAME
    if _version_less(min_name, MIN_SHELL_VERSION_NAME):
        min_name = MIN_SHELL_VERSION_NAME
    # 只有确认有可用安装包才标 available，避免客户端反复下到旧包死循环。
    info = {
        "available": package_ready,
        "filename": meta["filename"],
        "versionCode": reported_code,
        "versionName": reported_name,
        "notes": meta["notes"],
        "require_shell": True,
        "force": True,
        "minVersionCode": min_code,
        "minVersionName": min_name,
        "download_url": download_url,
        "update_in_place": True,
        "windows_available": windows_exe is not None,
        "windows_filename": "shuran-windows.exe",
        "windows_download_url": windows_download_url,
        "windows_version": windows_version_name(),
        "windows_update_in_place": True,
    }
    if apk is not None:
        size = apk.stat().st_size
        info["size_bytes"] = size
        info["size_mb"] = round(size / (1024 * 1024), 1)
        if apk_code is not None:
            info["apk_version_code"] = apk_code
    else:
        info["size_bytes"] = 0
        info["size_mb"] = 0
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
    # 新加坡旧机若本地只有过期包，尝试从香港拉一份正确包再应答。
    if find_apk() is None and is_legacy_singapore(request):
        fetch_apk_from_canonical()
    if find_apk() is None:
        ensure_apk()
    return build_info(request)


@router.get("/download/apk")
async def download_apk(request: Request):
    # 1.3.4 外壳写死新加坡 URL：必须在本机直接返回字节，禁止 302 去香港/GitHub
    #（旧 HttpURLConnection 跟跨机重定向经常下到空包或失败）。
    apk = find_apk()
    if not apk and is_legacy_singapore(request):
        apk = fetch_apk_from_canonical()
    if not apk:
        apk = ensure_apk()
    if apk and apk_meets_min(apk, MIN_SHELL_VERSION_CODE):
        return FileResponse(
            path=str(apk),
            media_type="application/vnd.android.package-archive",
            filename="shuran.apk",
            headers={"Cache-Control": "no-store"},
        )
    raise HTTPException(
        status_code=503,
        detail="安装包暂不可用或版本过旧，请稍后再试或打开 http://43.161.238.165:8000/download",
    )


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
