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


def _parse_windows_xp(cache: bytes) -> AppCompatCacheParseResult:
    header_size = 400
    entry_size = 552
    if len(cache) < header_size:
        raise AppCompatCacheParseError(
            f"Windows XP header requires {header_size} bytes, found {len(cache)}"
        )

    allocated_count = _read_uint(cache, 4, 4, "allocated entry count")
    if allocated_count > 96:
        raise AppCompatCacheParseError(
            f"Windows XP allocated entry count {allocated_count} exceeds 96"
        )
    entries_end = header_size + allocated_count * entry_size
    if entries_end > len(cache):
        raise AppCompatCacheParseError(
            f"Windows XP entry array ends at {entries_end}, cache ends at {len(cache)}"
        )

    diagnostics: list[str] = []
    trailing_bytes = len(cache) - entries_end
    if trailing_bytes:
        byte_label = "byte" if trailing_bytes == 1 else "bytes"
        diagnostics.append(
            f"Windows XP entry array ends at {entries_end}, cache has "
            f"{trailing_bytes} trailing {byte_label}"
        )
    lru_count = _read_uint(cache, 8, 4, "LRU entry count")
    if lru_count > allocated_count:
        raise AppCompatCacheParseError(
            f"Windows XP LRU entry count {lru_count} exceeds "
            f"{allocated_count} allocated slots"
        )

    active_indexes: list[int] = []
    seen_indexes: set[int] = set()
    for lru_position in range(lru_count):
        active_index = _read_uint(
            cache,
            16 + lru_position * 4,
            4,
            "LRU index",
        )
        if active_index >= allocated_count:
            raise AppCompatCacheParseError(
                f"Windows XP LRU index {active_index} is outside "
                f"{allocated_count} allocated slots"
            )
        if active_index in seen_indexes:
            raise AppCompatCacheParseError(
                f"Windows XP LRU index {active_index} is duplicated"
            )
        seen_indexes.add(active_index)
        active_indexes.append(active_index)

    entries: list[AppCompatCacheEntry] = []
    for entry_index in sorted(active_indexes):
        entry_offset = header_size + entry_index * entry_size
        path_field = cache[entry_offset : entry_offset + 528]
        terminator = None
        for path_offset in range(0, 528, 2):
            if path_field[path_offset : path_offset + 2] == b"\x00\x00":
                terminator = path_offset
                break
        if terminator is None:
            diagnostics.append(
                f"Windows XP entry {entry_index}: missing UTF-16 terminator"
            )
            continue
        try:
            path = _decode_utf16(path_field, 0, terminator, "path")
        except AppCompatCacheParseError as exception:
            diagnostics.append(f"Windows XP entry {entry_index}: {exception}")
            continue

        raw_filetime = _read_uint(
            cache,
            entry_offset + 528,
            8,
            "modification FILETIME",
        )
        modification_date, date_diagnostics = _decode_filetime(
            raw_filetime,
            "Windows XP",
            entry_index,
        )
        diagnostics.extend(date_diagnostics)
        entries.append(AppCompatCacheEntry(path, modification_date))

    return AppCompatCacheParseResult(tuple(entries), tuple(diagnostics))


@dataclass(frozen=True)
class _FixedLayout:
    name: str
    entry_size: int
    path_offset_field: int
    path_offset_size: int
    modification_time_field: int
    requires_padding: bool
    data_size_field: int | None = None
    data_offset_field: int | None = None
    data_field_size: int = 0


def _fixed_layout_score(
    cache: bytes,
    header_size: int,
    cached_count: int,
    layout: _FixedLayout,
) -> int:
    table_end = header_size + cached_count * layout.entry_size
    if table_end > len(cache):
        return -1

    score = 0
    for entry_index in range(cached_count):
        entry_offset = header_size + entry_index * layout.entry_size
        if layout.requires_padding and _read_uint(
            cache,
            entry_offset + 4,
            4,
            "alignment padding",
        ) != 0:
            continue
        path_size = _read_uint(cache, entry_offset, 2, "path size")
        maximum_path_size = _read_uint(cache, entry_offset + 2, 2, "maximum path size")
        path_offset = _read_uint(
            cache,
            entry_offset + layout.path_offset_field,
            layout.path_offset_size,
            "path offset",
        )
        if path_size == 0 or path_size % 2 or maximum_path_size != path_size + 2:
            continue
        if path_offset < table_end or path_offset + maximum_path_size > len(cache):
            continue
        if cache[path_offset + path_size : path_offset + maximum_path_size] != b"\x00\x00":
            continue
        score += 1
    return score


