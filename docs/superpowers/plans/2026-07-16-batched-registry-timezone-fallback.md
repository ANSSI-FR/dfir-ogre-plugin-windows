# Batched Registry Timezone Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Scheduled Task, ShellBag, and batched LNK local timestamps deterministic by resolving the matching SYSTEM timezone per VSS snapshot and falling back to naive UTC without stopping parsing.

**Architecture:** Add one shared resolver policy that preserves detailed `RunReport.errors`, logs one fallback warning, and always returns a usable `tzinfo`. Convert Scheduled Task to the existing batched registry pattern, then route all three parsers through the shared policy while retaining their artifact-specific timestamp decoders.

**Tech Stack:** Python 3.10+, `datetime`, `zoneinfo`, `python-dateutil`, `unittest`, `dfir_ogre_common` batched plugin/registry/output APIs.

## Global Constraints

- Group SOFTWARE/SYSTEM and artifact/SYSTEM inputs by case-insensitive VSS snapshot metadata.
- Resolve the source timezone once per artifact-bearing snapshot.
- Preserve missing, unreadable, or unrecognized SYSTEM timezone conditions in `RunReport.errors`.
- Log exactly one warning after an unsuccessful timezone resolution attempt, then use `timezone.utc` as the deterministic fallback.
- Continue parsing and producing output after timezone fallback.
- Never consult the analyst machine timezone.
- Preserve offset-aware Scheduled Task registration timestamps according to their embedded offsets.
- Preserve existing output field names, timeline qualifiers, dependencies, task-action decoding, and non-local timestamp behavior.
- Preserve the pre-existing `uv.lock` worktree modification and do not stage it.

---

## File Structure

- Create: `tests/test_system_timezone.py`
  - Verifies the shared successful-resolution and UTC-fallback policy.
- Modify: `src/dfir_ogre_plugin_windows/system_timezone.py`
  - Adds the shared error/warning/fallback policy without changing the detailed resolver.
- Modify: `tests/hive/test_scheduled_task.py`
  - Adds timestamp, grouping, batch integration, fallback, and host-independence regressions.
- Modify: `src/dfir_ogre_plugin_windows/registry/scheduled_task.py`
  - Converts Scheduled Task parsing to snapshot-aware batching and explicit timezone normalization.
- Modify: `configuration/registry/scheduled_task.xml`
  - Marks `RegScheduledTask` as a batched parser.
- Modify: `tests/hive/test_shell_bag.py`
  - Proves missing SYSTEM records an error, warns, falls back to UTC, and still emits ShellBag records.
- Modify: `src/dfir_ogre_plugin_windows/registry/shellbag.py`
  - Uses the shared always-usable timezone policy.
- Modify: `tests/test_lnk.py`
  - Proves the same missing-SYSTEM control flow for batched LNK parsing.
- Modify: `src/dfir_ogre_plugin_windows/lnk.py`
  - Uses the shared always-usable timezone policy in `LnkBatched`.

### Task 1: Shared SYSTEM Timezone-or-UTC Policy

**Files:**
- Create: `tests/test_system_timezone.py`
- Modify: `src/dfir_ogre_plugin_windows/system_timezone.py`

**Interfaces:**
- Consumes: `resolve_system_timezone(system_entries: List[BatchEntry], snapshot: Optional[str], report: RunReport) -> Optional[ZoneInfo]`.
- Produces: `resolve_system_timezone_or_utc(system_entries: List[BatchEntry], snapshot: Optional[str], report: RunReport) -> tzinfo`, which never returns `None`.

- [ ] **Step 1: Write the failing shared-policy tests**

Create `tests/test_system_timezone.py` with:

```python
import os
from datetime import timezone
from unittest import TestCase

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OutputConfiguration,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows import system_timezone

from . import BASE_TEMP_FOLDER


DATA_FOLDER = os.path.join("tests", "data")


class TestSystemTimezoneFallback(TestCase):
    def resolver(self):
        self.assertTrue(
            hasattr(system_timezone, "resolve_system_timezone_or_utc"),
            "shared timezone fallback policy is not implemented",
        )
        return getattr(system_timezone, "resolve_system_timezone_or_utc")

    def test_missing_system_reports_warns_and_returns_utc(self):
        report = RunReport()

        with self.assertLogs(system_timezone.__name__, level="WARNING") as logs:
            timezone_info = self.resolver()([], "vss-1", report)

        self.assertIs(timezone_info, timezone.utc)
        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'vss-1'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertIn("interpreting local timestamps as UTC", logs.output[0])

    def test_valid_system_returns_source_timezone_without_warning(self):
        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    "unused",
                    BASE_TEMP_FOLDER,
                    with_timeline=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "vss-1"
        metadata.original_filename = r"C:\Windows\System32\config\SYSTEM"
        entry = BatchEntry(
            os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat"),
            run_config,
            metadata,
        )
        report = RunReport()

        with self.assertNoLogs(system_timezone.__name__, level="WARNING"):
            timezone_info = self.resolver()([entry], "vss-1", report)

        self.assertEqual(str(timezone_info), "Europe/Paris")
        self.assertEqual(report.num_errors, 0)
        self.assertIsNone(report.last_error)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_system_timezone -v
```

