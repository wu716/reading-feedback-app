# -*- coding: utf-8 -*-
"""进程内限速，单机部署够用。"""
import time

from fastapi import HTTPException, Request, status

_hits: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune(key: str, window_sec: int) -> list[float]:
    now = time.time()
    kept = [t for t in _hits.get(key, []) if now - t < window_sec]
    _hits[key] = kept
    return kept


def guard_rate_limit(key: str, limit: int, window_sec: int, message: str) -> None:
    hits = _prune(key, window_sec)
    if len(hits) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
        )


def record_rate_hit(key: str) -> None:
    _hits.setdefault(key, []).append(time.time())