def _select_fixed_layout(
    cache: bytes,
    format_name: str,
    header_size: int,
    cached_count: int,
    layouts: tuple[_FixedLayout, _FixedLayout],
) -> _FixedLayout:
    scores = [
        (_fixed_layout_score(cache, header_size, cached_count, layout), layout)
        for layout in layouts
    ]
    best_score = max(score for score, _ in scores)
    best_layouts = [layout for score, layout in scores if score == best_score]
    if best_score <= 0 or len(best_layouts) != 1:
        labels = ", ".join(f"{layout.name}={score}" for score, layout in scores)
        raise AppCompatCacheParseError(
            f"{format_name}: unable to determine fixed-entry architecture ({labels})"
        )
    return best_layouts[0]


def _parse_fixed_cache(
    cache: bytes,
    format_name: str,
    header_size: int,
    maximum_entries: int,
    layouts: tuple[_FixedLayout, _FixedLayout],
) -> AppCompatCacheParseResult:
    if len(cache) < header_size:
        raise AppCompatCacheParseError(
            f"{format_name} header requires {header_size} bytes, found {len(cache)}"
        )
    cached_count = _read_uint(cache, 4, 4, "cached entry count")
    if cached_count > maximum_entries:
        raise AppCompatCacheParseError(
            f"{format_name} cached entry count {cached_count} exceeds {maximum_entries}"
        )
    if cached_count == 0:
        diagnostics = () if len(cache) == header_size else (
            f"{format_name} empty header has {len(cache) - header_size} trailing bytes",
        )
        return AppCompatCacheParseResult((), diagnostics)

    layout = _select_fixed_layout(
        cache,
        format_name,
        header_size,
        cached_count,
        layouts,
    )
    table_end = header_size + cached_count * layout.entry_size
    entries: list[AppCompatCacheEntry] = []
    diagnostics: list[str] = []
    for entry_index in range(cached_count):
        entry_offset = header_size + entry_index * layout.entry_size
        path_size = _read_uint(cache, entry_offset, 2, "path size")
        maximum_path_size = _read_uint(cache, entry_offset + 2, 2, "maximum path size")
        path_offset = _read_uint(
            cache,
            entry_offset + layout.path_offset_field,
            layout.path_offset_size,
            "path offset",
        )
        if (
            layout.data_size_field is not None
            and layout.data_offset_field is not None
        ):
            data_size = _read_uint(
                cache,
                entry_offset + layout.data_size_field,
                layout.data_field_size,
                "data size",
            )
            data_offset = _read_uint(
                cache,
                entry_offset + layout.data_offset_field,
                layout.data_field_size,
                "data offset",
            )
            data_end = data_offset + data_size
            if data_size and data_end > len(cache):
                diagnostics.append(
                    f"{format_name} {layout.name} entry {entry_index}: data range "
                    f"{data_offset}:{data_end} extends outside {len(cache)} bytes"
                )
        if (
            path_size == 0
            or path_size % 2
            or maximum_path_size != path_size + 2
            or path_offset < table_end
            or path_offset + maximum_path_size > len(cache)
            or cache[path_offset + path_size : path_offset + maximum_path_size]
            != b"\x00\x00"
        ):
            diagnostics.append(
                f"{format_name} {layout.name} entry {entry_index}: invalid path range"
            )
            continue
        try:
            path = _decode_utf16(cache, path_offset, path_size, "path")
        except AppCompatCacheParseError as exception:
            diagnostics.append(
                f"{format_name} {layout.name} entry {entry_index}: {exception}"
            )
            continue

        raw_filetime = _read_uint(
            cache,
            entry_offset + layout.modification_time_field,
            8,
            "modification FILETIME",
        )
        modification_date, date_diagnostics = _decode_filetime(
            raw_filetime,
            f"{format_name} {layout.name}",
            entry_index,
        )
        diagnostics.extend(date_diagnostics)
        entries.append(AppCompatCacheEntry(path, modification_date))

    return AppCompatCacheParseResult(tuple(entries), tuple(diagnostics))


