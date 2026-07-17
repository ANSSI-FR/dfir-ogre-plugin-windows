# AppCompatCache Multi-Version Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse AppCompatCache values from Windows XP through Windows 10, preserve the existing record schema, and report unsupported or malformed data without losing safely recoverable entries.

**Architecture:** Move binary decoding into a pure `app_compat_cache_formats.py` module with immutable parsed-entry/result types, bounded format-specific readers, and typed fatal errors. Keep `app_compat_cache.py` responsible for registry discovery, warning/`RunReport` diagnostics, and conversion of parsed entries into the existing OGRE records.

**Tech Stack:** Python 3.10+, standard-library `dataclasses` and integer decoding, `dfir_ogre_common`, existing `filetime_to_utc`, `unittest`, and `unittest.mock`; no new dependency.

## Global Constraints

- Support the documented Windows XP through Windows 10 layouts, including x86 and x64 fixed layouts.
- Search both `Session Manager\AppCompatibility` and `Session Manager\AppCompatCache` in every control set.
- Emit only the existing fields: `index`, `path`, `modification_date`, Windows 8.x `flag1`/`flag2`, and registry metadata.
- Do not change `configuration/registry/app_compat_cache.xml`.
- Keep paths as stored, removing only a format-defined UTF-16 terminator.
- Log a warning and add the same diagnostic to `RunReport` for unsupported or malformed input.
- Continue after entry damage only when the next boundary is trustworthy.
- Preserve existing Windows 10 output order and record counts.
- Leave the unrelated `uv.lock` working-tree change untouched and uncommitted.

---

## File Structure

- Create `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`: pure binary format detection, bounded decoding, common parsed-entry model, recoverable diagnostics, and fatal parse exceptions.
- Modify `src/dfir_ogre_plugin_windows/registry/app_compat_cache.py`: registry-key discovery, parser invocation, warning/`RunReport` plumbing, and unchanged record emission.
- Create `tests/hive/test_app_compat_cache_formats.py`: synthetic byte-level tests for every supported layout and corruption boundary.
- Modify `tests/hive/test_app_compat_cache.py`: discovery, diagnostics, schema compatibility, and existing real-hive regression coverage.

### Task 1: Pure Parser Core and Windows 10 Regression

**Files:**
- Create: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`
- Create: `tests/hive/test_app_compat_cache_formats.py`

**Interfaces:**
- Produces: `AppCompatCacheEntry(path: str, modification_date: datetime | None, flag1: bytes | None, flag2: bytes | None)`.
- Produces: `AppCompatCacheParseResult(entries: tuple[AppCompatCacheEntry, ...], diagnostics: tuple[str, ...])`.
- Produces: `AppCompatCacheParseError`, `UnsupportedAppCompatCacheFormat`, and `parse_appcompat_cache(cache: bytes) -> AppCompatCacheParseResult`.

- [ ] **Step 1: Write failing Windows 10 parser tests**

Create `tests/hive/test_app_compat_cache_formats.py` with the following foundation and tests:

```python
import struct
from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_plugin_windows.registry.app_compat_cache_formats import (
    AppCompatCacheParseError,
    UnsupportedAppCompatCacheFormat,
    parse_appcompat_cache,
)


FILETIME = 132224078450000000
EXPECTED_DATE = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def variable_entry(marker: bytes, body: bytes) -> bytes:
    return marker + bytes(4) + struct.pack("<I", len(body)) + body


def windows_10_entry(
    path: str,
    filetime: int = FILETIME,
    data: bytes = b"",
) -> bytes:
    encoded_path = path.encode("utf-16-le")
    body = (
        struct.pack("<H", len(encoded_path))
        + encoded_path
        + struct.pack("<QI", filetime, len(data))
        + data
    )
    return variable_entry(b"10ts", body)


