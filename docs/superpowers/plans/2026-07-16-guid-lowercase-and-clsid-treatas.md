# GUID Lowercase and CLSID TreatAs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read CLSID `TreatAs` redirects from the correct registry subkey and emit every semantically typed GUID/UUID/CLSID field in lowercase without rewriting raw or embedded evidence.

**Architecture:** Add one strict full-value GUID normalizer and configuration parser in `common.py`. Apply it at typed output boundaries in hand-written parsers and register it only for explicit GUID fields in configuration-driven parsers. Keep braces/hyphens and leave malformed, polymorphic non-GUID, raw payload, path, description, and command values unchanged.

**Tech Stack:** Python 3.10+, `re`, `unittest`, `dfir_ogre_common` parser/configuration/output APIs, XML plugin mappings.

## Global Constraints

- Normalize only a complete `8-4-4-4-12` hexadecimal GUID, optionally enclosed in braces.
- Preserve braces, hyphens, nulls, invalid values, and non-string values.
- Preserve GUID substrings embedded in paths, commands, JSON, descriptions, and other free-form text.
- Preserve raw registry and event payload containers; normalize their typed counterparts only.
- Do not treat hashes, SIDs, OIDs, volume serials, or arbitrary identifiers as GUIDs.
- Do not change output schemas, field names, timeline definitions, record counts, or parser continuation/error behavior.
- Keep existing Python `uuid.UUID` and LNK lowercase behavior intact.
- Preserve the user's unrelated main-worktree `uv.lock` change; do not stage or modify it.

---

## File Structure

- Modify: `src/dfir_ogre_plugin_windows/common.py`
  - Adds strict normalization helpers and a configuration parser.
- Modify: `tests/test_common.py`
  - Defines the casing and evidence-preservation contract.
- Modify: `src/dfir_ogre_plugin_windows/registry/clsid.py`
  - Reads `TreatAs\(default)` from the child key and normalizes typed CLSIDs.
- Modify: `tests/hive/test_clsid.py`
  - Replaces the incorrect description expectation with the true redirect CLSID.
- Modify: `src/dfir_ogre_plugin_windows/registry/{scheduled_task,amcache_program,mass_storage}.py`
  - Normalizes hand-built registry GUID fields.
- Modify: `src/dfir_ogre_plugin_windows/security_descriptor.py`
  - Normalizes typed ACE object GUIDs.
- Modify: focused registry/security tests.
- Modify: CSV, XML, SQLite, EVTX, and WER wrappers plus their GUID-bearing XML configurations.
  - Registers the strict parser at configuration-driven boundaries.
- Modify: `configuration/lnk_batched.xml` and `tests/test_lnk.py`
  - Covers the two LNK GUID mappings that were still plain strings.

### Task 1: Shared Strict GUID Normalizer

**Files:**
- Modify: `tests/test_common.py`
- Modify: `src/dfir_ogre_plugin_windows/common.py`

- [ ] **Step 1: Write failing helper and parser tests**

Add tests for mixed-case braced and unbraced GUIDs, lowercase idempotence,
malformed/unbalanced braces, a GUID embedded in a path/description, `None`, and
mixed list/tuple values. Also parse an uppercase GUID with `GuidParser` and
assert the requested output field contains the lowercase string.

Representative assertions:

```python
self.assertEqual(
    normalize_guid("{F20DA720-C02F-11CE-927B-0800095AE340}"),
    "{f20da720-c02f-11ce-927b-0800095ae340}",
)
self.assertEqual(
    normalize_guid(r"C:\Volume{F20DA720-C02F-11CE-927B-0800095AE340}"),
    r"C:\Volume{F20DA720-C02F-11CE-927B-0800095AE340}",
)
self.assertEqual(
    normalize_guid_values(["{F20DA720-C02F-11CE-927B-0800095AE340}", "Name"]),
    ["{f20da720-c02f-11ce-927b-0800095ae340}", "Name"],
)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest tests.test_common -v
```

Expected: imports/assertions fail because the GUID helpers and parser do not
exist.

- [ ] **Step 3: Implement the strict normalizer and `GuidParser`**

In `common.py`, add one compiled full-match expression equivalent to:

```python
GUID_PATTERN = re.compile(
    r"(?:\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}"
    r"|[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})"
)
```

`normalize_guid` lowercases only matching strings. `normalize_guid_values`
recurses through lists and tuples while preserving their container types.
`GuidParser.parse` omits empty input like the existing custom parsers and emits
`Value.String(normalize_guid(input))` otherwise. Its
`output_fields_names()` returns an empty list.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 command again and require `OK`.

### Task 2: Correct CLSID `TreatAs`

**Files:**
- Modify: `tests/hive/test_clsid.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/clsid.py`

- [ ] **Step 1: Change the fixture assertion to the real child value**

At software record 53, assert both the structured value and timeline text use:

```text
{f20da720-c02f-11ce-927b-0800095ae340}
```

The timeline `additional_description` must be:

