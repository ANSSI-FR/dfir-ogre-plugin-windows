# Winlogon Notify Autoruns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect documented Winlogon notification packages beneath `Winlogon\Notify` while preserving support for a nonstandard `DllName` on the parent key.

**Architecture:** Keep the existing data-driven autoruns parser and add one immediate-child wildcard path to each Winlogon Notify mapping. Exercise the complete SOFTWARE and user plugin control flow with controlled registry doubles so the regression test verifies path selection, record emission, and child-key metadata without adding a binary hive fixture.

**Tech Stack:** Python 3.10+, `dfir-ogre-common` registry/output APIs, standard-library `unittest`, and `unittest.mock`.

## Global Constraints

- Enumerate only immediate package keys beneath `Winlogon\Notify`.
- Read only `DllName` from each parent or package key.
- Apply identical parent-plus-child behavior to HKLM SOFTWARE and HKCU user hives.
- Preserve support for a nonstandard `DllName` stored directly on `Notify`.
- Preserve the existing `reg_autoruns` record schema, persistence type, registry metadata, and error handling.
- Skip keys whose `DllName` is absent or empty.
- Do not parse notification handler values or recursively inspect package descendants.
- Do not add or modify a binary registry-hive fixture.
- Do not change dependencies or `uv.lock`.

---

### Task 1: Parse Winlogon Notify parent and package keys

**Files:**
- Modify: `tests/hive/test_autoruns_hive.py:1-238`
- Modify: `src/dfir_ogre_plugin_windows/registry/autoruns_hive.py:100-210`

**Interfaces:**
- Consumes: `Registry.glob_keys(path)`, `RegAutorunsSoftware.parse()`, `RegAutorunsUser.parse()`, and the existing `parse_key(key, persistence_type, target_values, output)` record builder.
- Produces: `SOFTWARE_KEYS["Winlogon Notify"]` and `USER_KEYS["Winlogon Notify"]` mappings that query both the exact `Notify` key and its immediate `Notify\*` children; no new public API.

- [ ] **Step 1: Add a parser-level regression harness and failing test**

Update the test imports in `tests/hive/test_autoruns_hive.py`:

```python
import json
import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    Value,
)
from dfir_ogre_plugin_windows import (
    RegAutorunsSoftware,
    RegAutorunsSystem,
    RegAutorunsUser,
)
```

Add these methods near the beginning of `TestAutoruns`, before the existing
fixture-backed tests:

```python
    @staticmethod
    def _make_notify_key(path, dll_name, owner_sid, mtime):
        security_record = Record()
        security_record.add("owner_sid", Value.String(owner_sid))
        security_record.add("group_sid", Value.String(owner_sid))
        security_descriptor = Mock()
        security_descriptor.to_record.return_value = security_record

        key = Mock()
        key.path = path
        key.mtime = mtime
        key.security_descriptor = security_descriptor

        def value_data(name, default=None):
            return dll_name if name == "DllName" else default

        key.value_data.side_effect = value_data
        return key

    def _parse_notify_keys(self, parser, config_name, hive_root, output_name):
        notify_query = (
            f"\\{hive_root}\\Microsoft\\Windows NT\\CurrentVersion"
            "\\Winlogon\\Notify"
        )
        parent_path = notify_query.removeprefix("\\")
        package_path = parent_path + "\\ExamplePackage"
        missing_dll_path = parent_path + "\\MissingDllName"
        parent_time = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        package_time = datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

        parent_key = self._make_notify_key(
            parent_path,
            "legacy-notify.dll",
            "S-1-5-21-100",
            parent_time,
        )
        package_key = self._make_notify_key(
            package_path,
            "package-notify.dll",
            "S-1-5-21-200",
            package_time,
        )
        missing_dll_key = self._make_notify_key(
            missing_dll_path,
            None,
            "S-1-5-21-300",
            datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc),
        )

        class RegistryWithNotify:
            def __init__(self):
                self.queries = []

            def glob_keys(self, path):
                self.queries.append(path)
                if path == notify_query:
                    return [parent_key]
                if path == notify_query + "\\*":
                    return [package_key, missing_dll_key]
                return []

        registry = RegistryWithNotify()
        plugin_file = os.path.join(CONF_FOLDER, config_name)
        output_file = os.path.join(
            TEMP_FOLDER, f"{output_name}.reg_autoruns.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    output_name,
                    TEMP_FOLDER,
                    with_timeline=True,
                    include_empty=True,
                )
            ]
        )
        with patch(
            "dfir_ogre_plugin_windows.registry.autoruns_hive.Registry"
        ) as registry_type:
            registry_type.load.return_value = registry
            report = parser.parse(
                "unused-hive",
                plugin_file,
                run_config,
                Metadata("test"),
            )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as output:
            records = [json.loads(line) for line in output]

        return {
            "records": {
                record["data"]["key_path"]: record for record in records
            },
            "queries": registry.queries,
            "notify_query": notify_query,
            "parent_path": parent_path,
            "package_path": package_path,
            "missing_dll_path": missing_dll_path,
            "package_time": package_time,
        }

    def test_winlogon_notify_reads_parent_and_package_keys(self):
        cases = (
            (
                RegAutorunsSoftware(),
                "autoruns_software.xml",
                "HKLM\\SOFTWARE",
                "winlogon_notify_software",
            ),
            (
                RegAutorunsUser(),
                "autoruns_user.xml",
                "HKCU\\Software",
                "winlogon_notify_user",
            ),
        )

        for parser, config_name, hive_root, output_name in cases:
            with self.subTest(parser=parser.description().command):
                result = self._parse_notify_keys(
                    parser, config_name, hive_root, output_name
                )
                records = result["records"]

                self.assertEqual(
                    set(records),
                    {result["parent_path"], result["package_path"]},
                )
                self.assertIn(
                    result["notify_query"] + "\\*", result["queries"]
                )
                self.assertNotIn(
                    result["notify_query"] + "\\*\\*", result["queries"]
                )
                self.assertNotIn(result["missing_dll_path"], records)

                parent_record = records[result["parent_path"]]
                self.assertEqual(
                    parent_record["data"]["values"],
                    [{"name": "DllName", "data": "legacy-notify.dll"}],
                )

                package_record = records[result["package_path"]]
                self.assertEqual(
                    package_record["data"]["type"], "Winlogon Notify"
                )
                self.assertEqual(
                    package_record["data"]["values"],
                    [{"name": "DllName", "data": "package-notify.dll"}],
                )
                self.assertEqual(
                    package_record["timestamp"],
                    result["package_time"].isoformat(),
                )
                self.assertEqual(
                    package_record["data"]["key_modif_time"],
                    result["package_time"].isoformat(),
                )
                self.assertEqual(
                    package_record["related_user"], "S-1-5-21-200"
                )
                self.assertEqual(
                    package_record["data"]["key_security"]["owner_sid"],
                    "S-1-5-21-200",
                )
```

- [ ] **Step 2: Run the new test and verify RED**

Run from the isolated worktree:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_autoruns_hive.TestAutoruns.test_winlogon_notify_reads_parent_and_package_keys -v
```

Expected: `FAIL`. Each subtest emits the compatible direct-parent record but
does not query `Notify\*`, so the expected package path is absent.

- [ ] **Step 3: Add immediate-child paths to both mappings**

Replace the SOFTWARE Winlogon Notify entry in
`src/dfir_ogre_plugin_windows/registry/autoruns_hive.py` with:

```python
    'Winlogon Notify': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify',
         ('DllName',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify\\*',
         ('DllName',)),
    ],
```

Replace the user Winlogon Notify entry with:

```python
    'Winlogon Notify': [
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify',
         ('DllName',)),
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify\\*',
         ('DllName',)),
    ],
```

Do not add recursive wildcards or a special-case traversal function. The
existing generic loop must pass every matching parent or package key to
`parse_key()`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_autoruns_hive.TestAutoruns.test_winlogon_notify_reads_parent_and_package_keys -v
```

Expected: `PASS`. Both subtests emit the parent and immediate package records,
skip the child without `DllName`, and retain package-key metadata.

- [ ] **Step 5: Run the complete autoruns hive test module**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_autoruns_hive -v
```

Expected: all four tests in `tests.hive.test_autoruns_hive` pass.

- [ ] **Step 6: Run full verification**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest discover -q
PYTHONPATH=src ../../.venv/bin/python -m compileall -q src tests
git diff --check
```

Expected: the full suite passes with 149 tests, compilation succeeds, and
`git diff --check` emits no output.

- [ ] **Step 7: Review the final diff for scope**

Run:

```bash
git diff -- src/dfir_ogre_plugin_windows/registry/autoruns_hive.py \
  tests/hive/test_autoruns_hive.py
```

Expected: the source diff contains only the two immediate-child mapping
entries. The test diff contains only the controlled Notify registry harness,
the HKLM/HKCU regression, and required imports. No dependency, fixture,
configuration, or unrelated parser changes are present.

- [ ] **Step 8: Commit the fix**

```bash
git add src/dfir_ogre_plugin_windows/registry/autoruns_hive.py \
  tests/hive/test_autoruns_hive.py
git commit -m "Fix Winlogon Notify autorun parsing"
```
