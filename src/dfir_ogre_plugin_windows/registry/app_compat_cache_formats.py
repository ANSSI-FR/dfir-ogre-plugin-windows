from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from dfir_ogre_plugin_windows.common import filetime_to_utc


BodyParser = Callable[[bytes, int], tuple["AppCompatCacheEntry", list[str]]]


class AppCompatCacheParseError(ValueError):
    """Raised when a cache header or boundary cannot be parsed safely."""


class UnsupportedAppCompatCacheFormat(AppCompatCacheParseError):
    """Raised when a cache value has no supported format discriminator."""


@dataclass(frozen=True)
class AppCompatCacheEntry:
    path: str
    modification_date: datetime | None
    flag1: bytes | None = None
    flag2: bytes | None = None


@dataclass(frozen=True)
class AppCompatCacheParseResult:
    entries: tuple[AppCompatCacheEntry, ...]
    diagnostics: tuple[str, ...]


def _read_uint(data: bytes, offset: int, size: int, field: str) -> int:
    end = offset + size
    if offset < 0 or end > len(data):
        raise AppCompatCacheParseError(
            f"{field} at offset {offset} extends outside {len(data)} bytes"
        )
    return int.from_bytes(data[offset:end], byteorder="little")


def _decode_utf16(data: bytes, offset: int, size: int, field: str) -> str:
    if size == 0 or size % 2:
        raise AppCompatCacheParseError(f"{field} has invalid byte size {size}")
    end = offset + size
    if offset < 0 or end > len(data):
        raise AppCompatCacheParseError(
            f"{field} range {offset}:{end} extends outside {len(data)} bytes"
        )
    try:
        return data[offset:end].decode("utf-16-le")
    except UnicodeDecodeError as exception:
        raise AppCompatCacheParseError(
            f"{field} is not valid UTF-16LE: {exception}"
        ) from exception


def _decode_filetime(
    raw_filetime: int,
    format_name: str,
    entry_index: int,
) -> tuple[datetime | None, list[str]]:
    try:
        return filetime_to_utc(raw_filetime), []
    except (OSError, OverflowError, ValueError) as exception:
        return None, [
            f"{format_name} entry {entry_index}: invalid FILETIME "
            f"0x{raw_filetime:016x}: {exception}"
        ]


def _parse_variable_entries(
    cache: bytes,
    header_size: int,
    marker: bytes,
    format_name: str,
    body_parser: BodyParser,
) -> tuple[AppCompatCacheParseResult, int]:
    entries: list[AppCompatCacheEntry] = []
    diagnostics: list[str] = []
    offset = header_size
    seen_entries = 0

    while offset < len(cache):
        if offset + 12 > len(cache):
            diagnostics.append(
                f"{format_name} entry {seen_entries}: truncated 12-byte entry header"
            )
            break
        if cache[offset : offset + 4] != marker:
            actual = cache[offset : offset + 4].hex()
            diagnostics.append(
                f"{format_name} entry {seen_entries}: expected marker "
                f"{marker!r}, found 0x{actual}"
            )
            break

        body_size = _read_uint(cache, offset + 8, 4, "entry body size")
        body_start = offset + 12
        body_end = body_start + body_size
        if body_end > len(cache):
            diagnostics.append(
                f"{format_name} entry {seen_entries}: body range "
                f"{body_start}:{body_end} extends outside the cache"
            )
            break

        body = cache[body_start:body_end]
        try:
            entry, entry_diagnostics = body_parser(body, seen_entries)
        except AppCompatCacheParseError as exception:
            diagnostics.append(f"{format_name} entry {seen_entries}: {exception}")
        else:
            entries.append(entry)
            diagnostics.extend(entry_diagnostics)

        seen_entries += 1
        offset = body_end

    return AppCompatCacheParseResult(tuple(entries), tuple(diagnostics)), seen_entries


def _parse_windows_10_body(
    body: bytes,
    entry_index: int,
) -> tuple[AppCompatCacheEntry, list[str]]:
    path_size = _read_uint(body, 0, 2, "path size")
    path = _decode_utf16(body, 2, path_size, "path")
    filetime_offset = 2 + path_size
    raw_filetime = _read_uint(body, filetime_offset, 8, "modification FILETIME")
    data_size_offset = filetime_offset + 8
    data_size = _read_uint(body, data_size_offset, 4, "data size")
    expected_size = data_size_offset + 4 + data_size
    if expected_size != len(body):
        raise AppCompatCacheParseError(
            f"declared data ends at {expected_size}, body ends at {len(body)}"
        )
    modification_date, diagnostics = _decode_filetime(
        raw_filetime,
        "Windows 10",
        entry_index,
    )
    return AppCompatCacheEntry(path, modification_date), diagnostics


def _parse_windows_10(cache: bytes, header_size: int) -> AppCompatCacheParseResult:
    result, seen_entries = _parse_variable_entries(
        cache,
        header_size,
        b"10ts",
        "Windows 10",
        _parse_windows_10_body,
    )
    count_offset = 36 if header_size == 48 else 40
    declared_count = _read_uint(cache, count_offset, 4, "cached entry count")
    diagnostics = list(result.diagnostics)
    if declared_count != seen_entries:
        diagnostics.append(
            f"Windows 10 header declares {declared_count} entries "
            f"but contains {seen_entries}"
        )
    return AppCompatCacheParseResult(result.entries, tuple(diagnostics))


def parse_appcompat_cache(cache: bytes) -> AppCompatCacheParseResult:
    if not isinstance(cache, bytes):
        raise AppCompatCacheParseError("AppCompatCache value is not bytes")
    if len(cache) < 4:
        raise AppCompatCacheParseError(
            f"AppCompatCache value is too short: {len(cache)} bytes"
        )

    signature = _read_uint(cache, 0, 4, "signature")
    if signature in (48, 52):
        if len(cache) == signature:
            return AppCompatCacheParseResult((), ())
        if len(cache) < signature + 4 or cache[signature : signature + 4] != b"10ts":
            raise AppCompatCacheParseError(
                f"Windows 10 header size {signature} is not followed by 10ts"
            )
        return _parse_windows_10(cache, signature)
    if signature == 128 and len(cache) == 128:
        return AppCompatCacheParseResult((), ())

    raise UnsupportedAppCompatCacheFormat(
        f"unsupported AppCompatCache signature 0x{signature:08x}"
    )
