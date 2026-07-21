# Windows XP AppCompatCache Slot Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Windows XP AppCompatCache parsing from reporting fixed-capacity unused slots as malformed while retaining only the active records named by the LRU index table.

**Architecture:** Keep the format dispatcher and every post-XP parser unchanged. Extend the XP test builder to represent allocated and active slots independently, then make `_parse_windows_xp()` validate the allocated array, derive the active slot set from the LRU table, and parse that set in physical-slot order.

**Tech Stack:** Python 3.10+, standard-library `struct`, existing immutable AppCompatCache result types, `dfir_ogre_common`, and `unittest`; no new dependency.

## Global Constraints

- Change only `_parse_windows_xp()` and XP-specific test helpers/tests.
- Use the DWORD at offset `0x04` only to bound the allocated 552-byte slot array.
- Use the LRU count at offset `0x08` and indexes at offset `0x10` to select active slots.
- Preserve deterministic ascending physical-slot output order and the existing public record schema.
- Do not emit unreferenced nonzero slots as active records.
- Keep active-entry UTF-16, terminator, and FILETIME recovery behavior unchanged.
- Leave Windows 2003/Vista, Windows 7, Windows 8.x, Windows 10, XML configuration, registry discovery, and diagnostic plumbing unchanged.
- Keep `tests/data/hive/SYSTEM_WIN_XP_SP2.data` untouched and untracked.

---

## File Structure

- Modify `tests/hive/test_app_compat_cache_formats.py`: represent allocated XP slots independently from LRU-selected active slots and add focused valid/invalid header tests.
- Modify `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py`: select and validate XP active slots without changing any other format parser.
- Read `tests/data/hive/SYSTEM_WIN_XP_SP2.data` only during final local verification.

### Task 1: Select Active XP Slots from the LRU Table

**Files:**
- Modify: `tests/hive/test_app_compat_cache_formats.py:81-92,277-322`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py:165-238`

**Interfaces:**
- Consumes: `parse_appcompat_cache(cache: bytes) -> AppCompatCacheParseResult`.
- Produces: `windows_xp_entry(path: str) -> bytes` and an extended `windows_xp_cache(paths: list[str], *, slot_count: int | None = None, lru_indexes: list[int] | None = None) -> bytes` test helper.
- Preserves: `AppCompatCacheParseResult.entries` in ascending physical-slot order and `diagnostics` for referenced malformed entries.

- [ ] **Step 1: Replace the XP test builder with fixed-capacity support**

Replace the current `windows_xp_cache()` helper in `tests/hive/test_app_compat_cache_formats.py` with:

```python
def windows_xp_entry(path: str) -> bytes:
    encoded_path = path.encode("utf-16-le") + b"\x00\x00"
    path_field = encoded_path + bytes(528 - len(encoded_path))
    return path_field + struct.pack("<QQQ", FILETIME, 1234, FILETIME)


def windows_xp_cache(
    paths: list[str],
    *,
    slot_count: int | None = None,
    lru_indexes: list[int] | None = None,
) -> bytes:
    if slot_count is None:
        slot_count = len(paths)
    if lru_indexes is None:
        lru_indexes = list(range(len(paths)))
    if len(paths) != len(lru_indexes):
        raise ValueError("each XP path requires one LRU index")

    header = bytearray(400)
    struct.pack_into(
        "<IIII",
        header,
        0,
        0xDEADBEEF,
        slot_count,
        len(lru_indexes),
        0,
    )
    entries = [bytes(552) for _ in range(slot_count)]
    for lru_position, (slot_index, path) in enumerate(zip(lru_indexes, paths)):
        struct.pack_into("<I", header, 16 + lru_position * 4, slot_index)
        entries[slot_index] = windows_xp_entry(path)
    return bytes(header) + b"".join(entries)