Expected: both tests fail at the `hasattr` assertion because `resolve_system_timezone_or_utc` does not exist. There must be no import or fixture error.

- [ ] **Step 3: Implement the shared fallback policy**

In `src/dfir_ogre_plugin_windows/system_timezone.py`, replace the import/header block with:

```python
import logging
import os
from datetime import timezone, tzinfo
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dfir_ogre_common import BatchEntry, Registry, RunReport

from dfir_ogre_plugin_windows.common import win_tz_to_iana


logger = logging.getLogger(__name__)
```

Add immediately after `resolve_system_timezone`:

```python
def resolve_system_timezone_or_utc(
    system_entries: List[BatchEntry],
    snapshot: Optional[str],
    report: RunReport,
) -> tzinfo:
    timezone_info = resolve_system_timezone(system_entries, snapshot, report)
    if timezone_info is not None:
        return timezone_info

    logger.warning(
        "Unable to resolve source timezone for VSS snapshot %r; "
        "interpreting local timestamps as UTC",
        snapshot,
    )
    return timezone.utc
```

Do not change `resolve_system_timezone`: it remains the sole source of detailed `RunReport.errors`.

- [ ] **Step 4: Run the shared-policy tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_system_timezone -v
```

Expected: both tests pass and the command ends with `OK`.

- [ ] **Step 5: Check and commit Task 1**

Run:

```bash
git diff --check -- tests/test_system_timezone.py src/dfir_ogre_plugin_windows/system_timezone.py
git add tests/test_system_timezone.py src/dfir_ogre_plugin_windows/system_timezone.py
git commit -m "Add shared registry timezone fallback policy"
```

Expected: the commit contains only the shared helper and its tests; `uv.lock` remains modified and unstaged.

### Task 2: Batch Scheduled Tasks and Normalize Registration Dates

**Files:**
- Modify: `tests/hive/test_scheduled_task.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/scheduled_task.py`
- Modify: `configuration/registry/scheduled_task.xml`

**Interfaces:**
- Consumes: `resolve_system_timezone_or_utc(...) -> tzinfo`, `BatchEntry.metadata.vss`, and `BatchEntry.metadata.original_filename`.
- Produces: `group_scheduled_task_inputs(input_files: List[BatchEntry]) -> Dict[Optional[str], ScheduledTaskBatch]` and `registration_date_to_utc(registration_date: str, source_timezone: tzinfo) -> datetime`.
- Changes: `RegScheduledTask.parse` to the `OgreBatchedPlugin` signature `parse(input_files: List[BatchEntry], plugin_file: str) -> RunReport`.

- [ ] **Step 1: Write the failing Scheduled Task unit and batch regressions**

In `tests/hive/test_scheduled_task.py`, add these imports:

```python
import time
from datetime import timezone
from zoneinfo import ZoneInfo

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OgreBatchedPlugin,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import RegScheduledTask
from dfir_ogre_plugin_windows.registry import scheduled_task
from dfir_ogre_plugin_windows.registry.scheduled_task import decode_task_action
```

Retain the existing `json`, `os`, `TestCase`, constants, and `bstr` declarations, removing their duplicate old imports.

Add these methods to `TestScheduledTask` before the integration test:

```python
    def scheduled_helper(self, name: str):
        self.assertTrue(
            hasattr(scheduled_task, name),
            f"Scheduled Task helper {name} is not implemented",
        )
        return getattr(scheduled_task, name)

    def test_groups_software_and_system_hives_by_vss(self):
        run_config = RunConfiguration(
            [OutputConfiguration("unused", TEMP_FOLDER, with_timeline=False)]
        )

        def entry(file: str, original_filename: str, vss: str) -> BatchEntry:
            metadata = Metadata("test")
            metadata.original_filename = original_filename
            metadata.vss = vss
            return BatchEntry(file, run_config, metadata)

        grouped = self.scheduled_helper("group_scheduled_task_inputs")(
            [
                entry("software-2", r"C:\Windows\System32\config\SOFTWARE", "vss-2"),
                entry("system-1", r"C:\Windows\System32\config\SYSTEM", "vss-1"),
                entry("software-1a", r"C:\Windows\System32\config\SOFTWARE", "vss-1"),
                entry("software-1b", "SOFTWARE.dat", "vss-1"),
                entry("system-2", r"C:\Windows\System32\config\SYSTEM", "vss-2"),
                entry("ignored", r"C:\Windows\System32\config\SAM", "vss-1"),
            ]
        )

        self.assertEqual(
            [item.file for item in grouped["vss-1"].software_entries],
            ["software-1a", "software-1b"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-1"].system_entries],
            ["system-1"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-2"].software_entries],
            ["software-2"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-2"].system_entries],
            ["system-2"],
        )

    def test_registration_date_uses_source_timezone_not_process_timezone(self):
        normalize = self.scheduled_helper("registration_date_to_utc")
        original_timezone = os.environ.get("TZ")
        results = []
        try:
            if not hasattr(time, "tzset"):
                self.skipTest("process timezone switching requires time.tzset")
            for process_timezone in ("UTC", "America/New_York"):
                os.environ["TZ"] = process_timezone
                time.tzset()
                results.append(
                    normalize(
                        "2024-07-01T12:00:00",
                        ZoneInfo("Europe/Paris"),
                    ).isoformat()
                )
        finally:
            if original_timezone is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_timezone
            if hasattr(time, "tzset"):
                time.tzset()

        self.assertEqual(
            results,
            ["2024-07-01T10:00:00+00:00", "2024-07-01T10:00:00+00:00"],
        )

    def test_registration_date_honors_embedded_offset(self):
        normalized = self.scheduled_helper("registration_date_to_utc")(
            "2024-01-15T12:00:00+05:30",
            ZoneInfo("Europe/Paris"),
        )

        self.assertEqual(normalized.isoformat(), "2024-01-15T06:30:00+00:00")

    def test_registration_date_uses_naive_utc_fallback(self):
        normalized = self.scheduled_helper("registration_date_to_utc")(
            "2024-01-15T12:00:00",
            timezone.utc,
        )

        self.assertEqual(normalized.isoformat(), "2024-01-15T12:00:00+00:00")
```

Update `test_scheduled_task` to construct matching SOFTWARE/SYSTEM `BatchEntry` objects and call the batched interface:

```python
        software_metadata = Metadata("test")
        software_metadata.vss = "test_vss"
        software_metadata.original_filename = r"C:\Windows\System32\config\SOFTWARE"
        system_metadata = Metadata("test")
        system_metadata.vss = "test_vss"
        system_metadata.original_filename = r"C:\Windows\System32\config\SYSTEM"

        parser = RegScheduledTask()
        self.assertIsInstance(parser, OgreBatchedPlugin)
        self.assertEqual("RegScheduledTask", parser.description().command)

        run_config = RunConfiguration([output_config])
        entries = [
            BatchEntry(input_file, run_config, software_metadata),
            BatchEntry(
                os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat"),
                run_config,
                system_metadata,
            ),
        ]
        report = parser.parse(entries, plugin_file)
        self.assertEqual(None, report.last_error)
```

After loading `records`, add:

```python
        maps_data = next(
            record["data"]
            for record in records
            if record["data"].get("task")
            == r"\Microsoft\Windows\Maps\MapsUpdateTask"
            and "registration_date_local" in record["data"]
        )
        self.assertEqual(
            maps_data["registration_date_local"],
            "2014-11-04T23:00:00.000000+00:00",
        )
```

Add the missing-SYSTEM integration regression:

```python
    def test_scheduled_task_without_system_reports_and_uses_utc_fallback(self):
        plugin_file = os.path.join(CONF_FOLDER, "scheduled_task.xml")
        software_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")
        base_output_name = "scheduled_task_without_system"
        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".scheduled_tasks.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=True,
                    include_empty=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "missing-system"
        metadata.original_filename = r"C:\Windows\System32\config\SOFTWARE"
        parser = RegScheduledTask()
        self.assertIsInstance(parser, OgreBatchedPlugin)

        with self.assertLogs(
            "dfir_ogre_plugin_windows.system_timezone",
            level="WARNING",
        ) as logs:
            report = parser.parse(
                [BatchEntry(software_file, run_config, metadata)],
                plugin_file,
            )

        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'missing-system'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 530)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]
        maps_data = next(
            record["data"]
            for record in records
            if record["data"].get("task")
            == r"\Microsoft\Windows\Maps\MapsUpdateTask"
            and "registration_date_local" in record["data"]
        )
        self.assertEqual(
            maps_data["registration_date_local"],
            "2014-11-05T00:00:00.000000+00:00",
        )
```

- [ ] **Step 2: Run the Scheduled Task tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.hive.test_scheduled_task -v
```

Expected: the new helper tests fail at explicit assertions because the grouping and normalization helpers do not exist, and both integration tests fail at `assertIsInstance` because `RegScheduledTask` is not yet batched. Existing task-action tests continue to pass.

- [ ] **Step 3: Implement Scheduled Task grouping, batching, and normalization**

In `src/dfir_ogre_plugin_windows/registry/scheduled_task.py`, change the top-level imports to include:

```python
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Dict, List, Optional
from uuid import UUID

from dateutil import parser as date_parser
from dfir_ogre_common import (
    BatchEntry,
    OgreBatchedPlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RegValue,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc, value
from dfir_ogre_plugin_windows.security_descriptor import SecurityDescriptor
from dfir_ogre_plugin_windows.system_timezone import (
    entry_snapshot,
    entry_source_basename,
    is_system_hive,
    resolve_system_timezone_or_utc,
)
```

Insert before `RegScheduledTask`:

```python
@dataclass
class ScheduledTaskBatch:
    software_entries: List[BatchEntry]
    system_entries: List[BatchEntry]


def is_software_hive(entry: BatchEntry) -> bool:
    filename = entry_source_basename(entry)
    return (
        filename == "software"
        or filename.startswith("software.")
        or filename.startswith("software_")
    )


def group_scheduled_task_inputs(
    input_files: List[BatchEntry],
) -> Dict[Optional[str], ScheduledTaskBatch]:
    grouped: Dict[Optional[str], ScheduledTaskBatch] = {}
    for entry in input_files:
        snapshot = entry_snapshot(entry)
        batch = grouped.setdefault(snapshot, ScheduledTaskBatch([], []))
        if is_system_hive(entry):
            batch.system_entries.append(entry)
        elif is_software_hive(entry):
            batch.software_entries.append(entry)
    return grouped


def registration_date_to_utc(
    registration_date: str,
    source_timezone: tzinfo,
) -> datetime:
    parsed = date_parser.parse(registration_date)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone, fold=0)
    return parsed.astimezone(timezone.utc)
```

Replace the current `RegScheduledTask` declaration and `parse` method with:

```python
class RegScheduledTask(OgreBatchedPlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegScheduledTask",
            "Get scheduled tasks from the Software hive",
        )

    def parse(
        self,
        input_files: List[BatchEntry],
        plugin_file: str,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()

        for snapshot, batch in group_scheduled_task_inputs(input_files).items():
            if not batch.software_entries:
                continue

            timezone_info = resolve_system_timezone_or_utc(
                batch.system_entries,
                snapshot,
                report,
            )
            for entry in batch.software_entries:
                self.parse_software(entry, plugin_config, timezone_info, report)

        return report

    def parse_software(
        self,
        entry: BatchEntry,
        plugin_config: PluginConfiguration,
        timezone_info: tzinfo,
        report: RunReport,
    ) -> None:
        key_paths = [
            "\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache",
            "\\HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows NT\\CurrentVersion\\Schedule",
        ]

        try:
            reg = Registry.load(entry.file, "\\HKLM\\SOFTWARE")
        except Exception as e:
            report.add_error(f"{e}")
            return

        with Output(entry.run_config, plugin_config, entry.metadata) as output:
            try:
                for key_path in key_paths:
                    for key in reg.glob_keys(key_path):
                        self.parse_key(output, key, report, timezone_info)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())
```

Change `parse_key` to accept the timezone:

```python
    def parse_key(
        self,
        output: Output,
        task_cache_key: RegKey,
        report: RunReport,
        timezone_info: tzinfo,
    ):
```

Replace the existing registration-date block with:

```python
            registration_date_local = task.value_data("Date")
            if registration_date_local:
                registration_date = registration_date_to_utc(
                    registration_date_local,
                    timezone_info,
                )
                tuple.add("registration_date_local", value(registration_date))
```

In `configuration/registry/scheduled_task.xml`, replace the root element with:

```xml
<plugin parser="RegScheduledTask" batch="true" file_encoding="UTF_8">
```

- [ ] **Step 4: Run the Scheduled Task tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.hive.test_scheduled_task -v
```

Expected: all Scheduled Task unit and integration tests pass. The valid SYSTEM fixture produces the Europe/Paris-derived UTC registration timestamp; the missing-SYSTEM run records one error, logs one warning, emits 530 lines, and uses naive UTC.

- [ ] **Step 5: Run parser-registration/configuration tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_configuration -v
```

Expected: all parser registration and timeline-field checks pass with `RegScheduledTask` registered as a batched parser.

- [ ] **Step 6: Check and commit Task 2**

Run:

```bash
git diff --check -- tests/hive/test_scheduled_task.py src/dfir_ogre_plugin_windows/registry/scheduled_task.py configuration/registry/scheduled_task.xml
git add tests/hive/test_scheduled_task.py src/dfir_ogre_plugin_windows/registry/scheduled_task.py configuration/registry/scheduled_task.xml
git commit -m "Batch Scheduled Tasks with source timezone"
```

Expected: the commit contains only the Scheduled Task parser, configuration, and tests; `uv.lock` remains unstaged.

### Task 3: Apply the Shared Fallback to ShellBag and Batched LNK

**Files:**
- Modify: `tests/hive/test_shell_bag.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/shellbag.py`
- Modify: `tests/test_lnk.py`
- Modify: `src/dfir_ogre_plugin_windows/lnk.py`

**Interfaces:**
- Consumes: `resolve_system_timezone_or_utc(...) -> tzinfo` from Task 1.
- Produces: unchanged ShellBag and LNK record schemas, with local FAT timestamps labeled UTC rather than null when SYSTEM resolution fails.

- [ ] **Step 1: Write the failing ShellBag missing-SYSTEM regression**

Add to `TestShellBag` in `tests/hive/test_shell_bag.py`:

```python
    def test_shell_bag_without_system_reports_and_uses_utc_fallback(self):
        plugin_file = os.path.join(CONF_FOLDER, "shell_bag.xml")
        usrclass_file = os.path.join(DATA_FOLDER, "hive", "UsrClass_shell.dat")
        base_output_name = "shell_bag_without_system"
        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".shellbags.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "missing-system"
        metadata.original_filename = (
            r"C:\Users\Administrator\AppData\Local\Microsoft\Windows\UsrClass.dat"
        )

        with self.assertLogs(
            "dfir_ogre_plugin_windows.system_timezone",
            level="WARNING",
        ) as logs:
            report = RegShellBag().parse(
                [BatchEntry(usrclass_file, run_config, metadata)],
                plugin_file,
            )

        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'missing-system'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 14)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]
        records_by_key = {record["key_path"]: record for record in records}
        leaf = records_by_key[
            "HKCU\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\BagMRU\\3\\0\\0\\1\\0"
        ]
        self.assertIn("modification_time", leaf)
        self.assertEqual(
            leaf["modification_time"],
            "2038-11-06T10:17:10.000000+00:00",
        )
```

- [ ] **Step 2: Write the failing batched LNK missing-SYSTEM regression**

Add to `TestLnkFatTimestamps` in `tests/test_lnk.py`:

```python
    def test_batched_lnk_without_system_reports_and_uses_utc_fallback(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        lnk_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_without_system"
        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "missing-system"
        metadata.original_filename = r"C:\Users\test\desktop.lnk"
        parsed_lnk = {
            "status": "success",
            "lnk": [
                {
                    "status": "success",
                    "header": {
                        "modification_time": "2024-06-29T17:42:58+00:00"
                    },
                    "target": {
                        "items": [
                            {
                                "primary_name": "target.txt",
                                "modification_time": "2024-06-29T17:42:58+00:00",
                            }
                        ]
                    },
                }
            ],
        }

        with self.assertLogs(
            "dfir_ogre_plugin_windows.system_timezone",
            level="WARNING",
        ) as logs, patch(
            "dfir_ogre_plugin_windows.lnk.parse_jumplist",
            return_value=parsed_lnk,
        ):
            report = LnkBatched().parse(
                [BatchEntry(lnk_file, run_config, metadata)],
                plugin_file,
            )

        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'missing-system'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 1)
        self.assertEqual(
            parsed_lnk["lnk"][0]["target"]["items"][0]["modification_time"],
            "2024-06-29T17:42:58+00:00",
        )

        with open(output_file) as fp:
            record = json.loads(fp.readline())
        self.assertEqual(
            record["target"]["items"][0]["modification_time"],
            "2024-06-29T17:42:58.000000+00:00",
        )
```

The controlled `parse_jumplist` result is necessary to isolate the DOS/FAT target-item timestamp from unrelated binary-decoder behavior; assertions remain on parser output and report state.

- [ ] **Step 3: Run both new regressions and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.hive.test_shell_bag.TestShellBag.test_shell_bag_without_system_reports_and_uses_utc_fallback \
  tests.test_lnk.TestLnkFatTimestamps.test_batched_lnk_without_system_reports_and_uses_utc_fallback \
  -v
```

Expected: both tests fail because the current consumers call the nullable resolver, emit no fallback warning, and null the affected local timestamp.

- [ ] **Step 4: Route ShellBag and batched LNK through the shared policy**

In `src/dfir_ogre_plugin_windows/registry/shellbag.py`, replace the resolver import:

```python
    resolve_system_timezone_or_utc,
```

and change `resolve_shellbag_timezone` to:

```python
def resolve_shellbag_timezone(
    system_entries: List[BatchEntry],
    snapshot: Optional[str],
    report: RunReport,
) -> tzinfo:
    return resolve_system_timezone_or_utc(system_entries, snapshot, report)
```

The returned object can also be `datetime.timezone.utc`; therefore update the annotations used to pass it through ShellBag parsing from `Optional[ZoneInfo]`/`ZoneInfo` to `tzinfo`, importing `tzinfo` from `datetime`. Keep `ShellItem.add_fat_datetime`'s defensive `None` check for callers outside the batched path.

In `src/dfir_ogre_plugin_windows/lnk.py`, replace the resolver import:

```python
    resolve_system_timezone_or_utc,
```

and replace the call inside `LnkBatched.parse` with:

```python
            timezone_info = resolve_system_timezone_or_utc(
                batch.system_entries,
                snapshot,
                report,
            )
```

Change `LnkBatched.parse_entry`'s `timezone_info` annotation to `tzinfo`, importing `tzinfo` from `datetime`. Keep `lnk_fat_datetime_to_utc(..., None)` supported for the separate non-batched `Lnk` parser and its existing tests.

- [ ] **Step 5: Run ShellBag and LNK tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.hive.test_shell_bag tests.test_lnk -v
```

Expected: all ShellBag and LNK tests pass. Missing-SYSTEM cases retain one report error, log one warning, continue output, and preserve their local wall-clock fields as UTC.

- [ ] **Step 6: Check and commit Task 3**

Run:

```bash
git diff --check -- tests/hive/test_shell_bag.py src/dfir_ogre_plugin_windows/registry/shellbag.py tests/test_lnk.py src/dfir_ogre_plugin_windows/lnk.py
git add tests/hive/test_shell_bag.py src/dfir_ogre_plugin_windows/registry/shellbag.py tests/test_lnk.py src/dfir_ogre_plugin_windows/lnk.py
git commit -m "Use UTC fallback for batched local timestamps"
```

Expected: the commit contains only ShellBag/LNK source and test files; `uv.lock` remains unstaged.

### Task 4: Final Verification and Scope Audit

**Files:**
- Verify only; no additional files should change.

**Interfaces:**
- Consumes: all behavior implemented in Tasks 1–3.
- Produces: fresh test and Git evidence that the agreed behavior is complete and unrelated work remains untouched.

- [ ] **Step 1: Run all focused timezone and parser tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_system_timezone \
  tests.hive.test_scheduled_task \
  tests.hive.test_shell_bag \
  tests.test_lnk \
  tests.test_configuration \
  -v
```

Expected: every focused test passes and the command ends with `OK`.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
.venv/bin/python -m unittest discover -v
```

Expected: the complete suite ends with `OK`, with no failures or errors.

- [ ] **Step 3: Audit formatting, commits, and unrelated changes**

Run:

```bash
git diff --check
git status --short
git log -4 --oneline
```

Expected: `git diff --check` emits nothing; only the pre-existing unstaged `uv.lock` modification remains; recent history contains the design checkpoint and the three scoped implementation commits.
