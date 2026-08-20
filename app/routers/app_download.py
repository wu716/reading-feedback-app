# -*- coding: utf-8 -*-
"""Android 安装包下载：避开微信拦截，供系统浏览器下载。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["app-download"])

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO_ROOT / "releases"
APK_CANDIDATES = [
    RELEASE_DIR / "shuran.apk",
    REPO_ROOT / "mobile" / "android" / "dist" / "shuran-1.0.0.apk",
    REPO_ROOT / "static" / "releases" / "shuran.apk",
]


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


@router.get("/download/info")
async def download_info():
    apk = find_apk()
    if not apk:
        return {"available": False}
    size = apk.stat().st_size
    return {
        "available": True,
        "filename": "shuran.apk",
        "size_bytes": size,
        "size_mb": round(size / (1024 * 1024), 1),
    }


@router.get("/download/apk")
async def download_apk():
    apk = find_apk()
    if not apk:
        raise HTTPException(status_code=404, detail="安装包尚未上传")

    return FileResponse(
        path=str(apk),
        media_type="application/octet-stream",
        filename="shuran.apk",
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