def windows_10_cache(
    entries: list[bytes],
    header_size: int = 52,
    declared_count: int | None = None,
) -> bytes:
    header = bytearray(header_size)
    struct.pack_into("<I", header, 0, header_size)
    count_offset = 36 if header_size == 48 else 40
    struct.pack_into(
        "<I",
        header,
        count_offset,
        len(entries) if declared_count is None else declared_count,
    )
    return bytes(header) + b"".join(entries)


class AppCompatCacheFormats(TestCase):
    def test_windows_10_headers(self):
        for header_size in (48, 52):
            with self.subTest(header_size=header_size):
                result = parse_appcompat_cache(
                    windows_10_cache(
                        [windows_10_entry(r"C:\Windows\System32\cmd.exe")],
                        header_size=header_size,
                    )
                )

                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(
                    result.entries[0].path,
                    r"C:\Windows\System32\cmd.exe",
                )
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertIsNone(result.entries[0].flag1)
                self.assertIsNone(result.entries[0].flag2)

    def test_windows_10_invalid_filetime_preserves_path(self):
        result = parse_appcompat_cache(
            windows_10_cache(
                [windows_10_entry(r"C:\Evidence\invalid-time.exe", 0xFFFFFFFFFFFFFFFF)]
            )
        )

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].path, r"C:\Evidence\invalid-time.exe")
        self.assertIsNone(result.entries[0].modification_date)
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid FILETIME", result.diagnostics[0])

    def test_windows_10_stops_at_unbounded_truncation(self):
        valid = windows_10_entry(r"C:\Evidence\valid.exe")
        truncated = b"10ts" + bytes(4) + struct.pack("<I", 4096)
        result = parse_appcompat_cache(windows_10_cache([valid, truncated]))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\Evidence\valid.exe"])
        self.assertEqual(len(result.diagnostics), 2)
        self.assertIn("outside the cache", result.diagnostics[0])
        self.assertIn("declares 2 entries but contains 1", result.diagnostics[1])

    def test_header_only_caches_are_empty(self):
        for header_size in (48, 52, 128):
            with self.subTest(header_size=header_size):
                header = bytearray(header_size)
                struct.pack_into("<I", header, 0, header_size)
                result = parse_appcompat_cache(bytes(header))
                self.assertEqual(result.entries, ())
                self.assertEqual(result.diagnostics, ())

    def test_unsupported_signature_is_explicit(self):
        with self.assertRaisesRegex(
            UnsupportedAppCompatCacheFormat,
            "0x12345678",
        ):
            parse_appcompat_cache(struct.pack("<I", 0x12345678) + bytes(60))

    def test_short_value_is_malformed(self):
        with self.assertRaisesRegex(AppCompatCacheParseError, "too short: 3 bytes"):
            parse_appcompat_cache(b"\x01\x02\x03")

    def test_invalid_utf16_body_is_reported(self):
        body = (
            struct.pack("<H", 2)
            + b"\x00\xd8"
            + struct.pack("<QI", FILETIME, 0)
        )
        result = parse_appcompat_cache(
            windows_10_cache([variable_entry(b"10ts", body)])
        )

        self.assertEqual(result.entries, ())
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("not valid UTF-16LE", result.diagnostics[0])
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: test collection fails with `ModuleNotFoundError: No module named 'dfir_ogre_plugin_windows.registry.app_compat_cache_formats'`.

- [ ] **Step 3: Implement the pure model, bounded readers, and Windows 10 parser**

Create `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py` with these definitions:

```python
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
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: `Ran 7 tests` followed by `OK`.

- [ ] **Step 5: Commit the parser core**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py tests/hive/test_app_compat_cache_formats.py
git commit -m "Add bounded Windows 10 AppCompatCache parser"
```

