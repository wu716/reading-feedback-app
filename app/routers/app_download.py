# -*- coding: utf-8 -*-
"""Android 安装包下载与版本检查：覆盖更新，不必卸载重装。"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

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


def load_latest_meta() -> dict:
    defaults = {
        "versionCode": 0,
        "versionName": "",
        "filename": "shuran.apk",
        "notes": "覆盖安装即可更新，登录数据会保留，不必卸载重装。",
        "require_shell": False,
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
        return {
            "versionCode": version_code,
            "versionName": str(data.get("versionName") or ""),
            "filename": str(data.get("filename") or defaults["filename"]),
            "notes": str(notes),
            "require_shell": bool(data.get("require_shell")),
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
    # 界面在网页里，打开即最新。默认不把安装包标成「有新版本」，
    # 避免手机外壳启动时误弹更新。真正要换系统能力时，把 require_shell 打开。
    reported_code = meta["versionCode"] if meta.get("require_shell") else 0
    info = {
        "available": apk is not None,
        "filename": meta["filename"],
        "versionCode": reported_code,
        "versionName": meta["versionName"],
        "notes": meta["notes"],
        "require_shell": bool(meta.get("require_shell")),
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
    return build_info(request)


@router.get("/download/apk")
async def download_apk():
    apk = find_apk()
    if not apk:
        raise HTTPException(status_code=404, detail="安装包尚未上传")

    return FileResponse(
        path=str(apk),
        media_type="application/vnd.android.package-archive",
        filename="shuran.apk",
        headers={"Cache-Control": "no-store"},
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
