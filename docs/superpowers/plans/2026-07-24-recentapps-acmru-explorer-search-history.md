# RecentApps, ACMru, and Explorer Search History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct RecentApps and Windows XP ACMru extraction, add a dedicated Windows 7+ Explorer Search History plugin for the `WordWheelQuery` artifact, and validate the supported formats with two small public registry hives.

**Architecture:** Keep one plugin per registry artifact and preserve the existing `RegRecentApp` and `RegAcMru` commands. Add `RegExplorerSearchHistory` as a separate plugin for the `WordWheelQuery` key because its registry path, binary encoding, ordering, and OS scope differ from ACMru; all three plugins continue to use `dfir_ogre_common.Registry`, `Record`, `Output`, and XML output mappings.

**Tech Stack:** Python 3.10, `unittest`, `dfir_ogre_common` registry/output APIs, XML plugin configurations, binary Windows registry hives.

## Global Constraints

- Keep `RegRecentApp` and `RegAcMru` command names and data types available.
- Implement Explorer Search History as the additive `RegExplorerSearchHistory` command with `data_type="explorer_search_history"`; retain `WordWheelQuery` as the underlying registry artifact name.
- Store both downloaded fixtures locally; tests must not access the network.
- Record each fixture's immutable source URL, byte size, SHA-256,
  decompression status, and complete locally redistributed upstream license.
- Never stringify an absent registry value as `"None"`.
- Emit the registry key LastWrite time only for the newest entry in ACMru and WordWheelQuery.
- Do not infer timestamps for older MRU entries.
- Do not combine ACMru and WordWheelQuery behind a generic search-history parser.
- Add no runtime dependency.

---

### Task 1: Add Reproducible Public Hive Fixtures

**Files:**
- Create: `tests/data/hive/NTUSER_RECENT_APPS.dat`
- Create: `tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat`
- Create: `tests/data/hive/SOURCES.md`
- Create: `tests/data/hive/licenses/regipy-MIT.txt`
- Create: `tests/data/hive/licenses/plaso-Apache-2.0.txt`

**Interfaces:**
- Consumes: the already downloaded `/tmp/regipy-transactions-NTUSER.DAT` and `/tmp/plaso-NTUSER-WIN7.DAT` files
- Produces: stable local paths consumed by `tests/hive/test_recent_app.py` and `tests/hive/test_explorer_search_history.py`

- [ ] **Step 1: Verify the downloaded source artifacts before copying**

Run:

```bash
sha256sum \
  /tmp/regipy-transactions-NTUSER.DAT \
  /tmp/plaso-NTUSER-WIN7.DAT
stat -c '%n %s' \
  /tmp/regipy-transactions-NTUSER.DAT \
  /tmp/plaso-NTUSER-WIN7.DAT
```

Expected:

```text
e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1  /tmp/regipy-transactions-NTUSER.DAT
672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03  /tmp/plaso-NTUSER-WIN7.DAT
/tmp/regipy-transactions-NTUSER.DAT 1048576
/tmp/plaso-NTUSER-WIN7.DAT 1310720
```

If either temporary file is absent, download its documented upstream file,
decompress the regipy XZ source, and repeat this exact verification before
continuing.

- [ ] **Step 2: Copy the verified binary fixtures into the repository**

Run:

```bash
install -m 0644 \
  /tmp/regipy-transactions-NTUSER.DAT \
  tests/data/hive/NTUSER_RECENT_APPS.dat
install -m 0644 \
  /tmp/plaso-NTUSER-WIN7.DAT \
  tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat
```

- [ ] **Step 3: Add fixture provenance documentation**

Create `tests/data/hive/SOURCES.md` with:

```markdown
# Registry hive fixture sources

## `NTUSER_RECENT_APPS.dat`

- Source:
  <https://raw.githubusercontent.com/mkorman90/regipy/f78c55ae67ad7672660a255569c20650de5564de/regipy_tests/data/transactions_NTUSER.DAT.xz>
- Upstream project: <https://github.com/mkorman90/regipy>
- Upstream commit: `f78c55ae67ad7672660a255569c20650de5564de`
- Upstream license: MIT; the complete copyright and permission notice is
  redistributed in [`licenses/regipy-MIT.txt`](licenses/regipy-MIT.txt).
- Stored form: XZ source decompressed once; registry hive bytes are otherwise
  unmodified.
- Size: 1,048,576 bytes
- SHA-256:
  `e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Search\RecentApps`

## `NTUSER_WORD_WHEEL_QUERY.dat`

- Source:
  <https://raw.githubusercontent.com/log2timeline/plaso/4ea03ef9a48dad5284c371ac9b537a184b3eea9c/test_data/NTUSER-WIN7.DAT>
- Upstream project: <https://github.com/log2timeline/plaso>
- Upstream commit: `4ea03ef9a48dad5284c371ac9b537a184b3eea9c`
- Upstream license: Apache License 2.0; the complete license is redistributed
  in
  [`licenses/plaso-Apache-2.0.txt`](licenses/plaso-Apache-2.0.txt).
- Upstream `4ea03ef9a48dad5284c371ac9b537a184b3eea9c` contains no `NOTICE` file.
- Stored form: raw upstream registry hive, unmodified.
- Size: 1,310,720 bytes
- SHA-256:
  `672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03`
- Relevant artifact:
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery`
```

- [ ] **Step 4: Verify repository copies byte-for-byte**

Run:

```bash
sha256sum \
  tests/data/hive/NTUSER_RECENT_APPS.dat \
  tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat
```

Expected: the hashes exactly match Step 1.

- [ ] **Step 5: Commit the fixture baseline**

```bash
git add \
  tests/data/hive/NTUSER_RECENT_APPS.dat \
  tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat \
  tests/data/hive/SOURCES.md \
  tests/data/hive/licenses/regipy-MIT.txt \
  tests/data/hive/licenses/plaso-Apache-2.0.txt
git commit -m "Add search history registry fixtures"
```

---

### Task 2: Correct RecentApps Fields and Add Positive Coverage

**Files:**
- Modify: `tests/hive/test_recent_app.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/recent_app.py`
- Modify: `configuration/registry/recent_app.xml`

**Interfaces:**
- Consumes: `RegKey.value_data(name) -> object | None` for `AppPath`, `Path`, and `Arguments`
- Produces: `recent_app_record(key, item=None) -> Record` with raw `path`, separate `arguments`, and application-level `app_path`

- [ ] **Step 1: Make the focused RecentApps test express the corrected contract**

In `test_one_record_is_emitted_per_recent_item`, change the first item's
arguments to `"/open"` and remove `Arguments` from the second item. Add
`"AppPath": r"C:\Program Files\Forensic\forensic.exe"` to the application
values.

After the existing GUID and display-name assertions, add:

```python
self.assertEqual(
    [record["path"] for record in records],
    [
        r"C:\evidence\first.txt",
        r"C:\evidence\second.txt",
    ],
)
self.assertEqual(records[0]["arguments"], "/open")
self.assertIsNone(records[1].get("arguments"))
self.assertTrue(
    all(
        record["app_path"] == r"C:\Program Files\Forensic\forensic.exe"
        for record in records
    )
)
self.assertNotIn("None", json.dumps(records))
```

- [ ] **Step 2: Replace the zero-row real-hive assertion with positive validation**

Rename `test_recent_app` to
`test_recent_app_public_hive_emits_application_record`, use
`NTUSER_RECENT_APPS.dat`, retain `include_empty=True`, and replace the
zero-line assertion and commented inspection block with:

```python
self.assertEqual(report.last_error, None)
self.assertEqual(
    report.output_reports[0].file_reports[0].num_lines,
    1,
)

with open(output_file, encoding="utf-8") as output:
    records = [json.loads(line) for line in output]