### Task 2: Windows XP Fixed Layout

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`
- Modify: `tests/hive/test_app_compat_cache_formats.py`

**Interfaces:**
- Consumes: `AppCompatCacheParseResult`, `_decode_utf16`, `_decode_filetime`, and `_read_uint` from Task 1.
- Extends: `parse_appcompat_cache()` with `0xdeadbeef` dispatch.

- [ ] **Step 1: Add failing XP parsing and recovery tests**

Add this builder above the test class:

```python
def windows_xp_cache(paths: list[str]) -> bytes:
    header = bytearray(400)
    struct.pack_into("<IIII", header, 0, 0xDEADBEEF, len(paths), len(paths), 0)
    for index in range(len(paths)):
        struct.pack_into("<I", header, 16 + index * 4, index)

    entries = []
    for path in paths:
        encoded_path = path.encode("utf-16-le") + b"\x00\x00"
        path_field = encoded_path + bytes(528 - len(encoded_path))
        entries.append(path_field + struct.pack("<QQQ", FILETIME, 1234, FILETIME))
    return bytes(header) + b"".join(entries)
```

Add these tests to `AppCompatCacheFormats`:

```python
    def test_windows_xp(self):
        result = parse_appcompat_cache(
            windows_xp_cache([r"\??\C:\Windows\System32\calc.exe"])
        )

        self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(
            result.entries[0].path,
            r"\??\C:\Windows\System32\calc.exe",
        )
        self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)

    def test_windows_xp_skips_bad_fixed_entry_and_continues(self):
        cache = bytearray(windows_xp_cache([r"C:\bad.exe", r"C:\good.exe"]))
        cache[400:928] = b"A" * 528
        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\good.exe"])
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("missing UTF-16 terminator", result.diagnostics[0])
```

- [ ] **Step 2: Run the XP tests and verify unsupported-format failures**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: the two XP tests fail with `UnsupportedAppCompatCacheFormat` containing `0xdeadbeef`.

- [ ] **Step 3: Add the XP parser and dispatcher branch**

Add this function before `parse_appcompat_cache`:

```python
def _parse_windows_xp(cache: bytes) -> AppCompatCacheParseResult:
    header_size = 400
    entry_size = 552
    if len(cache) < header_size:
        raise AppCompatCacheParseError(
            f"Windows XP header requires {header_size} bytes, found {len(cache)}"
        )

    cached_count = _read_uint(cache, 4, 4, "cached entry count")
    if cached_count > 96:
        raise AppCompatCacheParseError(
            f"Windows XP cached entry count {cached_count} exceeds 96"
        )
    entries_end = header_size + cached_count * entry_size
    if entries_end > len(cache):
        raise AppCompatCacheParseError(
            f"Windows XP entry array ends at {entries_end}, cache ends at {len(cache)}"
        )

    diagnostics: list[str] = []
    lru_count = _read_uint(cache, 8, 4, "LRU entry count")
    if lru_count > 96:
        diagnostics.append(f"Windows XP LRU entry count {lru_count} exceeds 96")
    else:
        for lru_index in range(lru_count):
            cached_index = _read_uint(cache, 16 + lru_index * 4, 4, "LRU index")
            if cached_index >= cached_count:
                diagnostics.append(
                    f"Windows XP LRU index {cached_index} is outside "
                    f"{cached_count} cached entries"
                )

    entries: list[AppCompatCacheEntry] = []
    for entry_index in range(cached_count):
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
```

Insert this branch immediately after reading `signature` in `parse_appcompat_cache`:

```python
    if signature == 0xDEADBEEF:
        return _parse_windows_xp(cache)
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: `Ran 9 tests` followed by `OK`.

- [ ] **Step 5: Commit XP support**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py tests/hive/test_app_compat_cache_formats.py
git commit -m "Support Windows XP AppCompatCache entries"
```

### Task 3: Server 2003, Vista, and Windows 7 Fixed Layouts

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`
- Modify: `tests/hive/test_app_compat_cache_formats.py`

**Interfaces:**
- Consumes: the pure parser model and bounded readers from Tasks 1–2.
- Produces: internal `_FixedLayout` candidates and `_parse_fixed_cache()` for `0xbadc0ffe` and `0xbadc0fee`.

- [ ] **Step 1: Add failing x86/x64 fixed-layout tests**

Add this builder above the test class:

```python
def fixed_cache(signature: int, paths: list[str], is_64bit: bool) -> bytes:
    if signature == 0xBADC0FFE:
        header_size = 8
        entry_size = 32 if is_64bit else 24
    else:
        header_size = 128
        entry_size = 48 if is_64bit else 32
    encoded_paths = [path.encode("utf-16-le") for path in paths]
    next_path_offset = header_size + entry_size * len(paths)
    entries = []
    path_data = []

    for encoded_path in encoded_paths:
        if signature == 0xBADC0FFE and is_64bit:
            entry = struct.pack(
                "<HHIQQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                0,
                next_path_offset,
                FILETIME,
                0,
            )
        elif signature == 0xBADC0FFE:
            entry = struct.pack(
                "<HHIQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                next_path_offset,
                FILETIME,
                0,
            )
        elif is_64bit:
            entry = struct.pack(
                "<HHIQQIIQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                0,
                next_path_offset,
                FILETIME,
                2,
                0,
                0,
                0,
            )
        else:
            entry = struct.pack(
                "<HHIQIIII",
                len(encoded_path),
                len(encoded_path) + 2,
                next_path_offset,
                FILETIME,
                2,
                0,
                0,
                0,
            )
        entries.append(entry)
        path_data.append(encoded_path + b"\x00\x00")
        next_path_offset += len(encoded_path) + 2

    header = struct.pack("<II", signature, len(paths)) + bytes(header_size - 8)
    return header + b"".join(entries) + b"".join(path_data)
```

Add this test:

```python
    def test_fixed_layouts(self):
        cases = (
            (0xBADC0FFE, False, "Windows 2003/Vista x86"),
            (0xBADC0FFE, True, "Windows 2003/Vista x64"),
            (0xBADC0FEE, False, "Windows 7 x86"),
            (0xBADC0FEE, True, "Windows 7 x64"),
        )
        for signature, is_64bit, label in cases:
            with self.subTest(label=label):
                path = rf"C:\Evidence\case-{signature:x}-{int(is_64bit)}.exe"
                result = parse_appcompat_cache(
                    fixed_cache(signature, [path], is_64bit)
                )
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].path, path)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertIsNone(result.entries[0].flag1)
                self.assertIsNone(result.entries[0].flag2)

    def test_fixed_layout_skips_bad_path_and_continues(self):
        cache = bytearray(
            fixed_cache(
                0xBADC0FEE,
                [r"C:\Evidence\bad.exe", r"C:\Evidence\good.exe"],
                False,
            )
        )
        struct.pack_into("<I", cache, 128 + 4, len(cache) + 100)
        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\Evidence\good.exe"])
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid path range", result.diagnostics[0])
```

- [ ] **Step 2: Run the tests and verify both signatures are unsupported**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: both fixed-layout tests fail with `UnsupportedAppCompatCacheFormat`.

- [ ] **Step 3: Implement fixed-layout selection and parsing**

Add these definitions before `parse_appcompat_cache`:

```python
@dataclass(frozen=True)
class _FixedLayout:
    name: str
    entry_size: int
    path_offset_field: int
    path_offset_size: int
    modification_time_field: int
    requires_padding: bool


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
            f"unable to determine fixed-entry architecture ({labels})"
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

    layout = _select_fixed_layout(cache, header_size, cached_count, layouts)
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
    _FixedLayout("x86", 32, 4, 4, 8, False),
    _FixedLayout("x64", 48, 8, 8, 16, True),
)
```

Insert these branches in `parse_appcompat_cache` after the XP branch:

```python
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
```

- [ ] **Step 4: Run all pure-parser tests**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: `Ran 11 tests` followed by `OK`.

- [ ] **Step 5: Commit fixed-layout support**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py tests/hive/test_app_compat_cache_formats.py
git commit -m "Support legacy fixed AppCompatCache layouts"
```

### Task 4: Windows 8.0 and Windows 8.1 Variable Layouts

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`
- Modify: `tests/hive/test_app_compat_cache_formats.py`

