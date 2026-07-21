# Hive Common Schema Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the upcoming `dfir-ogre-common` flat hive-value schema without changing the Windows plugin's established `HiveKey` command or description text.

**Architecture:** Keep `HiveKeys` as the sole Python plugin and continue delegating parsing to common's `parse_hive_values`. Replace only the stale XML record mapping, retaining `parser="HiveKey"` at its integration boundary, and update regression tests to lock both the stable plugin identity and the new flat output contract.

**Tech Stack:** Python 3.10, `unittest` tests collected by pytest, `uv`, editable local `dfir-ogre-common`, XML plugin mappings.

## Global Constraints

- `HiveKeys.description().command` remains exactly `HiveKey`.
- `HiveKeys.description().description` remains exactly `Extract Keys and Values from Windows Registry File`.
- `../dfir-ogre-common` is read-only and must not be modified.
- The output adopts data type `hive` and the flat common record schema.
- Do not modify or stage the existing untracked `tests/data/hive/SYSTEM_WIN_XP_SP2.data` fixture.

---

### Task 1: Migrate the Generic Hive Mapping Without Renaming the Plugin

**Files:**
- Modify: `tests/test_hive.py:24-66`
- Modify: `tests/test_configuration.py:76-79`
- Modify: `configuration/hive.xml:1-210`
- Modify: `src/dfir_ogre_plugin_windows/hive.py:1-9`

**Interfaces:**
- Consumes: `dfir_ogre_common.parse_hive_values(input_file, run_config, plugin_config, metadata, root_name, filter) -> RunReport`
- Produces: plugin command `HiveKey`, unchanged description text, and flat `hive` records containing `path`, `mtime`, `security_descriptor`, `name`, `data`, `type`, `size`, `is_placeholder`, `invalid_signature`, and `error`.

- [ ] **Step 1: Update the tests to express the compatibility contract**

In `tests/test_hive.py`, retain the command assertion, add the description-text assertion, change the expected output suffix, and validate the flat placeholder rows:

```python
        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".hive.jsonl")

        # Existing OutputConfiguration and RunConfiguration setup remains here.

        metadata = Metadata("test")
        parser = HiveKeys()
        description = parser.description()
        self.assertEqual("HiveKey", description.command)  # type: ignore
        self.assertEqual(
            "Extract Keys and Values from Windows Registry File",
            description.description,  # type: ignore
        )

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 6
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            rows = [json.loads(line) for line in fp]

        self.assertEqual(len(rows), expected_lines)
        self.assertEqual(
            rows[3]["data"]["path"],
            "HELLO\\subpath-test\\with-two-levels-of-subkeys",
        )

        for row in rows:
            data = row["data"]
            self.assertEqual("hive", row["data_type"])
            self.assertNotIn("values", data)
            self.assertEqual("Default", data["name"])
            self.assertEqual("", data["data"])
            self.assertEqual("REG_NONE", data["type"])
            self.assertEqual(0, data["size"])
            self.assertTrue(data["is_placeholder"])
            self.assertIsInstance(data["security_descriptor"], dict)
```

In `tests/test_configuration.py`, make the hive-specific descriptor lookup follow the new common field name:

```python
            descriptors = list(root.findall(".//object[@input='key_security']"))
            if plugin_file == Path(CONF_FOLDER, "hive.xml"):
                descriptors.extend(
                    root.findall(".//object[@input='security_descriptor']")
                )
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run --offline --frozen --with pytest --with-editable ../dfir-ogre-common \
  pytest -q tests/test_hive.py tests/test_configuration.py
```

Expected: two relevant failures. `test_hive_keys` expects `.hive.jsonl` but receives `.reg_keys.jsonl`, and the descriptor mapping test counts 27 mappings because the legacy XML still declares `descriptor`.

- [ ] **Step 3: Replace the legacy mapping with the flat schema**

Replace `configuration/hive.xml` with exactly:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plugin parser="HiveKey" file_encoding="UTF_8">
  <mapping data_type="hive">
    <description>Parse Windows Registry hive values</description>

    <default_parser value="Ignore" />
    <default_date_pattern value='%Y-%m-%d %H:%M:%S.%3f' />
    <truncate_values_after value="512" />

    <timeline>
      <timeline_type value="Standard" />
      <max_date_meaning value="0" />
      <source_type value="file" />
      <related_user include_field_name="false" field_separator=" - ">
        <output_name value="security_descriptor.owner_sid" />
      </related_user>
      <description>
        <output_name value="path" />
        <output_name value="name" />
      </description>
    </timeline>

    <fields>
      <field input="path" parser="String" qualifier="KEY_PATH" />
      <field input="mtime" parser="DateTime" qualifier="DATE_MODIFICATION" />
      <object input="security_descriptor">
        <field input="owner_sid" parser="String" qualifier="USER_SID" />
        <field input="group_sid" parser="String" />
        <array>
          <field input="control_flags" parser="String" />
        </array>
        <array>
          <object input="sacl_aces" ignore="false">
            <field input="ace_type" parser="String" />
            <array>
              <field input="ace_flags" parser="String" />
            </array>
            <array>
              <field input="rights" parser="String" />
            </array>
            <field input="account_sid" parser="String" />
            <field input="ace_size" parser="Int" />
            <field input="object_type_guid" parser="String" />
            <field input="inherited_object_type_guid" parser="String" />
            <field input="raw_hex" parser="String" />
          </object>
        </array>
        <array>
          <object input="dacl_aces" ignore="false">
            <field input="ace_type" parser="String" />
            <array>
              <field input="ace_flags" parser="String" />
            </array>
            <array>
              <field input="rights" parser="String" />
            </array>
            <field input="account_sid" parser="String" />
            <field input="ace_size" parser="Int" />
            <field input="object_type_guid" parser="String" />
            <field input="inherited_object_type_guid" parser="String" />
            <field input="raw_hex" parser="String" />
          </object>
        </array>
      </object>
      <field input="name" parser="String" qualifier="VALUE_NAME" />
      <field input="data" parser="String" />
      <field input="type" parser="String" />
      <field input="size" parser="Int" />
      <field input="is_placeholder" parser="Bool" />
      <field input="invalid_signature" parser="Bool" />
      <field input="error" parser="String" />
    </fields>
  </mapping>
</plugin>
```

In `src/dfir_ogre_plugin_windows/hive.py`, remove only the obsolete import while leaving `HiveKeys.description()` untouched:

```python
from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_hive_values,
)
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run --offline --frozen --with pytest --with-editable ../dfir-ogre-common \
  pytest -q tests/test_hive.py tests/test_configuration.py
```

Expected: `4 passed`.

- [ ] **Step 5: Run the complete regression suite**

Run:

```bash
uv run --offline --frozen --with pytest --with-editable ../dfir-ogre-common \
  pytest -q
```

Expected: `187 passed`, `37 subtests passed`, with only the three existing certificate deprecation warnings.

- [ ] **Step 6: Review and commit the implementation**

Verify that the Python description has no diff and that only the intended files are staged:

```bash
git diff --check
git diff -- src/dfir_ogre_plugin_windows/hive.py configuration/hive.xml \
  tests/test_hive.py tests/test_configuration.py
git status --short
```

Then commit only the implementation files:

```bash
git add src/dfir_ogre_plugin_windows/hive.py configuration/hive.xml \
  tests/test_hive.py tests/test_configuration.py
git commit -m "Migrate hive output to flat common schema"
```