self.assertEqual(len(records), 1)
record = records[0]
self.assertEqual(
    record["guid_app"],
    "da8dc440-0faa-417d-8af4-8f4b2eb50409",
)
self.assertEqual(record["app_id"], r"D:\setup64.exe")
self.assertEqual(record["launch_count"], 1)
self.assertEqual(
    record["app_last_accessed_time"],
    "2017-07-12T07:34:32.178000+00:00",
)
self.assertIsNone(record["guid_file"])
self.assertIsNone(record["path"])
self.assertIsNone(record["arguments"])
```

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
uv run python -m unittest \
  tests.hive.test_recent_app.RecentApp.test_one_record_is_emitted_per_recent_item \
  tests.hive.test_recent_app.RecentApp.test_recent_app_public_hive_emits_application_record \
  -v
```

Expected: the item test fails because `path` contains arguments or `"None"`
and because `arguments` and `app_path` are absent. The public-hive test also
fails until `arguments` is declared in the configuration when
`include_empty=True`.

- [ ] **Step 4: Implement the minimal RecentApps field correction**

In `recent_app_record`, add application path immediately after `app_id`:

```python
app_path = key.value_data("AppPath")
record.add("app_path", value(app_path))
```

Replace the item path/argument concatenation with:

```python
path = item.value_data("Path")
record.add("path", value(path))

arguments = item.value_data("Arguments")
record.add("arguments", value(arguments))
```

Update the description to:

```python
return PluginDescription(
    "RegRecentApp",
    "Get applications and files recorded by Windows 10 RecentApps "
    "(introduced in 1607 and removed in 1709) from NTUSER.DAT",
)
```

- [ ] **Step 5: Update the RecentApps XML contract**

Change the description bullet about command lines to:

```text
- Preserves each recent file path and its optional arguments as separate fields.
```

Insert after `app_id`:

```xml
      <field
        input="app_path"
        parser="String"
        qualifier="PATH"
        description="Path of the application executable"
      />
```

Change the `path` description to:

```xml
description="Path of the recently accessed item"
```

Insert after `path`:

```xml
      <field
        input="arguments"
        parser="String"
        description="Optional arguments associated with the recently accessed item"
      />
```

- [ ] **Step 6: Run the RecentApps tests and verify GREEN**

Run:

```bash
uv run python -m unittest tests.hive.test_recent_app -v
```

Expected: both tests pass with no errors.

- [ ] **Step 7: Commit the RecentApps correction**

```bash
git add \
  tests/hive/test_recent_app.py \
  src/dfir_ogre_plugin_windows/registry/recent_app.py \
  configuration/registry/recent_app.xml
git commit -m "Correct RecentApps path extraction"
```

---

### Task 3: Correct Legacy ACMru Ordering and Timestamp Provenance

**Files:**
- Modify: `tests/hive/test_acmru.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/acmru.py`
- Modify: `configuration/registry/acmru.xml`

**Interfaces:**
- Consumes: non-empty ASCII decimal registry value names below an ACMru
  category key
- Produces: deterministic records with `search_request: str`, `order_index: int`, `category: str`, and `key_modif_time` only for index zero

- [ ] **Step 1: Replace the zero-row ACMru test with focused key behavior tests**

Replace `tests/hive/test_acmru.py` with:

```python
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import Record, RunReport, Value

from dfir_ogre_plugin_windows import RegAcMru


def registry_value(name: str, data: str):
    reg_value = Mock()
    reg_value.name.return_value = name
    reg_value.data.return_value = data
    return reg_value


def acmru_key(values):
    key = Mock()
    key.name = "5603"
    key.path = r"HKCU\Software\Microsoft\Search Assistant\ACMru\5603"
    key.mtime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    key.values.return_value = values

    security = Record()
    security.add("owner_sid", Value.String("S-1-5-21-test"))
    key.security_descriptor.to_record.return_value = security
    return key


class TestAcmru(TestCase):
    def test_values_are_sorted_and_only_newest_has_timestamp(self):
        key = acmru_key(
            [
                registry_value("002", "third"),
                registry_value("000", "newest"),
                registry_value("001", "second"),
            ]
        )
        output = Mock()
        report = RunReport()

        RegAcMru().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertIsNone(report.last_error)
        self.assertEqual(
            [record["search_request"] for record in records],
            ["newest", "second", "third"],
        )
        self.assertEqual(
            [record["order_index"] for record in records],
            [0, 1, 2],
        )
        self.assertTrue(all(record["category"] == "5603" for record in records))
        self.assertEqual(
            records[0]["key_modif_time"],
            "2025-01-02T03:04:05.000000+00:00",
        )
        self.assertNotIn("key_modif_time", records[1])
        self.assertNotIn("key_modif_time", records[2])

    def test_invalid_value_name_is_reported_without_losing_valid_values(self):
        key = acmru_key(
            [
                registry_value("invalid", "skip me"),
                registry_value("000", "keep me"),
            ]
        )
        output = Mock()
        report = RunReport()

        RegAcMru().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertEqual([record["search_request"] for record in records], ["keep me"])
        self.assertIn("invalid ACMru value name", report.last_error)
        self.assertIn("invalid", report.last_error)
```

- [ ] **Step 2: Run the ACMru tests and verify RED**

Run:

```bash
uv run python -m unittest tests.hive.test_acmru -v
```

Expected: both tests fail because the current parser preserves enumeration
order, emits string indices, omits `category`, timestamps every value, and
accepts the malformed name.

- [ ] **Step 3: Implement deterministic per-value parsing**

Replace `parse_key` with:

```python
def parse_key(self, key: RegKey, output: Output, report: RunReport):
    try:
        self._parse_key(key, output, report)
    except Exception as error:
        report.add_error(f"{key.path}: {error}")

def _parse_key(self, key: RegKey, output: Output, report: RunReport):
    indexed_values = []
    for reg_value in key.values():
        value_name = reg_value.name()
        if (
            not isinstance(value_name, str)
            or not value_name
            or not value_name.isascii()
            or not value_name.isdecimal()
        ):
            report.add_error(
                f"{key.path}: invalid ACMru value name {value_name!r}"
            )
            continue
        order_index = int(value_name, 10)
        indexed_values.append((order_index, reg_value))

    for order_index, reg_value in sorted(
        indexed_values,
        key=lambda item: item[0],
    ):
        record = Record()
        record.add("search_request", value(reg_value.data()))
        record.add("order_index", value(order_index))
        record.add("category", value(key.name))
        record.add("key_path", value(key.path))
        if order_index == 0:
            record.add("key_modif_time", value(key.mtime))
        record.add(
            "key_security",
            Value.Object(key.security_descriptor.to_record()),
        )
        output.write(record)
```

Remove the unused `datetime` and `timezone` imports and delete `parse_date` and
`parse_int`. Change the description to:

```python
return PluginDescription(
    "RegAcMru",
    "Get Windows XP Search Assistant history from NTUSER.DAT",
)
```

- [ ] **Step 4: Update the ACMru XML contract**

Replace the mapping description with:

```text
Extracts Windows XP Search Assistant entries from the NTUSER.DAT hive.

- Retrieves search queries from category subkeys such as 5603 and 5604.
- Emits entries in deterministic most-recent-first numeric order.
- Associates the category key LastWrite time only with index 000.
```

Change `order_index` to:

```xml
      <field
        input="order_index"
        parser="Int"
        description="Zero-based position of the query in the category MRU"
      />
```

Insert after `order_index`:

```xml
      <field
        input="category"
        parser="String"
        description="Windows XP Search Assistant category identifier"
      />
```

- [ ] **Step 5: Run ACMru and configuration tests and verify GREEN**

Run:

```bash
uv run python -m unittest \
  tests.hive.test_acmru \
  tests.test_configuration \
  -v
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 6: Commit the ACMru correction**

```bash
git add \
  tests/hive/test_acmru.py \
  src/dfir_ogre_plugin_windows/registry/acmru.py \
  configuration/registry/acmru.xml