```

This keeps all existing calls backward-compatible while allowing a 96-slot serialized value with fewer active paths.

- [ ] **Step 2: Add failing active-slot selection tests**

Add these tests immediately after `test_windows_xp()` in `AppCompatCacheFormats`:

```python
    def test_windows_xp_ignores_unused_allocated_slots(self):
        result = parse_appcompat_cache(
            windows_xp_cache(
                [r"C:\active-one.exe", r"C:\active-two.exe"],
                slot_count=96,
            )
        )

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\active-one.exe", r"C:\active-two.exe"],
        )
        self.assertEqual(result.diagnostics, ())

    def test_windows_xp_uses_lru_indexes_in_physical_slot_order(self):
        cache = bytearray(
            windows_xp_cache(
                [r"C:\slot-five.exe", r"C:\slot-two.exe"],
                slot_count=6,
                lru_indexes=[5, 2],
            )
        )
        stale_offset = 400 + 4 * 552
        cache[stale_offset : stale_offset + 552] = windows_xp_entry(
            r"C:\unreferenced-stale.exe"
        )

        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\slot-two.exe", r"C:\slot-five.exe"],
        )
        self.assertEqual(result.diagnostics, ())
```

- [ ] **Step 3: Run the two tests and verify the regression is red**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_xp_ignores_unused_allocated_slots \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_xp_uses_lru_indexes_in_physical_slot_order \
  -v
```

Expected: `FAILED (failures=2)`. The first test sees 94 false empty-path diagnostics. The second includes the unreferenced stale path and false empty-slot diagnostics.

- [ ] **Step 4: Make the minimal XP active-slot selection change**

In `_parse_windows_xp()`, retain the existing count and boundary behavior but replace the LRU validation/entry-loop setup with:

```python
    active_indexes: list[int] = []
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
            else:
                active_indexes.append(cached_index)

    entries: list[AppCompatCacheEntry] = []
    for entry_index in sorted(active_indexes):
```

Leave the existing fixed-entry body under that loop unchanged.

- [ ] **Step 5: Run the focused tests and verify green**

Run the command from Step 3 again.

Expected: `Ran 2 tests` followed by `OK`.

- [ ] **Step 6: Run the full format parser module**

Run:

```bash
.venv/bin/python -m unittest tests.hive.test_app_compat_cache_formats -v
```

Expected: all existing tests plus the two new XP tests pass.

- [ ] **Step 7: Commit active-slot selection**

```bash
git add tests/hive/test_app_compat_cache_formats.py \
  src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py
git commit -m "Select active Windows XP AppCompatCache slots"
```

### Task 2: Reject Inconsistent XP LRU Metadata

**Files:**
- Modify: `tests/hive/test_app_compat_cache_formats.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py:173-210`

**Interfaces:**
- Consumes: `AppCompatCacheParseError`, `_read_uint()`, and the Task 1 XP test helpers.
- Produces: fatal header validation for an LRU count beyond allocated slots, an out-of-range LRU index, or a duplicate LRU index.
- Preserves: recoverable diagnostics for corruption inside a valid referenced slot.

- [ ] **Step 1: Add failing LRU metadata validation tests**

Add these tests after the active-slot selection tests:

```python
    def test_windows_xp_rejects_lru_count_beyond_allocated_slots(self):
        cache = bytearray(
            windows_xp_cache([r"C:\active.exe"], slot_count=2)
        )
        struct.pack_into("<I", cache, 8, 3)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU entry count 3 exceeds 2 allocated slots",
        ):
            parse_appcompat_cache(bytes(cache))

    def test_windows_xp_rejects_out_of_range_lru_index(self):
        cache = bytearray(
            windows_xp_cache([r"C:\active.exe"], slot_count=2)
        )
        struct.pack_into("<I", cache, 16, 2)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU index 2 is outside 2 allocated slots",
        ):
            parse_appcompat_cache(bytes(cache))

    def test_windows_xp_rejects_duplicate_lru_index(self):
        cache = bytearray(
            windows_xp_cache(
                [r"C:\first.exe", r"C:\second.exe"],
                slot_count=2,
            )
        )
        struct.pack_into("<I", cache, 20, 0)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU index 0 is duplicated",
        ):
            parse_appcompat_cache(bytes(cache))
```