**Interfaces:**
- Consumes: `_parse_variable_entries()` and the common parsed-entry model.
- Extends: `parse_appcompat_cache()` with `00ts` and `10ts` at byte offset 128.

- [ ] **Step 1: Add failing Windows 8 layout and bounded-recovery tests**

Add these builders above the test class:

```python
def windows_8_entry(
    path: str,
    version: str,
    flag1: bytes,
    flag2: bytes,
    filetime: int = FILETIME,
    data: bytes = b"",
) -> bytes:
    encoded_path = path.encode("utf-16-le")
    unknown = b"\x5a\xa5" if version == "8.1" else b""
    body = (
        struct.pack("<H", len(encoded_path))
        + encoded_path
        + flag1
        + flag2
        + unknown
        + struct.pack("<QI", filetime, len(data))
        + data
    )
    marker = b"00ts" if version == "8.0" else b"10ts"
    return variable_entry(marker, body)


def windows_8_cache(entries: list[bytes], first_dword: int = 128) -> bytes:
    header = bytearray(128)
    struct.pack_into("<I", header, 0, first_dword)
    return bytes(header) + b"".join(entries)
```

Add these tests:

```python
    def test_windows_8_layouts_and_flag_alignment(self):
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        for version in ("8.0", "8.1"):
            with self.subTest(version=version):
                result = parse_appcompat_cache(
                    windows_8_cache(
                        [
                            windows_8_entry(
                                rf"C:\Evidence\windows-{version}.exe",
                                version,
                                flag1,
                                flag2,
                                data=b"forensic-data",
                            )
                        ],
                        first_dword=0,
                    )
                )
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].flag1, flag1)
                self.assertEqual(result.entries[0].flag2, flag2)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)

    def test_windows_8_skips_malformed_bounded_body(self):
        valid_1 = windows_8_entry(
            r"C:\Evidence\first.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )
        malformed = variable_entry(b"10ts", b"\x03\x00abc")
        valid_2 = windows_8_entry(
            r"C:\Evidence\second.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )
        result = parse_appcompat_cache(windows_8_cache([valid_1, malformed, valid_2]))

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\Evidence\first.exe", r"C:\Evidence\second.exe"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid byte size 3", result.diagnostics[0])
```

- [ ] **Step 2: Run the tests and verify Windows 8 values are unsupported**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: both new tests fail with `UnsupportedAppCompatCacheFormat`.

- [ ] **Step 3: Implement distinct Windows 8.0 and 8.1 bodies**

Add these functions before `parse_appcompat_cache`:

```python
def _parse_windows_8_body(
    body: bytes,
    entry_index: int,
    version: str,
) -> tuple[AppCompatCacheEntry, list[str]]:
    path_size = _read_uint(body, 0, 2, "path size")
    path = _decode_utf16(body, 2, path_size, "path")
    flags_offset = 2 + path_size
    if flags_offset + 8 > len(body):
        raise AppCompatCacheParseError("flags extend outside the entry body")
    flag1 = body[flags_offset : flags_offset + 4]
    flag2 = body[flags_offset + 4 : flags_offset + 8]
    filetime_offset = flags_offset + 8
    if version == "8.1":
        _read_uint(body, filetime_offset, 2, "Windows 8.1 unknown field")
        filetime_offset += 2
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
```

Replace `parse_appcompat_cache` with this complete dispatcher:

```python
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
            return AppCompatCacheParseResult((), ())
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
```

- [ ] **Step 4: Run all pure-parser tests**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: `Ran 13 tests` followed by `OK`.

- [ ] **Step 5: Commit Windows 8 support**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py tests/hive/test_app_compat_cache_formats.py
git commit -m "Support Windows 8 AppCompatCache layouts"
```

### Task 5: Registry Discovery, Diagnostics, and Existing Record Output

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache.py`
- Modify: `tests/hive/test_app_compat_cache.py`

**Interfaces:**
- Consumes: `parse_appcompat_cache()` and its result/error types from Tasks 1–4.
- Preserves: `RegAppCompatCache.parse()` and `RegAppCompatCache.parse_key()` public behavior and the XML field contract.

