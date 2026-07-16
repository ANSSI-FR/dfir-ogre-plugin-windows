# WER OsInfo, State, and Optional BOM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve WER `OsInfo` and `State` key/value data and parse UTF-16LE reports correctly whether or not they begin with a BOM.

**Architecture:** Extend the existing indexed-object builder to understand both `Name` and `Key` anchors, and make the two arbitrary-key output objects dynamic. Keep streaming UTF-16LE decoding, replacing unconditional first-character consumption with removal of only an actual BOM from the first line.

**Tech Stack:** Python 3.10+, XML plugin configuration, `dfir-ogre-common` record/output APIs, and standard-library `unittest`.

## Global Constraints

- Support both indexed `Name`/`Value` and `Key`/`Value` pairs.
- Emit every `OsInfo` and `State` entry that has a value.
- Keep dynamic object values as strings and retain framework field-name normalization.
- Accept UTF-16LE reports with and without a leading BOM.
- Do not add UTF-16BE detection.
- Preserve all existing WER fields, files, loaded modules, signatures, and GUID normalization.
- Ignore orphaned or malformed indexed values without aborting the report.
- Do not change dependencies or `uv.lock`.

---

### Task 1: Preserve OsInfo and State objects

**Files:**
- Modify: `tests/test_wer.py:70-201`
- Modify: `src/dfir_ogre_plugin_windows/wer.py:106-117`
- Modify: `configuration/wer.xml:377-380`

**Interfaces:**
- Consumes: WER indexed keys ending in `.Name`, `.Key`, or `.Value`, and `ObjectBuilder.current_key`.
- Produces: Dynamic `os_info` and `state` objects populated with string values under framework-normalized field names.

- [ ] **Step 1: Add failing assertions for real OsInfo and State fixtures**

In `test_wer()`, after the existing `dynamic_sig` assertion, add:

```python
                    self.assertEqual(len(jsoned["os_info"]), 33)
                    self.assertEqual(jsoned["os_info"]["vermaj"], "10")
                    self.assertEqual(
                        jsoned["os_info"]["edition"],
                        "ServerStandard",
                    )
```

In `test_wer_2()`, after the existing `dynamic_sig` assertion, add:

```python
                    self.assertEqual(len(jsoned["os_info"]), 37)
                    self.assertEqual(jsoned["os_info"]["vermaj"], "10")
                    self.assertEqual(
                        jsoned["os_info"]["edition"],
                        "Enterprise",
                    )
                    self.assertEqual(
                        jsoned["state"]["transport._done_stage1"],
                        "1",
                    )
```

- [ ] **Step 2: Run both fixture tests and verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer \
  tests.test_wer.WerTest.test_wer_2 -v
```

Expected: `FAIL`; `report_1.wer` exposes an empty `os_info` object instead of 33 entries. The failure demonstrates that real `.Key/.Value` data does not reach output.

- [ ] **Step 3: Teach the object builder both pair formats**

Replace `build_object()` with:

```python
def build_object(tables: dict, key: str, value: str, pattern: str):
    builder: ObjectBuilder | None = tables.get(pattern, None)
    if not builder:
        builder = ObjectBuilder()
        tables[pattern] = builder

    key_type = key.rsplit(".", 1)[1]
    if key_type in ("Name", "Key"):
        builder.current_key = value
    elif key_type == "Value" and builder.current_key:
        builder.object.add(builder.current_key, Value.String(value))
```

- [ ] **Step 4: Allow arbitrary OsInfo and State fields through mapping**

Replace the two object declarations at the end of `configuration/wer.xml` with:

```xml
      <object input="OsInfo" output="os_info" dynamic="true" />

      <object input="State" output="state" dynamic="true" />
```

- [ ] **Step 5: Run both fixture tests and verify GREEN**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer \
  tests.test_wer.WerTest.test_wer_2 -v
```

Expected: both tests pass; report 1 emits 33 OS values, report 2 emits 37 OS values and one State value.

- [ ] **Step 6: Run the complete WER test module**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_wer -v
```

Expected: all existing WER tests pass with the new fixture assertions.

- [ ] **Step 7: Commit object-pair parsing**

```bash
git add src/dfir_ogre_plugin_windows/wer.py configuration/wer.xml \
  tests/test_wer.py
git commit -m "Fix WER OsInfo and State parsing"
```

---

### Task 2: Preserve the first key in BOM-less reports

**Files:**
- Modify: `tests/test_wer.py`
- Modify: `src/dfir_ogre_plugin_windows/wer.py:49-56`

**Interfaces:**
- Consumes: a text stream decoded with `encoding="utf-16-le"`.
- Produces: Identical key/value lines for BOM-less input and first-line input with only a leading `\ufeff` removed.

- [ ] **Step 1: Add a failing BOM-less report test**

Add this method to `WerTest`:

```python
    def test_wer_preserves_first_key_without_bom(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")
        input_file = os.path.join(TEMP_FOLDER, "report_without_bom.wer")
        base_output_name = "wer_without_bom"

        with open(input_file, "wb") as fp:
            fp.write(
                (
                    "Version=1\n"
                    "EventType=BomlessReport\n"
                ).encode("utf-16-le")
            )

        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".wer.jsonl",
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

        report = Wer().parse(
            input_file,
            plugin_file,
            run_config,
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as fp:
            record = json.loads(fp.readline())
        self.assertEqual(record.get("version"), 1)
        self.assertEqual(record["event_type"], "BomlessReport")
```

- [ ] **Step 2: Run the BOM-less test and verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer_preserves_first_key_without_bom -v
```

Expected: `FAIL` with `None != 1` because `version` is missing; the parser consumed the leading `V` and parsed the first key as `ersion`.

- [ ] **Step 3: Remove only an actual BOM from the first line**

Delete:

```python
            input.read(1)  # ignore the BOM prefix
```

Change the line loop from:

```python
                for line in input:
```

to:

```python
                for line_number, line in enumerate(input):
                    if line_number == 0:
                        line = line.removeprefix("\ufeff")
```

- [ ] **Step 4: Run the BOM-less test and verify GREEN**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer_preserves_first_key_without_bom -v
```

Expected: `PASS`; both `version` and `event_type` are present.

- [ ] **Step 5: Run all verification checks**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest discover -q
PYTHONPATH=src ../../.venv/bin/python -m compileall -q src tests
git diff --check
```

Expected: the full suite passes with 148 tests, compilation succeeds, and `git diff --check` emits no output.

- [ ] **Step 6: Review the final diff for scope**

Run:

```bash
git diff main -- src/dfir_ogre_plugin_windows/wer.py \
  configuration/wer.xml tests/test_wer.py
```

Expected: only optional-BOM handling, `Name`/`Key` pair support, dynamic mappings, and regression coverage are present.

- [ ] **Step 7: Commit optional-BOM support**

```bash
git add src/dfir_ogre_plugin_windows/wer.py tests/test_wer.py
git commit -m "Support BOM-less WER reports"
```
