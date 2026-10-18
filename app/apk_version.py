# -*- coding: utf-8 -*-
"""Read the actual Android APK version from its binary manifest."""
from __future__ import annotations

import logging
import struct
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Known broken artifact once served as "latest" (1.5.2 / versionCode 18).
STALE_APK_SIZES = frozenset({1810063})
ANDROID_NS = "http://schemas.android.com/apk/res/android"


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


def _length8(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first & 0x80:
        return ((first & 0x7F) << 8) | data[offset], offset + 1
    return first, offset


def _length16(data: bytes, offset: int) -> tuple[int, int]:
    first = struct.unpack_from("<H", data, offset)[0]
    offset += 2
    if first & 0x8000:
        second = struct.unpack_from("<H", data, offset)[0]
        return ((first & 0x7FFF) << 16) | second, offset + 2
    return first, offset


def _string_pool(data: bytes, pos: int, size: int, header_size: int) -> list[str]:
    if header_size < 28:
        raise ValueError("Invalid Android string pool header")
    count, _styles, flags, strings_start, _styles_start = struct.unpack_from(
        "<IIIII", data, pos + 8
    )
    offsets_at = pos + header_size
    if count > 100_000 or offsets_at + count * 4 > pos + size:
        raise ValueError("Invalid Android string pool count")
    strings: list[str] = []
    for index in range(count):
        relative = struct.unpack_from("<I", data, offsets_at + index * 4)[0]
        at = pos + strings_start + relative
        if at >= pos + size:
            raise ValueError("Android string offset outside pool")
        if flags & 0x100:  # UTF-8
            _chars, at = _length8(data, at)
            byte_count, at = _length8(data, at)
            value = data[at : at + byte_count].decode("utf-8")
        else:  # UTF-16LE
            char_count, at = _length16(data, at)
            value = data[at : at + char_count * 2].decode("utf-16le")
        strings.append(value)
    return strings


def _read_axml_version(manifest: bytes) -> tuple[int, str] | None:
    """Read versionCode and versionName from the manifest root element."""
    try:
        root_type, root_header, root_size = struct.unpack_from("<HHI", manifest)
        if root_type != 0x0003 or root_header < 8 or root_size > len(manifest):
            return None
        strings: list[str] = []
        pos = root_header
        while pos + 8 <= root_size:
            kind, header_size, chunk_size = struct.unpack_from("<HHI", manifest, pos)
            if header_size < 8 or chunk_size < header_size or pos + chunk_size > root_size:
                return None
            if kind == 0x0001:
                strings = _string_pool(manifest, pos, chunk_size, header_size)
            elif kind == 0x0102 and strings:  # RES_XML_TYPE_START_ELEMENT
                base = pos + header_size
                _namespace, name, attr_start, attr_size, attr_count, *_ = struct.unpack_from(
                    "<IIHHHHHH", manifest, base
                )
                if name >= len(strings) or strings[name] != "manifest":
                    pos += chunk_size
                    continue
                attrs_at = base + attr_start
                if attr_size < 20 or attrs_at + attr_count * attr_size > pos + chunk_size:
                    return None
                code: int | None = None
                version_name: str | None = None
                for index in range(attr_count):
                    attr_ns, attr_name, raw, _value_size, _zero, value_type, value = (
                        struct.unpack_from("<IIIHBBI", manifest, attrs_at + index * attr_size)
                    )
                    if attr_ns >= len(strings) or strings[attr_ns] != ANDROID_NS:
                        continue
                    if attr_name >= len(strings):
                        continue
                    if strings[attr_name] == "versionCode" and value_type in (0x10, 0x11):
                        code = value
                    elif strings[attr_name] == "versionName":
                        string_index = value if value_type == 0x03 else raw
                        if string_index < len(strings):
                            version_name = strings[string_index]
                if code is not None and code > 0 and version_name:
                    return code, version_name
                return None
            pos += chunk_size
    except (IndexError, UnicodeError, ValueError, struct.error):
        logger.debug("Android binary manifest parse failed", exc_info=True)
    return None


def read_apk_version(apk_path: Path) -> tuple[int, str] | None:
    """Return the package version; a mismatched sidecar invalidates it."""
    if not apk_path.is_file():
        return None
    try:
        with zipfile.ZipFile(apk_path) as zf:
            actual = _read_axml_version(zf.read("AndroidManifest.xml"))
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    if actual is None:
        return None
    sidecar = read_sidecar_version_code(apk_path)
    if sidecar is not None and sidecar != actual[0]:
        logger.error(
            "APK version sidecar mismatch: %s has %s but manifest has %s",
            apk_path,
            sidecar,
            actual[0],
        )
        return None
    return actual


def read_apk_version_code(apk_path: Path) -> int | None:
    version = read_apk_version(apk_path)
    return version[0] if version else None


def apk_meets_min(apk_path: Path, min_code: int) -> bool:
    if not apk_path.is_file() or apk_path.stat().st_size <= 1024:
        return False
    if apk_path.stat().st_size in STALE_APK_SIZES:
        return False
    code = read_apk_version_code(apk_path)
    return code is not None and code >= int(min_code)
