# Windows 8.x AppCompatCache Package-Only Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept structurally valid Windows 8.x package-only AppCompatCache entries without emitting empty-path records or parser errors.

**Architecture:** Extend the internal variable-body parser contract to allow a valid body to return no path entry. The Windows 8.x body parser will use that outcome only when the path is empty, the package field is nonempty, and all remaining bounded fields validate; all other formats and malformed-entry diagnostics remain unchanged.

**Tech Stack:** Python 3.10, `unittest`, `dfir_ogre_common` registry APIs, `dfir-ogre-plugin` CLI.

## Global Constraints

- Only Windows 8.0 and Windows 8.1 package-only entries may omit a path.
- A valid package-only entry emits no output record and no diagnostic.
- A zero-length path with no package data remains malformed.
- Odd or invalid nonempty UTF-16 paths and truncated package/body fields remain malformed.
- Package bytes remain opaque and may have an odd byte length.
- Do not change dependencies or the XML output schema.

---

### Task 1: Recognize and Skip Valid Package-Only Entries

**Files:**
- Modify: `tests/hive/test_app_compat_cache_formats.py:589-662`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py:8-120`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py:454-497`

**Interfaces:**
- Consumes: `_parse_windows_8_body(body: bytes, entry_index: int, version: str)`
- Produces: `BodyParser` results of `tuple[AppCompatCacheEntry | None, list[str]]`; `None` means the bounded body is valid but has no path record to emit

- [ ] **Step 1: Add regression and malformed-control tests**

Add these tests after `test_windows_8_skips_package_data_before_flags`:

```python
    def test_windows_8_skips_valid_package_only_entry(self):
        package = (
            "00000009\t0011000425804000\t0006000300000000\t"
            "microsoft.windowscommunicationsapps\t8wekyb3d8bbwe\t"
        ).encode("utf-16-le")
        for version in ("8.0", "8.1"):
            with self.subTest(version=version):
                first = windows_8_entry(
                    r"C:\Evidence\first.exe",
                    version,
                    bytes.fromhex("01000000"),
                    bytes(4),
                )
                package_only = windows_8_entry(
                    "",
                    version,
                    bytes.fromhex("15000000"),
                    bytes.fromhex("00010000"),
                    package=package,
                )
                last = windows_8_entry(
                    r"C:\Evidence\last.exe",
                    version,
                    bytes.fromhex("02000000"),
                    bytes(4),
                )

                result = parse_appcompat_cache(
                    windows_8_cache([first, package_only, last])
                )

                self.assertEqual(
                    [entry.path for entry in result.entries],
                    [r"C:\Evidence\first.exe", r"C:\Evidence\last.exe"],
                )
                self.assertEqual(result.diagnostics, ())

    def test_windows_8_zero_path_without_package_is_malformed(self):
        empty = windows_8_entry(
            "",
            "8.1",
            bytes.fromhex("15000000"),
            bytes.fromhex("00010000"),
        )
        valid = windows_8_entry(
            r"C:\Evidence\valid.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )

        result = parse_appcompat_cache(windows_8_cache([empty, valid]))

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\Evidence\valid.exe"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("path has invalid byte size 0", result.diagnostics[0])

    def test_windows_8_package_only_entry_still_validates_package_extent(self):
        malformed_body = struct.pack("<HH", 0, 100)
        valid = windows_8_entry(
            r"C:\Evidence\valid.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )

        result = parse_appcompat_cache(
            windows_8_cache(
                [variable_entry(b"10ts", malformed_body), valid]
            )
        )

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\Evidence\valid.exe"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("flags extend outside the entry body", result.diagnostics[0])
```

- [ ] **Step 2: Run the new tests and verify the current parser fails for the intended reasons**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_skips_valid_package_only_entry \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_zero_path_without_package_is_malformed \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_package_only_entry_still_validates_package_extent \
  -v
```

Expected: the valid-package test fails because it receives
`path has invalid byte size 0`; the package-extent test fails because the path
check fires before the package boundary check. The zero-path/zero-package
control passes.

- [ ] **Step 3: Make valid non-emitting bodies explicit in the parser contract**

Change the body-parser alias to:

```python
BodyParser = Callable[
    [bytes, int],
    tuple["AppCompatCacheEntry | None", list[str]],
]
```

In `_parse_variable_entries`, append only a returned entry:

```python
        else:
            if entry is not None:
                entries.append(entry)
            diagnostics.extend(entry_diagnostics)
```

- [ ] **Step 4: Implement the narrow Windows 8.x package-only behavior**

Change `_parse_windows_8_body` and its wrappers to return optional entries:

```python
def _parse_windows_8_body(
    body: bytes,
    entry_index: int,
    version: str,
) -> tuple[AppCompatCacheEntry | None, list[str]]:
    path_size = _read_uint(body, 0, 2, "path size")
    path = _decode_utf16(body, 2, path_size, "path") if path_size else None
    package_size_offset = 2 + path_size
    package_size = _read_uint(body, package_size_offset, 2, "package size")
    if path is None and package_size == 0:
        raise AppCompatCacheParseError("path has invalid byte size 0")
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
    if path is None:
        return None, diagnostics
    return AppCompatCacheEntry(path, modification_date, flag1, flag2), diagnostics
```

Update `_parse_windows_8_0_body` and `_parse_windows_8_1_body` return types to
`tuple[AppCompatCacheEntry | None, list[str]]`.

- [ ] **Step 5: Run the three focused tests and verify they pass**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_skips_valid_package_only_entry \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_zero_path_without_package_is_malformed \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_8_package_only_entry_still_validates_package_extent \
  -v
```

Expected: `Ran 3 tests` and `OK`.

- [ ] **Step 6: Run the complete AppCompatCache test suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats \
  tests.hive.test_app_compat_cache \
  -v
```

Expected: every AppCompatCache format and plugin test passes.

- [ ] **Step 7: Verify the supplied Windows 8.1 hive**

Create a fresh output directory with `mktemp -d`, then run:

```bash
.venv/bin/dfir-ogre-plugin run \
  -f /home/asalais/dev/dfir-ogre/manual_tests/debug_data/app_compat_cache.system.w81.data \
  -p configuration/registry/app_compat_cache.xml \
  -o <fresh-output-directory>
```

Expected: only the `INFO` start message, no `WARNING` or `ERROR`, exit zero, and
an output JSONL containing 112 path records.

- [ ] **Step 8: Check the exact diff and formatting**

Run:

```bash
git diff --check
git diff -- \
  src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py \
  tests/hive/test_app_compat_cache_formats.py
```

Expected: `git diff --check` exits zero. The source diff contains only the
optional body-parser result and Windows 8.x exception; the test diff contains
only the three focused regression/control cases.

- [ ] **Step 9: Commit the implementation**

```bash
git add \
  src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py \
  tests/hive/test_app_compat_cache_formats.py
git commit -m "Handle Windows 8 package-only cache entries"
```
