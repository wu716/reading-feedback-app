# -*- coding: utf-8 -*-
"""新加坡旧机仍在备份，但用户流量应去香港。"""
from fastapi import Request

CANONICAL_ORIGIN = "http://43.161.238.165:8000"
LEGACY_SINGAPORE_HOSTS = frozenset({"47.236.122.207"})
KEEP_ON_LEGACY_EXACT = frozenset({"/health", "/download/info"})
KEEP_ON_LEGACY_PREFIXES = ("/api", "/owner", "/uploads")


def request_host_name(request: Request) -> str:
    raw = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    host = raw.split(",")[0].strip().lower()
    if host.startswith("["):
        return host.split("]")[0].lstrip("[")
    return host.split(":")[0]


def is_legacy_singapore(request: Request) -> bool:
    return request_host_name(request) in LEGACY_SINGAPORE_HOSTS


def keep_on_legacy_origin(path: str) -> bool:
    normalized = path or "/"
    if normalized in KEEP_ON_LEGACY_EXACT:
        return True
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in KEEP_ON_LEGACY_PREFIXES
    )


def canonical_url(path: str, query: str = "") -> str:
    suffix = path if path.startswith("/") else "/" + path
    url = CANONICAL_ORIGIN.rstrip("/") + suffix
    if query:
        url += "?" + query
    return url