- [ ] **Step 1: Add failing registry discovery and unsupported-format diagnostic tests**

Add this mock import to `tests/hive/test_app_compat_cache.py`:

```python
from unittest.mock import Mock, call
```

Add these tests to `AppCompatCache`:

```python
    def test_cache_key_discovery_includes_xp_and_later_paths(self):
        parser = RegAppCompatCache()
        registry = Mock()
        xp_key = Mock()
        later_key = Mock()
        registry.glob_keys.side_effect = ([xp_key], [later_key])
        report = RunReport()

        keys = list(parser.cache_keys(registry, report))

        self.assertEqual(keys, [xp_key, later_key])
        self.assertEqual(
            registry.glob_keys.call_args_list,
            [
                call(
                    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager"
                    "\\AppCompatibility"
                ),
                call(
                    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager"
                    "\\AppCompatCache"
                ),
            ],
        )
        self.assertEqual(report.num_errors, 0)

    def test_unsupported_format_warns_and_updates_run_report(self):
        parser = RegAppCompatCache()
        key = Mock()
        cache_value = Mock()
        cache_value.data.return_value = struct.pack("<I", 0x12345678) + bytes(60)
        key.value.return_value = cache_value
        key.path = r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        output = Mock()
        report = RunReport()

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ) as logs:
            parser.parse_key(key, output, report)

        self.assertEqual(output.write.call_count, 0)
        self.assertEqual(report.num_errors, 1)
        self.assertIn("0x12345678", report.last_error)
        self.assertIn("0x12345678", logs.output[0])

    def test_cache_key_discovery_continues_after_one_pattern_fails(self):
        parser = RegAppCompatCache()
        registry = Mock()
        later_key = Mock()
        registry.glob_keys.side_effect = (RuntimeError("XP traversal failed"), [later_key])
        report = RunReport()

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ):
            keys = list(parser.cache_keys(registry, report))

        self.assertEqual(keys, [later_key])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("XP traversal failed", report.last_error)

    def test_missing_and_non_byte_values_are_diagnostic(self):
        parser = RegAppCompatCache()
        cases = (("missing", None), ("non-byte", "not bytes"))
        for label, cache_data in cases:
            with self.subTest(label=label):
                key = Mock()
                key.path = rf"HKLM\SYSTEM\ControlSet001\{label}"
                if cache_data is None:
                    key.value.return_value = None
                else:
                    cache_value = Mock()
                    cache_value.data.return_value = cache_data
                    key.value.return_value = cache_value
                output = Mock()
                report = RunReport()

                with self.assertLogs(
                    "dfir_ogre_plugin_windows.registry.app_compat_cache",
                    level="WARNING",
                ):
                    parser.parse_key(key, output, report)

                self.assertEqual(output.write.call_count, 0)
                self.assertEqual(report.num_errors, 1)

    def test_windows_8_record_keeps_existing_schema(self):
        parser = RegAppCompatCache()
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        cache = windows_8_cache(
            [windows_8_entry(r"C:\Evidence\schema.exe", "8.1", flag1, flag2)]
        )
        key = Mock()
        cache_value = Mock()
        cache_value.data.return_value = cache
        key.value.return_value = cache_value
        key.path = r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        key.mtime = None
        key.security_descriptor.to_record.return_value = Record()
        output = Mock()
        report = RunReport()

        parser.parse_key(key, output, report)

        self.assertEqual(report.num_errors, 0)
        self.assertEqual(output.write.call_count, 1)
        record = json.loads(output.write.call_args.args[0].to_string())
        self.assertEqual(
            set(record),
            {
                "index",
                "path",
                "modification_date",
                "flag1",
                "flag2",
                "key_path",
                "key_modif_time",
                "key_security",
            },
        )
        self.assertEqual(record["flag1"], "0x11223344")
        self.assertEqual(record["flag2"], "0xaabbccdd")
```

Add these imports to the test file:

```python
import struct

from dfir_ogre_common import Record, RunReport

from .test_app_compat_cache_formats import windows_8_cache, windows_8_entry
```

- [ ] **Step 2: Run the new plugin tests and verify missing behavior**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache.AppCompatCache.test_cache_key_discovery_includes_xp_and_later_paths \
  tests.hive.test_app_compat_cache.AppCompatCache.test_cache_key_discovery_continues_after_one_pattern_fails \
  tests.hive.test_app_compat_cache.AppCompatCache.test_unsupported_format_warns_and_updates_run_report \
  tests.hive.test_app_compat_cache.AppCompatCache.test_missing_and_non_byte_values_are_diagnostic \
  tests.hive.test_app_compat_cache.AppCompatCache.test_windows_8_record_keeps_existing_schema \
  -q
```

Expected: discovery tests fail because `cache_keys` does not exist, and the
diagnostic/schema tests fail because the current parser silently ignores the
inputs or reads Windows 8.1 fields at the wrong offsets.

- [ ] **Step 3: Replace plugin-local byte scanning with the pure parser**

Replace `src/dfir_ogre_plugin_windows/registry/app_compat_cache.py` with:

```python
import logging
from collections.abc import Iterator

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import value
from dfir_ogre_plugin_windows.registry.app_compat_cache_formats import (
    AppCompatCacheEntry,
    AppCompatCacheParseError,
    parse_appcompat_cache,
)

logger = logging.getLogger(__name__)

CACHE_KEY_PATTERNS = (
    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager\\AppCompatibility",
    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager\\AppCompatCache",
)


