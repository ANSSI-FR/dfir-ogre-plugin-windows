# Windows 10 AppCompatCache Stale-Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop reporting valid Windows 10-format AppCompatCache values as errors when their advisory header count is stale.

**Architecture:** Keep the existing Windows 10 format discriminator and bounded sequential entry parser. Remove only the post-parse header-count equality diagnostic, leaving every marker, body, path, FILETIME, data-size, and cache-boundary check unchanged.

**Tech Stack:** Python 3, `unittest`, `dfir_ogre_common.Registry`, the `dfir-ogre-plugin` CLI.

## Global Constraints

- Treat the Windows 10 header count as advisory for both 48-byte and 52-byte headers.
- Do not change output fields, record ordering, per-key indexes, or non-Windows 10 parsing.
- Preserve all structural corruption diagnostics.
- Add no dependencies and make no unrelated refactors.

---

### Task 1: Make the Windows 10 header count advisory

**Files:**
- Modify: `tests/hive/test_app_compat_cache_formats.py:696-725`
- Modify: `tests/hive/test_app_compat_cache.py:184-220`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py:146-162`

**Interfaces:**
- Consumes: `windows_10_cache(entries: list[bytes], header_size: int = 52, declared_count: int | None = None) -> bytes` and `parse_appcompat_cache(cache: bytes) -> AppCompatCacheParseResult`.
- Produces: unchanged `parse_appcompat_cache` interface; Windows 10 results contain only structural diagnostics, never a header-count mismatch diagnostic.

- [x] **Step 1: Change the parser-level expectations before production code**

In `tests/hive/test_app_compat_cache_formats.py`, retain the structural truncation assertion but remove its derived count-mismatch expectation:

```python
def test_windows_10_stops_at_unbounded_truncation(self):
    valid = windows_10_entry(r"C:\Evidence\valid.exe")
    truncated = b"10ts" + bytes(4) + struct.pack("<I", 4096)
    result = parse_appcompat_cache(windows_10_cache([valid, truncated]))

    self.assertEqual([entry.path for entry in result.entries], [r"C:\Evidence\valid.exe"])
    self.assertEqual(len(result.diagnostics), 1)
    self.assertIn("outside the cache", result.diagnostics[0])
```

Replace `test_windows_10_exact_headers_honor_declared_count` with a test that exercises both supported headers and a stale count against a real entry:

```python
def test_windows_10_exact_headers_ignore_stale_count(self):
    for header_size in (48, 52):
        with self.subTest(header_size=header_size):
            result = parse_appcompat_cache(
                windows_10_cache(
                    [windows_10_entry(r"C:\Evidence\stale-count.exe")],
                    header_size=header_size,
                    declared_count=0,
                )
            )

            self.assertEqual(
                [entry.path for entry in result.entries],
                [r"C:\Evidence\stale-count.exe"],
            )
            self.assertEqual(result.diagnostics, ())
```

- [x] **Step 2: Change the plugin-level expectation before production code**

Replace `test_windows_10_exact_headers_report_count_mismatch` in `tests/hive/test_app_compat_cache.py` with:

```python
def test_windows_10_stale_header_count_is_not_an_error(self):
    parser = RegAppCompatCache()
    key_path = (
        r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
    )
    for header_size in (48, 52):
        with self.subTest(header_size=header_size):
            key = Mock()
            cache_value = Mock()
            cache_value.data.return_value = windows_10_cache(
                [windows_10_entry(r"C:\Evidence\stale-count.exe")],
                header_size=header_size,
                declared_count=0,
            )
            key.value.return_value = cache_value
            key.path = key_path
            key.mtime = None
            key.security_descriptor.to_record.return_value = Record()
            output = Mock()
            report = RunReport()

            parser.parse_key(key, output, report)

            self.assertEqual(report.num_errors, 0)
            self.assertIsNone(report.last_error)
            self.assertEqual(output.write.call_count, 1)
```

Add `windows_10_entry` to the existing imports from `test_app_compat_cache_formats`.

- [x] **Step 3: Run the changed tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_10_exact_headers_ignore_stale_count \
  tests.hive.test_app_compat_cache_formats.AppCompatCacheFormats.test_windows_10_stops_at_unbounded_truncation \
  tests.hive.test_app_compat_cache.AppCompatCache.test_windows_10_stale_header_count_is_not_an_error \
  -v
```

Expected: all three tests fail because the parser still emits `Windows 10 header declares ...` diagnostics; the plugin test reports one error instead of zero.

- [x] **Step 4: Implement the minimal parser change**

Replace `_parse_windows_10` with a direct return of the bounded entry parser result:

```python
def _parse_windows_10(cache: bytes, header_size: int) -> AppCompatCacheParseResult:
    result, _ = _parse_variable_entries(
        cache,
        header_size,
        b"10ts",
        "Windows 10",
        _parse_windows_10_body,
    )
    return result
```

- [x] **Step 5: Run the changed tests and verify GREEN**

Run the Step 3 command again.

Expected: 3 tests pass with no unexpected warnings or errors.

- [x] **Step 6: Run all focused AppCompatCache tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache_formats \
  tests.hive.test_app_compat_cache \
  -v
```

Expected: 40 tests pass. Existing malformed-cache tests continue to emit only their expected diagnostics.

- [x] **Step 7: Verify the supplied Server 2016 hive through the CLI**

Create a fresh temporary output directory, then run:

```bash
REGAPP_OUT=$(mktemp -d)
.venv/bin/dfir-ogre-plugin run \
  -f /home/asalais/dev/dfir-ogre/manual_tests/debug_data/system.2016.data \
  -p configuration/registry/app_compat_cache.xml \
  -o "$REGAPP_OUT"
```

Expected: the CLI log contains its normal `INFO` line and no `WARNING` or `ERROR` lines. The resulting JSONL contains 1,493 records: 747 for `ControlSet001` and 746 for `ControlSet002`.

- [x] **Step 8: Run repository verification**

Run:

```bash
.venv/bin/python -m compileall -q \
  src/dfir_ogre_plugin_windows \
  tests/hive/test_app_compat_cache.py \
  tests/hive/test_app_compat_cache_formats.py
git diff --check
.venv/bin/python -m unittest discover -v
```

Expected: compilation and `git diff --check` succeed. All AppCompatCache tests pass; the complete suite may retain only the previously confirmed unrelated baseline failures in `test_scheduled_task` and `test_hive_keys`.

- [x] **Step 9: Review and commit the implementation**

Confirm the diff contains only the approved test expectation changes and the removal of the Windows 10 count diagnostic, then run:

```bash
git add \
  src/dfir_ogre_plugin_windows/registry/app_compat_cache_formats.py \
  tests/hive/test_app_compat_cache_formats.py \
  tests/hive/test_app_compat_cache.py
git add -f docs/superpowers/plans/2026-07-22-windows-10-appcompatcache-stale-count.md
git commit -m "Ignore stale Windows 10 AppCompatCache counts"
```

Expected: one implementation commit containing the minimal parser change, regressions, and this plan.
