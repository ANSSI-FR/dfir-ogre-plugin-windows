# AppCompatCache Missing-Value Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat an absent `AppCompatCache` registry value as an absent artifact while preserving errors for present non-byte or malformed values.

**Architecture:** Keep registry key discovery and binary-format parsing unchanged. Make the semantic distinction at the start of `RegAppCompatCache.parse_key`: a `None` lookup result returns cleanly, while every present value continues through the existing data-type and structural validation.

**Tech Stack:** Python 3.10, `unittest`, `dfir_ogre_common` registry and reporting APIs.

## Global Constraints

- A missing `AppCompatCache` value emits no record, warning, or `RunReport` error.
- A present non-byte value remains an error.
- A present malformed byte value remains an error.
- Registry discovery, successful output records, and cache-format parsing remain unchanged.
- Do not add dependencies or change the XML output schema.

---

### Task 1: Distinguish Artifact Absence from Invalid Cache Data

**Files:**
- Modify: `tests/hive/test_app_compat_cache.py:121-145`
- Modify: `src/dfir_ogre_plugin_windows/registry/app_compat_cache.py:96-113`

**Interfaces:**
- Consumes: `RegKey.value("AppCompatCache") -> RegValue | None`
- Produces: `RegAppCompatCache.parse_key(key, output, report) -> None` with a clean early return only when the lookup result is `None`

- [ ] **Step 1: Replace the combined semantics test with focused missing-value and non-byte tests**

```python
def test_missing_value_is_artifact_absent(self):
    parser = RegAppCompatCache()
    key = Mock()
    key.value.return_value = None
    key.path = r"HKLM\SYSTEM\ControlSet001\missing"
    output = Mock()
    report = RunReport()

    with self.assertNoLogs(
        "dfir_ogre_plugin_windows.registry.app_compat_cache",
        level="WARNING",
    ):
        parser.parse_key(key, output, report)

    self.assertEqual(output.write.call_count, 0)
    self.assertEqual(report.num_errors, 0)
    self.assertIsNone(report.last_error)

def test_non_byte_value_is_diagnostic(self):
    parser = RegAppCompatCache()
    key = Mock()
    cache_value = Mock()
    cache_value.data.return_value = "not bytes"
    key.value.return_value = cache_value
    key.path = r"HKLM\SYSTEM\ControlSet001\non-byte"
    output = Mock()
    report = RunReport()

    with self.assertLogs(
        "dfir_ogre_plugin_windows.registry.app_compat_cache",
        level="WARNING",
    ) as logs:
        parser.parse_key(key, output, report)

    self.assertEqual(output.write.call_count, 0)
    self.assertEqual(report.num_errors, 1)
    self.assertIn("AppCompatCache value is not bytes", report.last_error)
    self.assertIn("AppCompatCache value is not bytes", logs.output[0])
```

- [ ] **Step 2: Run the new missing-value test and verify the current implementation fails**

Run:

```bash
.venv/bin/python -m unittest tests.hive.test_app_compat_cache.AppCompatCache.test_missing_value_is_artifact_absent -v
```

Expected: `FAIL`; the current implementation logs a warning and adds
`missing AppCompatCache value` to the report.

- [ ] **Step 3: Implement the minimal clean early return**

Change the existing `None` branch to:

```python
if cache_value is None:
    return
```

Do not change exception handling, the non-byte branch, or
`parse_appcompat_cache`.

- [ ] **Step 4: Run both semantics tests and verify they pass**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache.AppCompatCache.test_missing_value_is_artifact_absent \
  tests.hive.test_app_compat_cache.AppCompatCache.test_non_byte_value_is_diagnostic \
  -v
```

Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 5: Reproduce the repair-hive case**

Create the isolated output directory:

```bash
mkdir -p /tmp/dfir-ogre-appcompat-missing-value
```

Run:

```bash
.venv/bin/dfir-ogre-plugin run \
  -f /home/asalais/dev/dfir-ogre/manual_tests/debug_data/appcompat_cache.SYSTEM.2003.data \
  -p configuration/registry/app_compat_cache.xml \
  -o /tmp/dfir-ogre-appcompat-missing-value
```

Expected: the plugin logs its `INFO` start message with no `WARNING` or
`ERROR`, exits zero, and emits zero AppCompatCache rows.

- [ ] **Step 6: Run the populated-hive integration controls**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache.AppCompatCache.test_compat_cache \
  tests.hive.test_app_compat_cache.AppCompatCache.test_compat_cache_2 \
  -v
```

Expected: `Ran 2 tests` and `OK`, retaining 54 and 237 canonical entries.

- [ ] **Step 7: Run the complete AppCompatCache suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_app_compat_cache \
  tests.hive.test_app_compat_cache_formats \
  -v
```

Expected: all tests pass, including malformed non-byte and binary-cache
diagnostics.

- [ ] **Step 8: Check formatting and the exact diff**

Run:

```bash
git diff --check
git diff -- src/dfir_ogre_plugin_windows/registry/app_compat_cache.py tests/hive/test_app_compat_cache.py
```

Expected: `git diff --check` exits zero; the source diff contains only the
removed missing-value diagnostic and the test diff contains only the focused
semantics split.

- [ ] **Step 9: Commit the implementation**

```bash
git add src/dfir_ogre_plugin_windows/registry/app_compat_cache.py tests/hive/test_app_compat_cache.py
git commit -m "Treat missing AppCompatCache value as absent"
```