class RegAppCompatCache(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAppCompatCache",
            "Get the Application Compatibility cache from System hive",
        )

    @staticmethod
    def add_diagnostic(report: RunReport, location: str, reason: str) -> None:
        message = f"AppCompatCache {location}: {reason}"
        logger.warning("%s", message)
        report.add_error(message)

    def cache_keys(self, reg: Registry, report: RunReport) -> Iterator[RegKey]:
        for pattern in CACHE_KEY_PATTERNS:
            try:
                yield from reg.glob_keys(pattern)
            except Exception as exception:
                self.add_diagnostic(report, pattern, str(exception))

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()
        try:
            reg = Registry.load(input_file, "\\HKLM\\SYSTEM")
        except Exception as exception:
            report.add_error(f"{exception}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            for key in self.cache_keys(reg, report):
                self.parse_key(key, output, report)
            report.add_output_report(output.get_report())

        return report

    def write_entry(
        self,
        parsed_entry: AppCompatCacheEntry,
        index: int,
        key: RegKey,
        key_security: Value,
        output: Output,
    ) -> None:
        record = Record()
        record.add("index", value(index))
        record.add("path", value(parsed_entry.path))
        record.add("modification_date", value(parsed_entry.modification_date))
        if parsed_entry.flag1 is not None:
            record.add("flag1", value(parsed_entry.flag1))
        if parsed_entry.flag2 is not None:
            record.add("flag2", value(parsed_entry.flag2))
        record.add("key_path", value(key.path))
        record.add("key_modif_time", value(key.mtime))
        record.add("key_security", key_security)
        output.write(record)

    def parse_key(self, key: RegKey, output: Output, report: RunReport) -> None:
        try:
            cache_value = key.value("AppCompatCache")
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        if cache_value is None:
            self.add_diagnostic(report, key.path, "missing AppCompatCache value")
            return

        try:
            cache = cache_value.data()
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        if not isinstance(cache, bytes):
            self.add_diagnostic(report, key.path, "AppCompatCache value is not bytes")
            return

        try:
            result = parse_appcompat_cache(cache)
        except AppCompatCacheParseError as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        except Exception as exception:
            self.add_diagnostic(report, key.path, f"unexpected parser failure: {exception}")
            return

        for diagnostic in result.diagnostics:
            self.add_diagnostic(report, key.path, diagnostic)

        try:
            key_security = Value.Object(key.security_descriptor.to_record())
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return

        for index, parsed_entry in enumerate(result.entries):
            try:
                self.write_entry(
                    parsed_entry,
                    index,
                    key,
                    key_security,
                    output,
                )
            except Exception as exception:
                self.add_diagnostic(report, key.path, str(exception))
                break
```

- [ ] **Step 4: Run focused plugin and real-hive regression tests**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache \
  tests.hive.test_app_compat_cache_formats \
  -v
```

Expected: `Ran 20 tests` followed by `OK`; the existing `SYSTEM.dat` test still
emits 108 lines and `SYSTEM_2.dat` still emits 474 lines with no errors.

- [ ] **Step 5: Commit plugin integration**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache.py tests/hive/test_app_compat_cache.py
git commit -m "Integrate multi-version AppCompatCache parsing"
```

### Task 6: Independent Reference Vectors and Full Verification

**Files:**
- Modify: `tests/hive/test_app_compat_cache_formats.py`

**Interfaces:**
- Consumes: the completed pure parser and plugin integration.
- Verifies: compatibility with the cited `winreg-kb` byte layouts independently of the synthetic builders.

- [ ] **Step 1: Add compact golden-vector assertions**

Add this test using literal headers and bodies rather than the shared builders:

```python
    def test_compact_golden_vectors(self):
        path = r"C:\golden.exe"
        encoded_path = path.encode("utf-16-le")

        win8_body = (
            len(encoded_path).to_bytes(2, "little")
            + encoded_path
            + bytes.fromhex("0200000001000000")
            + bytes.fromhex("5aa5")
            + FILETIME.to_bytes(8, "little")
            + (0).to_bytes(4, "little")
        )
        win8 = (
            (128).to_bytes(4, "little")
            + bytes(124)
            + b"10ts"
            + bytes(4)
            + len(win8_body).to_bytes(4, "little")
            + win8_body
        )

        win10_body = (
            len(encoded_path).to_bytes(2, "little")
            + encoded_path
            + FILETIME.to_bytes(8, "little")
            + (0).to_bytes(4, "little")
        )
        win10_header = bytearray(52)
        win10_header[0:4] = (52).to_bytes(4, "little")
        win10_header[40:44] = (1).to_bytes(4, "little")
        win10 = (
            bytes(win10_header)
            + b"10ts"
            + bytes(4)
            + len(win10_body).to_bytes(4, "little")
            + win10_body
        )

        for label, cache in (("Windows 8.1", win8), ("Windows 10", win10)):
            with self.subTest(label=label):
                result = parse_appcompat_cache(cache)
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(result.entries[0].path, path)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
```

- [ ] **Step 2: Run the pure parser, AppCompatCache integration, and complete suite**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_app_compat_cache -v
PYTHONPATH=src ../../.venv/bin/python -m unittest discover -q
```

Expected:

- Pure parser: `Ran 14 tests` followed by `OK`.
- AppCompatCache integration: `Ran 7 tests` followed by `OK`.
- Complete suite: all tests pass; the pre-change baseline was 149 tests, so the expected new total is 168 tests.

- [ ] **Step 3: Run static and repository-state checks**

Run:

```bash
.venv/bin/python -m compileall -q src/dfir_ogre_plugin_windows tests/hive
git diff --check
git status --short
```

Expected:

- `compileall` exits zero.
- `git diff --check` prints nothing.
- `git status --short` shows only the intended AppCompatCache changes plus the pre-existing unstaged ` M uv.lock`.

- [ ] **Step 4: Commit the independent vectors**

```bash
git add tests/hive/test_app_compat_cache_formats.py
git commit -m "Add AppCompatCache format regression vectors"
```

- [ ] **Step 5: Review the final diff and commit list**

Run:

```bash
git diff HEAD~6..HEAD --stat
git log -6 --oneline
```

Expected: six implementation commits cover Windows 10 parser extraction, XP,
fixed legacy layouts, Windows 8, plugin integration, and final vectors without
staging `uv.lock`.