git commit -m "Correct ACMru ordering and timestamps"
```

---

### Task 4: Add the Dedicated Explorer Search History Plugin

**Files:**
- Create: `src/dfir_ogre_plugin_windows/registry/explorer_search_history.py`
- Create: `configuration/registry/explorer_search_history.xml`
- Create: `tests/hive/test_explorer_search_history.py`
- Modify: `src/dfir_ogre_plugin_windows/__init__.py`
- Modify: `tests/test_configuration.py`

**Interfaces:**
- Produces: `parse_mru_list_ex(data: bytes) -> list[int]`
- Produces: `decode_word_wheel_value(data: bytes) -> str`
- Produces: `RegExplorerSearchHistory.parse_key(key, output, report) -> None`
- Produces: registered command `RegExplorerSearchHistory` and data type `explorer_search_history`

- [ ] **Step 1: Add the Explorer Search History XML configuration first**

Copy `configuration/registry/acmru.xml` to
`configuration/registry/explorer_search_history.xml`, then make these exact changes:

```xml
<plugin parser="RegExplorerSearchHistory" file_encoding="UTF_8">
  <mapping data_type="explorer_search_history">
```

Use this description:

```text
Extracts Windows 7 and later Explorer search history from WordWheelQuery in
the NTUSER.DAT hive.

- Decodes UTF-16LE registry values.
- Uses MRUListEx to emit most-recent-first search order.
- Associates the key LastWrite time only with the newest search.
```

Declare these fields before the unchanged registry metadata fields:

```xml
      <field
        input="search_request"
        parser="String"
        description="Search query entered in Windows Explorer"
      />
      <field
        input="order_index"
        parser="Int"
        description="Zero-based position in MRUListEx, where zero is newest"
      />
      <field
        input="value_index"
        parser="Int"
        description="Registry value identifier referenced by MRUListEx"
      />
```

Keep the existing `key_path`, `key_modif_time`, and complete `key_security`
mapping. Remove the ACMru `category` field if the source file already contains
it after Task 3.

- [ ] **Step 2: Verify the existing registration test is RED**

Run:

```bash
uv run python -m unittest \
  tests.test_configuration.ConfigurationTest.test_all_configuration_parsers_are_registered \
  -v
```

Expected: `FAIL` listing
`configuration/registry/explorer_search_history.xml: RegExplorerSearchHistory`.

- [ ] **Step 3: Add the minimal registered plugin scaffold**

Create `explorer_search_history.py` with:

```python
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


class RegExplorerSearchHistory(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegExplorerSearchHistory",
            "Get Windows 7 and later Explorer search history from "
            "WordWheelQuery in NTUSER.DAT",
        )

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
            registry = Registry.load(input_file, r"\HKCU")
        except Exception as error:
            report.add_error(str(error))
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = registry.glob_keys(
                    r"\HKCU\Software\Microsoft\Windows\CurrentVersion"
                    r"\Explorer\WordWheelQuery"
                )
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as error:
                report.add_error(str(error))
            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        return
```

Export it from `src/dfir_ogre_plugin_windows/__init__.py`:

```python
from .registry.explorer_search_history import (
    RegExplorerSearchHistory as RegExplorerSearchHistory,
)
```

The additional XML security descriptor mapping is intentional. Update the
mapping count in
`ConfigurationTest.test_common_security_descriptor_mappings_use_plural_ace_arrays`:

```python
self.assertEqual(29, mapping_count)
```

- [ ] **Step 4: Verify registration and security mapping validation are GREEN**

Run:

```bash
uv run python -m unittest \
  tests.test_configuration.ConfigurationTest.test_all_configuration_parsers_are_registered \
  tests.test_configuration.ConfigurationTest.test_common_security_descriptor_mappings_use_plural_ace_arrays \
  -v
```

Expected: `OK`.

- [ ] **Step 5: Add positive real-hive and focused error tests**

Create `tests/hive/test_explorer_search_history.py` with:

```python
import json
import os
import struct
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows import RegExplorerSearchHistory

from . import CONF_FOLDER, DATA_FOLDER, TEMP_FOLDER