NT5_LAYOUTS = (
    _FixedLayout("x86", 24, 4, 4, 8, False),
    _FixedLayout("x64", 32, 8, 8, 16, True),
)

WINDOWS_7_LAYOUTS = (
    _FixedLayout(
        "x86",
        32,
        4,
        4,
        8,
        False,
        data_size_field=24,
        data_offset_field=28,
        data_field_size=4,
    ),
    _FixedLayout(
        "x64",
        48,
        8,
        8,
        16,
        True,
        data_size_field=32,
        data_offset_field=40,
        data_field_size=8,
    ),
)


def _parse_windows_8_body(
    body: bytes,
    entry_index: int,
    version: str,
) -> tuple[AppCompatCacheEntry, list[str]]:
    path_size = _read_uint(body, 0, 2, "path size")
    path = _decode_utf16(body, 2, path_size, "path")
    package_size_offset = 2 + path_size
    package_size = _read_uint(body, package_size_offset, 2, "package size")
    flags_offset = package_size_offset + 2 + package_size
    if flags_offset + 8 > len(body):
        raise AppCompatCacheParseError("flags extend outside the entry body")
    flag1 = body[flags_offset : flags_offset + 4]
    flag2 = body[flags_offset + 4 : flags_offset + 8]
    filetime_offset = flags_offset + 8
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
        f"Windows {version}",
        entry_index,
    )
    return AppCompatCacheEntry(path, modification_date, flag1, flag2), diagnostics


def _parse_windows_8_0_body(
    body: bytes,
    entry_index: int,
) -> tuple[AppCompatCacheEntry, list[str]]:
    return _parse_windows_8_body(body, entry_index, "8.0")


def _parse_windows_8_1_body(
    body: bytes,
    entry_index: int,
) -> tuple[AppCompatCacheEntry, list[str]]:
    return _parse_windows_8_body(body, entry_index, "8.1")


def _parse_windows_8(cache: bytes, marker: bytes) -> AppCompatCacheParseResult:
    if marker == b"00ts":
        format_name = "Windows 8.0"
        body_parser = _parse_windows_8_0_body
    else:
        format_name = "Windows 8.1"
        body_parser = _parse_windows_8_1_body
    result, _ = _parse_variable_entries(
        cache,
        128,
        marker,
        format_name,
        body_parser,
    )
    return result


def parse_appcompat_cache(cache: bytes) -> AppCompatCacheParseResult:
    if not isinstance(cache, bytes):
        raise AppCompatCacheParseError("AppCompatCache value is not bytes")
    if len(cache) < 4:
        raise AppCompatCacheParseError(
            f"AppCompatCache value is too short: {len(cache)} bytes"
        )

    signature = _read_uint(cache, 0, 4, "signature")
    if signature == 0xDEADBEEF:
        return _parse_windows_xp(cache)
    if signature == 0xBADC0FFE:
        return _parse_fixed_cache(
            cache,
            "Windows 2003/Vista",
            8,
            1024,
            NT5_LAYOUTS,
        )
    if signature == 0xBADC0FEE:
        return _parse_fixed_cache(
            cache,
            "Windows 7",
            128,
            1024,
            WINDOWS_7_LAYOUTS,
        )
    if signature in (48, 52):
        if len(cache) == signature:
            return _parse_windows_10(cache, signature)
        if len(cache) < signature + 4 or cache[signature : signature + 4] != b"10ts":
            raise AppCompatCacheParseError(
                f"Windows 10 header size {signature} is not followed by 10ts"
            )
        return _parse_windows_10(cache, signature)
    if len(cache) >= 132 and cache[128:132] in (b"00ts", b"10ts"):
        return _parse_windows_8(cache, cache[128:132])
    if signature == 128 and len(cache) == 128:
        return AppCompatCacheParseResult((), ())
    if signature == 128:
        raise AppCompatCacheParseError(
            "Windows 8 header is not followed by a supported entry marker"
        )

    raise UnsupportedAppCompatCacheFormat(
        f"unsupported AppCompatCache signature 0x{signature:08x}"
    )