```text
treat_as: {f20da720-c02f-11ce-927b-0800095ae340}
```

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest tests.hive.test_clsid -v
```

Expected: the old parser still emits `sound (ole2)`.

- [ ] **Step 3: Fix the key read and route CLSIDs through the helper**

Replace the parent read with `treat_as_key.value_data("(default)")`. Normalize
both `key.name` and the child default with `normalize_guid`; do not lowercase
the description or executable fields.

- [ ] **Step 4: Verify GREEN**

Run the Task 2 command and require both user and software hive tests to pass
with unchanged record counts.

### Task 3: Normalize Hand-Built Registry and Security GUID Fields

**Files:**
- Modify: `tests/hive/test_scheduled_task.py`
- Modify: `tests/hive/test_amcache_program.py`
- Modify: `tests/hive/test_mass_storage.py`
- Create: `tests/test_security_descriptor.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/scheduled_task.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/amcache_program.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/mass_storage.py`
- Modify: `src/dfir_ogre_plugin_windows/security_descriptor.py`

- [ ] **Step 1: Add failing focused assertions**

- Scheduled Task: assert every typed `data.guid` equals its lowercase form and
  that raw `plain.name` remains source-cased.
- Amcache: assert uppercase MSI product/package codes become lowercase,
  including GUID elements held in registry lists without changing the current
  string/list output schema.
- Mass storage: create a `UsbDevice`, assign an uppercase braced `volume_guid`,
  call `to_record`, and assert lowercase output.
- Security descriptor: parse an object ACE with uppercase `object_guid` and
  `inherit_object_guid`, then assert lowercase values in `to_record`.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest \
  tests.hive.test_scheduled_task \
  tests.hive.test_amcache_program \
  tests.hive.test_mass_storage \
  tests.test_security_descriptor -v
```

Expected: new casing assertions fail while existing parsing tests still run.

- [ ] **Step 3: Normalize only typed values**

- Wrap `task.name` with `normalize_guid`; leave `boot`, `logon`, `maintenance`,
  `plain`, and `tree` raw registry records unchanged.
- Pass both MSI code values through `normalize_guid_values` before `value(...)`.
- Normalize `UsbDevice.volume_guid` only when constructing its typed record.
- Normalize local `ACE.object_guid` and `ACE.inherit_object_guid` in
  `ACE.to_record`.
- Retain `uuid.UUID` conversion for Scheduled Task COM handlers.

- [ ] **Step 4: Verify GREEN**

Run the Task 3 command and require `OK` with unchanged integration counts.

### Task 4: Normalize CSV Snapshot GUIDs

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/{csv,get_this,i30_info,ntfs_info,usn_info}.py`
- Modify: `configuration/{vss_snapshot,volstat,get_this,i30_info,ntfs_info,usn_info}.xml`
- Modify: `tests/test_{csv,get_this,i30_info,ntfs_info,usn_info,vss_snapshot}.py`

- [ ] **Step 1: Add failing integration assertions**

- VSS `snapshot_id` must be
  `{dde981e2-0b1d-41d8-8ca5-ba4d87b7d2ca}`.
- Volstat `shadow_copy` must be lowercase while `volumeid` remains the original
  uppercase hexadecimal volume serial.
- Add `snapshot_id == snapshot_id.lower()` assertions to GetThis, I30, NTFS,
  and USN fixture records; their zero GUIDs also prove the Python mapping loads
  without disturbing the specialized extension parsers.

- [ ] **Step 2: Verify RED on uppercase fixtures**

Run:

```bash
../../.venv/bin/python -m unittest \
  tests.test_vss_snapshot tests.test_csv tests.test_get_this \
  tests.test_i30_info tests.test_ntfs_info tests.test_usn_info -v
```

Expected: VSS and Volstat casing assertions fail.

- [ ] **Step 3: Register and select `GuidParser`**

Load plugin configurations with Python mappings for `SnapshotID` and/or
`ShadowCopyId` in each relevant wrapper. Preserve existing Rust extension
mappings in GetThis/I30/NTFS/USN. Change only those XML fields from `String` to
`Python`. Update `Csv.description()` because it now supports this scoped Python
extension.

- [ ] **Step 4: Verify GREEN**

Run the Task 4 command and require all CSV parsers and timeline outputs to keep
their prior record counts.

### Task 5: Normalize XML and SQLite GUID Fields

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/xml.py`
- Modify: `configuration/amcache_file/amcache_ie_addon.xml`
- Modify: `tests/amcache_files/test_amcache_ie_addon.py`
- Modify: `src/dfir_ogre_plugin_windows/sqlite.py`
- Modify: `configuration/activity_cache.xml`
- Modify: `tests/test_sqlite.py`

- [ ] **Step 1: Add failing fixture assertions**

- Assert IE add-on `id` is
  `{d27cdb6e-ae6d-11cf-96b8-444553540000}`.
- Assert Activity Cache GUID-form `app_activity_id` values are lowercase.
- Assert the first non-GUID activity identifier remains exactly
  `default$windows.data.bluelightreduction.settings|windows.data.bluelightreduction.settings`.
- Assert GUID substrings inside `app_id` JSON are not rewritten.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest \
  tests.amcache_files.test_amcache_ie_addon tests.test_sqlite -v