def word_wheel_key(values: dict[str, object]):
    key = Mock()
    key.path = (
        r"HKCU\Software\Microsoft\Windows\CurrentVersion"
        r"\Explorer\WordWheelQuery"
    )
    key.mtime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    key.value_data.side_effect = values.get

    security = Record()
    security.add("owner_sid", Value.String("S-1-5-21-test"))
    key.security_descriptor.to_record.return_value = security
    return key


class ExplorerSearchHistoryTest(TestCase):
    def test_public_hive_is_emitted_in_mru_list_order(self):
        plugin_file = os.path.join(
            CONF_FOLDER,
            "explorer_search_history.xml",
        )
        input_file = os.path.join(
            DATA_FOLDER,
            "hive",
            "NTUSER_WORD_WHEEL_QUERY.dat",
        )
        output_file = os.path.join(
            TEMP_FOLDER,
            "word_wheel_public.explorer_search_history.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            "word_wheel_public",
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )
        report = RegExplorerSearchHistory().parse(
            input_file,
            plugin_file,
            RunConfiguration([output_config]),
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(
            report.output_reports[0].file_reports[0].num_lines,
            2,
        )
        with open(output_file, encoding="utf-8") as output:
            records = [json.loads(line) for line in output]

        self.assertEqual(
            [record["search_request"] for record in records],
            ["rar.exe", "hyth"],
        )
        self.assertEqual(
            [record["order_index"] for record in records],
            [0, 1],
        )
        self.assertEqual(
            [record["value_index"] for record in records],
            [1, 0],
        )
        self.assertEqual(
            records[0]["key_modif_time"],
            "2012-04-06T18:44:16.075674+00:00",
        )
        self.assertIsNone(records[1]["key_modif_time"])

    def test_missing_mru_list_is_artifact_absence(self):
        key = word_wheel_key({})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIsNone(report.last_error)

    def test_malformed_mru_list_is_reported_without_output(self):
        key = word_wheel_key({"MRUListEx": b"\x01\x00"})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIn("MRUListEx length", report.last_error)

    def test_unterminated_mru_list_is_reported_without_output(self):
        key = word_wheel_key({"MRUListEx": struct.pack("<I", 1)})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIn("MRUListEx has no terminator", report.last_error)

    def test_missing_reference_is_reported_and_later_value_is_kept(self):
        key = word_wheel_key(
            {
                "MRUListEx": struct.pack("<III", 2, 1, 0xFFFFFFFF),
                "1": "valid".encode("utf-16-le") + b"\x00\x00",
            }
        )
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertEqual([record["search_request"] for record in records], ["valid"])
        self.assertEqual(records[0]["order_index"], 1)
        self.assertNotIn("key_modif_time", records[0])
        self.assertIn("missing WordWheelQuery value 2", report.last_error)

    def test_invalid_utf16_value_is_reported(self):
        key = word_wheel_key(
            {
                "MRUListEx": struct.pack("<II", 0, 0xFFFFFFFF),
                "0": b"\x00\xd8",
            }
        )
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIn("invalid UTF-16LE value 0", report.last_error)
```

- [ ] **Step 6: Run Explorer Search History behavior tests and verify RED**

Run:

```bash
uv run python -m unittest tests.hive.test_explorer_search_history -v
```

Expected: the public-hive test and four diagnostic tests fail because
`parse_key` is still a no-op. The artifact-absence test passes.

- [ ] **Step 7: Implement MRUListEx and UTF-16LE decoding**

Add these imports:

```python
import struct
```

Add these helpers:

```python
MRU_LIST_TERMINATOR = 0xFFFFFFFF


def parse_mru_list_ex(data: bytes) -> list[int]:
    if not isinstance(data, bytes):
        raise ValueError("MRUListEx is not binary data")
    if len(data) % 4 != 0:
        raise ValueError(
            f"MRUListEx length {len(data)} is not a multiple of 4"
        )

    values = [
        value[0]
        for value in struct.iter_unpack("<I", data)
    ]
    try:
        terminator = values.index(MRU_LIST_TERMINATOR)
    except ValueError as error:
        raise ValueError("MRUListEx has no terminator") from error
    return values[:terminator]


def decode_word_wheel_value(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise ValueError("value is not binary data")
    if len(data) % 2 != 0:
        raise ValueError(f"UTF-16LE value length {len(data)} is odd")
    try:
        return data.decode("utf-16-le").rstrip("\x00")
    except UnicodeDecodeError as error:
        raise ValueError("value is not valid UTF-16LE") from error
```

Replace the no-op `parse_key` with:

```python
def parse_key(self, key: RegKey, output: Output, report: RunReport):
    mru_list = key.value_data("MRUListEx")
    if mru_list is None:
        return

    try:
        value_indices = parse_mru_list_ex(mru_list)
    except ValueError as error:
        report.add_error(f"{key.path}: {error}")
        return

    for order_index, value_index in enumerate(value_indices):
        raw_value = key.value_data(str(value_index))
        if raw_value is None:
            report.add_error(
                f"{key.path}: missing WordWheelQuery value {value_index}"
            )
            continue
        try:
            search_request = decode_word_wheel_value(raw_value)
        except ValueError as error:
            report.add_error(
                f"{key.path}: invalid UTF-16LE value {value_index}: {error}"
            )
            continue

        record = Record()
        record.add("search_request", value(search_request))
        record.add("order_index", value(order_index))
        record.add("value_index", value(value_index))
        record.add("key_path", value(key.path))
        if order_index == 0:
            record.add("key_modif_time", value(key.mtime))
        record.add(
            "key_security",
            Value.Object(key.security_descriptor.to_record()),
        )
        output.write(record)
```

- [ ] **Step 8: Run Explorer Search History and configuration tests and verify GREEN**

Run:

```bash
uv run python -m unittest \
  tests.hive.test_explorer_search_history \
  tests.test_configuration \
  -v
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 9: Commit the Explorer Search History plugin**

```bash
git add \
  src/dfir_ogre_plugin_windows/registry/explorer_search_history.py \
  src/dfir_ogre_plugin_windows/__init__.py \
  configuration/registry/explorer_search_history.xml \
  tests/hive/test_explorer_search_history.py \
  tests/test_configuration.py
git commit -m "Add Explorer search history registry plugin"
```

---

### Task 5: Verify the Integrated Parser Set

**Files:**
- Verify: all files created or modified by Tasks 1-4

**Interfaces:**
- Consumes: committed parser, configuration, test, and fixture changes
- Produces: evidence that focused tests, configuration validation, syntax compilation, and the complete suite pass together

- [ ] **Step 1: Run the three focused parser suites**

Run:

```bash
uv run python -m unittest \
  tests.hive.test_recent_app \
  tests.hive.test_acmru \
  tests.hive.test_explorer_search_history \
  -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run configuration validation**

Run:

```bash
uv run python -m unittest tests.test_configuration -v
```

Expected: every configuration parser is registered, every timeline reference
resolves, and all security descriptor mappings remain complete.

- [ ] **Step 3: Run syntax and whitespace validation**

Run:

```bash
uv run python -m compileall -q src/dfir_ogre_plugin_windows tests
git diff --check HEAD~4
```

Expected: both commands exit zero with no output.

- [ ] **Step 4: Run the complete unit-test suite**

Run:

```bash
uv run python -m unittest discover -v
```

Expected: zero failures and zero errors.

- [ ] **Step 5: Verify fixture integrity again**

Run:

```bash
sha256sum \
  tests/data/hive/NTUSER_RECENT_APPS.dat \
  tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat
```

Expected:

```text
e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1  tests/data/hive/NTUSER_RECENT_APPS.dat
672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03  tests/data/hive/NTUSER_WORD_WHEEL_QUERY.dat
```

- [ ] **Step 6: Inspect scope and committed state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -6
git diff --stat HEAD~4..HEAD
```

Expected: no uncommitted changes; the implementation consists of the fixture,
RecentApps, ACMru, and Explorer Search History commits after the implementation-plan
baseline.
