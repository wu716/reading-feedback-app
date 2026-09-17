# -*- coding: utf-8 -*-
"""Read Android APK versionCode without aapt (best-effort + sidecar)."""
from __future__ import annotations

import logging
import struct
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Known broken artifact once served as "latest" (1.5.2 / versionCode 18).
STALE_APK_SIZES = frozenset({1810063})


def sidecar_path(apk_path: Path) -> Path:
    return apk_path.with_name(apk_path.name + ".versioncode")


def write_version_sidecar(apk_path: Path, version_code: int) -> None:
    try:
        sidecar_path(apk_path).write_text(str(int(version_code)), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write APK version sidecar for %s", apk_path)


def read_sidecar_version_code(apk_path: Path) -> int | None:
    path = sidecar_path(apk_path)
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_axml_version_code(manifest: bytes) -> int | None:
    """Parse binary AndroidManifest for android:versionCode."""
    if len(manifest) < 16:
        return None
    # Chunk header: type(u16) header_size(u16) size(u32)
    try:
        # String pool is usually the second chunk.
        offset = 8
        typ, header_size, chunk_size = struct.unpack_from("<HHI", manifest, 0)
        if typ != 0x0003:  # RES_XML_TYPE
            # Some tools wrap differently; still try string pool scan below.
            pass
        # Walk chunks looking for RES_XML_TYPE_START_ELEMENT (0x0102) attributes.
        pos = 8
        end = len(manifest)
        best: int | None = None
        while pos + 8 <= end:
            c_typ, c_header, c_size = struct.unpack_from("<HHI", manifest, pos)
            if c_size < 8 or pos + c_size > end:
                break
            if c_typ == 0x0102:  # start element
                # After header: line, comment, ns, name, attrStart, attrSize, attrCount, idIndex...
                base = pos + c_header
                if base + 20 <= pos + c_size:
                    attr_start, attr_size, attr_count = struct.unpack_from(
                        "<HHH", manifest, base + 12
                    )
                    attrs_at = pos + attr_start
                    for i in range(attr_count):
                        ap = attrs_at + i * max(attr_size, 20)
                        if ap + 20 > pos + c_size:
                            break
                        # ns, name, raw, size, type, data
                        _ns, _name, _raw, _sz, type_byte, data = struct.unpack_from(
                            "<IIIHHI", manifest, ap
                        )
                        value_type = (type_byte >> 24) & 0xFF
                        # TYPE_INT_DEC / TYPE_INT_HEX
                        if value_type in (0x10, 0x11) and 1 <= data <= 10_000_000:
                            # Prefer small app versionCodes over resource ids.
                            if data < 10_000 and (best is None or data > best):
                                best = data
            pos += c_size
        return best
    except Exception:
        logger.debug("AXML version parse failed", exc_info=True)
        return None


def read_apk_version_code(apk_path: Path) -> int | None:
    """Return versionCode if known; None if unreadable."""
    if not apk_path.is_file():
        return None
    side = read_sidecar_version_code(apk_path)
    if side is not None:
        return side
    try:
        with zipfile.ZipFile(apk_path) as zf:
            manifest = zf.read("AndroidManifest.xml")
    except Exception:
        return None
    return _read_axml_version_code(manifest)


def apk_meets_min(apk_path: Path, min_code: int) -> bool:
    if not apk_path.is_file() or apk_path.stat().st_size <= 1024:
        return False
    if apk_path.stat().st_size in STALE_APK_SIZES:
        return False
    code = read_apk_version_code(apk_path)
    if code is None:
        # Unreadable and not denylisted size: allow, but prefer sidecar in builds.
        return True
    return code >= int(min_code)
