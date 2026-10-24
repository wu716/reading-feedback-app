import hashlib
import json

from app.routers import app_download as download
from fastapi import FastAPI
from fastapi.testclient import TestClient


def package(tmp_path, monkeypatch):
    executable = tmp_path / "shuran-windows.exe"
    executable.write_bytes(b"synthetic-package-1.6.4")
    manifest = tmp_path / "windows-latest.json"
    manifest.write_text(json.dumps({
        "filename": executable.name, "versionName": "1.6.4",
        "size_bytes": executable.stat().st_size,
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    monkeypatch.setattr(download, "WINDOWS_META", manifest)
    monkeypatch.setattr(download, "WINDOWS_CANDIDATES", [executable])
    monkeypatch.setattr(download, "RELEASE_DIR", tmp_path)
    monkeypatch.setattr(download, "windows_version_name", lambda: "1.6.4")
    return executable, manifest


def test_verified_windows_package_is_available(tmp_path, monkeypatch):
    executable, _ = package(tmp_path, monkeypatch)
    assert download.find_windows_exe() == executable


def test_old_or_corrupted_executable_is_not_advertised(tmp_path, monkeypatch):
    executable, _ = package(tmp_path, monkeypatch)
    executable.write_bytes(b"synthetic-package-1.6.3")
    assert download.find_windows_exe() is None


def test_hash_cache_invalidates_after_replacing_package(tmp_path, monkeypatch):
    executable, _ = package(tmp_path, monkeypatch)
    assert download.find_windows_exe() == executable
    executable.write_bytes(b"other-package-bytes-xxx")
    assert download.find_windows_exe() is None


def test_metadata_version_must_match_source(tmp_path, monkeypatch):
    _, manifest = package(tmp_path, monkeypatch)
    meta = json.loads(manifest.read_text())
    meta["versionName"] = "1.6.3"
    manifest.write_text(json.dumps(meta), encoding="utf-8")
    assert download.find_windows_exe() is None


def test_download_routes_never_serve_an_old_package_as_new(tmp_path, monkeypatch):
    executable, _ = package(tmp_path, monkeypatch)
    monkeypatch.setattr(download, "find_apk", lambda: None)
    app = FastAPI()
    app.include_router(download.router)
    with TestClient(app) as client:
        assert client.get("/download/info").json()["windows_available"] is True
        assert client.get("/download/windows").content == executable.read_bytes()
        executable.write_bytes(b"old-executable")
        assert client.get("/download/info").json()["windows_available"] is False
        assert client.get("/download/windows").status_code == 404