- [ ] **Step 2: Run the validation tests and verify red**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_xp_rejects_lru_count_beyond_allocated_slots \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_xp_rejects_out_of_range_lru_index \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_xp_rejects_duplicate_lru_index \
  -v
```

Expected: `FAILED (failures=3)` because the Task 1 implementation still returns diagnostics or duplicate entries instead of rejecting inconsistent header metadata.

- [ ] **Step 3: Implement strict allocated-slot and LRU validation**

Replace the XP count, array-bound, and LRU block with this code, then keep the existing entry-body loop beneath it:

```python
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
```

- [ ] **Step 4: Run the validation tests and verify green**

Run the command from Step 2 again.

Expected: `Ran 3 tests` followed by `OK`.

- [ ] **Step 5: Run all AppCompatCache tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache \
  tests.hive.test_app_compat_cache_formats \
  -v
```

Expected: `Ran 37 tests` followed by `OK`. The existing Windows 10 real-hive snapshots and all Windows 2003/Vista, Windows 7, and Windows 8.x format tests remain unchanged.

- [ ] **Step 6: Check the patch and commit strict validation**

Run:

```bash
git diff --check
git diff -- src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py \
  tests/hive/test_app_compat_cache_formats.py
```

Expected: no whitespace errors; the diff is limited to the XP parser and XP tests.

Then commit:

```bash
git add tests/hive/test_app_compat_cache_formats.py \
  src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py
git commit -m "Validate Windows XP AppCompatCache LRU metadata"
```

### Task 3: Verify the Real XP Hive and Repository Regressions

**Files:**
- Read only: `tests/data/hive/SYSTEM_WIN_XP_SP2.data`
- Read only: all test modules discovered by `unittest`

**Interfaces:**
- Consumes: `RegAppCompatCache.parse()`, `canonical_cache_sequence_snapshot()`, and the untracked XP fixture.
- Produces: verification evidence only; no source or fixture changes.

- [ ] **Step 1: Run the real XP fixture end to end**

Run:

```bash
.venv/bin/python - <<'PY'
import tempfile

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import RegAppCompatCache
from tests.hive.test_app_compat_cache import canonical_cache_sequence_snapshot

with tempfile.TemporaryDirectory(
    prefix="dfir-ogre-xp-verification.",
    dir="/tmp",
) as output_dir:
    output_config = OutputConfiguration(
        "xp_sp2",
        output_dir,
        with_timeline=True,
        include_empty=True,
    )
    report = RegAppCompatCache().parse(
        "tests/data/hive/SYSTEM_WIN_XP_SP2.data",
        "configuration/registry/app_compat_cache.xml",
        RunConfiguration([output_config]),
        Metadata("verification"),
    )
    assert report.num_errors == 0, report.last_error
    file_report = report.output_reports[0].file_reports[0]
    entry_count, _ = canonical_cache_sequence_snapshot(file_report.file_name)
    assert file_report.num_lines == 60, file_report.num_lines
    assert entry_count == 30, entry_count
    print("XP SP2: 30 unique entries, 60 timeline lines, 0 errors")
PY
```

Expected: `XP SP2: 30 unique entries, 60 timeline lines, 0 errors`.

- [ ] **Step 2: Run the complete repository test suite**

Run:

```bash
.venv/bin/python -m unittest discover -v
```

Expected: exit status 0 and final `OK`.

- [ ] **Step 3: Verify final scope and worktree state**

Run:

```bash
git diff --check HEAD~2..HEAD
git show --stat --oneline HEAD~2..HEAD
git status --short
```

Expected:

- no whitespace errors;
- implementation commits change only `app_compat_cache_formats.py` and its test module;
- `tests/data/hive/SYSTEM_WIN_XP_SP2.data` remains the only untracked user file;
- no post-XP parser or configuration file changed.