```

- [ ] **Step 3: Register mappings and update configurations**

Load `@CLSID` through `GuidParser` in `XML`, and `AppActivityId` through
`GuidParser` in `SQLite`; switch only those fields to `parser="Python"`.

- [ ] **Step 4: Verify GREEN**

Run the Task 5 command and require unchanged output counts and preserved
non-GUID values.

### Task 6: Normalize EVTX and WER GUID Fields

**Files:**
- Modify: `src/dfir_ogre_plugin_windows/evtx.py`
- Modify: `configuration/evtx.xml`
- Modify: `tests/test_evtx.py`
- Modify: `src/dfir_ogre_plugin_windows/wer.py`
- Modify: `configuration/wer.xml`
- Modify: `tests/test_wer.py`

- [ ] **Step 1: Add failing structured-output assertions**

For EVTX record zero, assert:

```python
data["system"]["provider"]["guid"] == "9c205a39-1250-487d-abd7-e831c6290539"
data["event_data"]["class_guid"] == "4d36e966-e325-11ce-bfc1-08002be10318"
data["event_data"]["device_instance_id"] == r"ROOT\ACPI_HAL\0000"
```

The last assertion protects the rest of the formerly dynamic event-data object.
For WER, create an uppercase synthetic report or assert a directly loaded
configuration/parser path for `ReportIdentifier`,
`IntegratorReportIdentifier`, and `AppSessionGuid`; all three must lowercase
while unrelated values containing GUID substrings remain unchanged.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest tests.test_evtx tests.test_wer -v
```

- [ ] **Step 3: Register mappings and explicitly type dynamic fields**

- Load EVTX configuration with `Guid` and `ClassGuid` Python mappings. Change
  provider `Guid` to `Python`. Add an explicit `ClassGuid` child mapping under
  `EventData` while confirming unspecified event-data keys remain dynamically
  parsed; if the configuration engine cannot merge explicit and dynamic keys,
  preserve `EventData` as raw and document/test that boundary rather than
  dropping fields.
- Load WER configuration with all three identifier keys and add explicit fields
  where the current default parser supplies one dynamically. Change those
  fields to `Python`.

- [ ] **Step 4: Verify GREEN and event-data completeness**

Run the Task 6 command. Require 123 EVTX records, both GUID fields lowercase,
and representative non-GUID event-data fields still present.

### Task 7: Complete LNK GUID Mappings

**Files:**
- Modify: `tests/test_lnk.py`
- Modify: `configuration/lnk_batched.xml`

- [ ] **Step 1: Add a failing parser-tree unit test**

Load the LNK configuration and call `parse_object` with a synthetic uppercase
target-item `guid` and metadata property-store `format_id`. Assert both are
lowercase and that braces/hyphens are preserved.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m unittest tests.test_lnk -v
```

- [ ] **Step 3: Change the two remaining mappings**

Set `property_store.format_id` and target-item `guid` to `StringToLower`. Do not
change already-correct LinkCLSID, known-folder, product-code, or Droid mappings.

- [ ] **Step 4: Verify GREEN**

Run the Task 7 command and require all direct and batched LNK regressions to
pass.

### Task 8: Audit, Configuration Validation, and Full Regression

**Files:**
- Modify as needed only for issues exposed by verification.

- [ ] **Step 1: Review the semantic-field audit**

Search source/configuration for remaining typed GUID declarations and raw
`.lower()` calls:

```bash
rg -n -i "guid|uuid|clsid" src configuration
rg -n "parser=\"String\"" configuration | rg -i "guid|clsid"
```

Confirm any remaining plain/raw GUID-looking location is either naturally
lowercase (`uuid.UUID`) or explicitly excluded (path, description, raw event or
registry payload, hash/serial/non-GUID ID).

- [ ] **Step 2: Run focused aggregate tests**

```bash
../../.venv/bin/python -m unittest \
  tests.test_common tests.hive.test_clsid tests.hive.test_scheduled_task \
  tests.hive.test_amcache_program tests.hive.test_mass_storage \
  tests.test_security_descriptor tests.test_vss_snapshot tests.test_csv \
  tests.test_get_this tests.test_i30_info tests.test_ntfs_info \
  tests.test_usn_info tests.amcache_files.test_amcache_ie_addon \
  tests.test_sqlite tests.test_evtx tests.test_wer tests.test_lnk -v
```

- [ ] **Step 3: Validate repository configuration tests**

```bash
../../.venv/bin/python -m unittest tests.test_configuration -v
```

- [ ] **Step 4: Run the complete suite**

```bash
../../.venv/bin/python -m unittest discover -v
```

Expected baseline: at least the original 137 tests plus the new regressions,
all ending in `OK`.

- [ ] **Step 5: Run static/diff checks**

```bash
../../.venv/bin/python -m compileall -q src tests
git diff --check
git status --short
git diff --stat
```

Inspect the final diff for accidental raw-evidence lowercasing, schema changes,
fixture edits, generated output, or `uv.lock` changes before reporting
completion.
