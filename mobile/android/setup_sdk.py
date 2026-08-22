# -*- coding: utf-8 -*-
"""Download Android SDK packages from Tencent mirror and unpack them."""
from __future__ import annotations

import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

SDK_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"
TOOLS = Path(os.environ.get("LOCALAPPDATA", "")) / "shuran-android-tools"
MIRROR = "https://mirrors.cloud.tencent.com/AndroidSDK/"

PACKAGES = {
    "commandlinetools-win-11076708_latest.zip": "cmdline",
    "build-tools_r34-windows.zip": "build-tools",
    "platform-UpsideDownCake_r04.zip": "platform",
    "platform-tools_r35.0.2-win.zip": "platform-tools",
}

LICENSE_HASHES = {
    "android-sdk-license": "24333b20aef56131b8d1bb45e31c2dcd0fc2e6ec",
    "android-sdk-preview-license": "84831b9409646161cecb09b7a2839dfd885b7f81",
}


def download(name: str) -> Path:
    dest = TOOLS / name
    TOOLS.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1024 * 1024:
        print(f"already have {dest} ({dest.stat().st_size} bytes)")
        return dest
    url = MIRROR + name
    print(f"download {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"saved {dest} ({dest.stat().st_size} bytes)")
    return dest


def unzip(zip_path: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)


def first_dir(path: Path) -> Path:
    dirs = [p for p in path.iterdir() if p.is_dir()]
    return dirs[0] if len(dirs) == 1 else path


def write_licenses() -> None:
    license_dir = SDK_ROOT / "licenses"
    license_dir.mkdir(parents=True, exist_ok=True)
    for name, digest in LICENSE_HASHES.items():
        (license_dir / name).write_text(digest + "\n", encoding="ascii")


def main() -> None:
    SDK_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = TOOLS / "sdk-extract"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    zips = {kind: download(name) for name, kind in PACKAGES.items()}

    cmdline_src = tmp / "cmdline"
    unzip(zips["cmdline"], cmdline_src)
    latest = SDK_ROOT / "cmdline-tools" / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    latest.parent.mkdir(parents=True, exist_ok=True)
    inner = cmdline_src / "cmdline-tools"
    shutil.move(str(inner if inner.exists() else first_dir(cmdline_src)), str(latest))

    bt_src = tmp / "build-tools"
    unzip(zips["build-tools"], bt_src)
    bt_dest = SDK_ROOT / "build-tools" / "34.0.0"
    if bt_dest.exists():
        shutil.rmtree(bt_dest)
    bt_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(first_dir(bt_src)), str(bt_dest))

    plat_src = tmp / "platform"
    unzip(zips["platform"], plat_src)
    plat_dest = SDK_ROOT / "platforms" / "android-34"
    if plat_dest.exists():
        shutil.rmtree(plat_dest)
    plat_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(first_dir(plat_src)), str(plat_dest))

    pt_src = tmp / "platform-tools"
    unzip(zips["platform-tools"], pt_src)
    pt_dest = SDK_ROOT / "platform-tools"
    if pt_dest.exists():
        shutil.rmtree(pt_dest)
    inner_pt = pt_src / "platform-tools"
    shutil.move(str(inner_pt if inner_pt.exists() else first_dir(pt_src)), str(pt_dest))

    write_licenses()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"SDK ready at {SDK_ROOT}")


if __name__ == "__main__":
    main()
