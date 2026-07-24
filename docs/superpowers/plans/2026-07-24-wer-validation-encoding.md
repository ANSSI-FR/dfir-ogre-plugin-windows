# WER Validation and Encoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject unrelated or corrupt `Report.wer` payloads before output creation, return one counted invalid-report error, and deliberately support strict UTF-8 and UTF-16LE WER decoding with or without a BOM.

**Architecture:** Add a pure byte-decoding and WER-structure validation boundary to `wer.py`, raising `InvalidWerReportError` for unsupported encoding or missing WER markers. Refactor `Wer.parse()` into configuration, input, validation, record-construction, and output phases so each exception is counted through `RunReport.add_error()` and `Output` is entered only after a complete `Record` exists.

**Tech Stack:** Python 3.10+, standard-library byte decoding and `unittest.mock`, XML plugin configuration, and the `dfir-ogre-common` record/output APIs.

## Global Constraints

- `Wer.parse()` continues to return `RunReport`; it does not expose exceptions to plugin callers.
- `InvalidWerReportError(ValueError)` is the typed internal decoding and structure-validation error.
- Invalid reports return `num_errors == 1`, an `Invalid WER report:` last-error prefix, no output reports, and no output file.
- Strictly support UTF-16LE with BOM, UTF-16LE without BOM, UTF-8 with BOM, and UTF-8 without BOM.
- Do not attempt repair or fallback decoding for UTF-16BE, legacy code pages,
  mixed encodings, or truncated data; inputs that fail strict decoding or the
  minimum WER structure are rejected.
- A valid report requires `Version=<ASCII decimal integer>` and at least one independent WER marker defined in the approved design.
- Decode and construct the complete record before entering `Output`.
- Preserve existing WER mapping, GUID normalization, indexed objects, files, modules, embedded equals signs, and timeline output.
- Count configuration, input, record-construction, and output exceptions with `RunReport.add_error()`.
- Keep repository fixtures synthetic; verify the two original forensic payloads separately.
- Do not add dependencies or modify `configuration/wer.xml` or `uv.lock`.

---

### Task 1: Add strict encoding detection and structural validation

**Files:**
- Modify: `tests/test_wer.py`
- Modify: `src/dfir_ogre_plugin_windows/wer.py`

**Interfaces:**
- Consumes: `payload: bytes`.
- Produces: `InvalidWerReportError(ValueError)`.
- Produces: `decode_wer_report(payload: bytes) -> str`, returning BOM-free validated text or raising `InvalidWerReportError`.
- Internal: `_validate_wer_structure(text: str) -> None`.
- Internal: `_decode_wer_candidate(payload: bytes, encoding: str, label: str) -> str`.

- [ ] **Step 1: Add decoder contract tests**

In `tests/test_wer.py`, extend the WER-module imports:

```python
from dfir_ogre_plugin_windows import Wer
from dfir_ogre_plugin_windows.wer import (
    InvalidWerReportError,
    decode_wer_report,
)
```

Add this test class before `WerTest`:

```python
class WerDecoderTest(TestCase):
    valid_text = "Version=1\nEventType=EncodingTest\n"

    def test_decode_wer_report_supports_declared_encodings(self):
        encoded_reports = {
            "utf16le_bom": (
                b"\xff\xfe" + self.valid_text.encode("utf-16-le")
            ),
            "utf16le_without_bom": self.valid_text.encode("utf-16-le"),
            "utf8_bom": b"\xef\xbb\xbf" + self.valid_text.encode("utf-8"),
            "utf8_without_bom": self.valid_text.encode("utf-8"),
        }

        for label, payload in encoded_reports.items():
            with self.subTest(label=label):
                self.assertEqual(
                    decode_wer_report(payload),
                    self.valid_text,
                )

    def test_decode_wer_report_rejects_utf16be(self):
        payload = b"\xfe\xff" + self.valid_text.encode("utf-16-be")

        with self.assertRaisesRegex(
            InvalidWerReportError,
            "unsupported UTF-16BE",
        ):
            decode_wer_report(payload)

    def test_decode_wer_report_rejects_non_wer_payloads(self):
        payloads = {
            "text_without_wer_marker": (
                b"Version=1\nProduct=SharePoint\n"
            ),
            "binary_like_wer_utf8_1": b"\xbe\xc6\x97\x00\xff\x81",
            "text_and_binary_like_wer_utf8_2": (
                b"FarmId\tRequestUsage\n" + b"\x00\x00\xff\x81"
            ),
        }

        for label, payload in payloads.items():
            with self.subTest(label=label):
                with self.assertRaises(InvalidWerReportError):
                    decode_wer_report(payload)
```

- [ ] **Step 2: Run the decoder tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_wer.WerDecoderTest -v
```

Expected: `ERROR` while importing `InvalidWerReportError` or
`decode_wer_report`, proving the typed decoding boundary does not yet exist.

- [ ] **Step 3: Implement the typed decoder and validator**

In `src/dfir_ogre_plugin_windows/wer.py`, add these definitions after the
imports and before `class Wer`:

```python
UTF16_LE_BOM = b"\xff\xfe"
UTF16_BE_BOM = b"\xfe\xff"
UTF8_BOM = b"\xef\xbb\xbf"

WER_MARKER_KEYS = frozenset(
    {
        "EventType",
        "ReportIdentifier",
        "IntegratorReportIdentifier",
        "AppSessionGuid",
        "ReportDescription",
    }
)
WER_MARKER_PREFIXES = (
    "Sig[",
    "DynamicSig[",
    "OsInfo[",
    "State[",
    "File[",
    "LoadedModule[",
)


class InvalidWerReportError(ValueError):
    """Raised when bytes cannot be decoded as a recognizable WER report."""


def _validate_wer_structure(text: str) -> None:
    has_version = False
    has_marker = False

    for line in text.splitlines():
        fields = line.split("=", 1)
        if len(fields) != 2:
            continue
        key, value = fields
        if key == "Version":
            version = value.strip()
            if not (version.isascii() and version.isdecimal()):
                raise InvalidWerReportError(
                    "Version must be an ASCII decimal integer"
                )
            has_version = True
        elif (
            key in WER_MARKER_KEYS
            or key.startswith(WER_MARKER_PREFIXES)
        ):
            has_marker = True

    if not has_version:
        raise InvalidWerReportError("missing Version field")
    if not has_marker:
        raise InvalidWerReportError("missing independent WER marker")


def _decode_wer_candidate(
    payload: bytes,
    encoding: str,
    label: str,
) -> str:
    try:
        text = payload.decode(encoding)
    except UnicodeDecodeError as exception:
        raise InvalidWerReportError(
            f"invalid {label} encoding"
        ) from exception
    _validate_wer_structure(text)
    return text


def decode_wer_report(payload: bytes) -> str:
    if payload.startswith(UTF16_LE_BOM):
        return _decode_wer_candidate(
            payload[len(UTF16_LE_BOM):],
            "utf-16-le",
            "UTF-16LE",
        )
    if payload.startswith(UTF8_BOM):
        return _decode_wer_candidate(
            payload[len(UTF8_BOM):],
            "utf-8",
            "UTF-8",
        )
    if payload.startswith(UTF16_BE_BOM):
        raise InvalidWerReportError("unsupported UTF-16BE encoding")

    candidates: Dict[str, str] = {}
    for encoding, label in (
        ("utf-16-le", "UTF-16LE"),
        ("utf-8", "UTF-8"),
    ):
        try:
            candidates[encoding] = _decode_wer_candidate(
                payload,
                encoding,
                label,
            )
        except InvalidWerReportError:
            continue

    if not candidates:
        raise InvalidWerReportError(
            "not a WER report in UTF-8 or UTF-16LE"
        )
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    if all(byte < 0x80 for byte in payload):
        return candidates["utf-8"]
    return candidates["utf-16-le"]
```

- [ ] **Step 4: Run the decoder tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_wer.WerDecoderTest -v
```

Expected: all three decoder tests pass. The successful cases return the same
BOM-free WER text, UTF-16BE raises the typed error, and all unrelated
payloads raise the typed error.

- [ ] **Step 5: Run the existing WER tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_wer.WerTest -v
```

Expected: all existing `WerTest` cases pass; the new helper is not integrated
into `Wer.parse()` yet.

- [ ] **Step 6: Commit the decoding boundary**

```bash
git add src/dfir_ogre_plugin_windows/wer.py tests/test_wer.py
git commit -m "Add strict WER encoding validation"
```

---

### Task 2: Validate and construct records before opening output

**Files:**
- Modify: `tests/test_wer.py`
- Modify: `src/dfir_ogre_plugin_windows/wer.py`

**Interfaces:**
- Consumes: `decode_wer_report(payload: bytes) -> str` from Task 1.
- Produces: `build_wer_record(text: str, field_mapping: FieldMapping) -> Record`.
- Produces: `Wer.parse(...) -> RunReport` with one counted, categorized error on every handled failure.
- Preserves: existing `build_object(...)` and `ObjectBuilder`.

- [ ] **Step 1: Add plugin-level UTF-8, invalid-input, and exception-accounting tests**

Add the mock import at the top of `tests/test_wer.py`:

```python
from unittest.mock import patch
```

Add these helpers as the first methods of `WerTest`:

```python
    def parse_file(self, input_file: str, base_output_name: str):
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
            os.path.join(CONF_FOLDER, "wer.xml"),
            run_config,
            Metadata("test"),
        )
        return report, output_file

    def parse_payload(
        self,
        payload: bytes,
        base_output_name: str,
    ):
        input_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".input.wer",
        )
        with open(input_file, "wb") as fp:
            fp.write(payload)
        return self.parse_file(input_file, base_output_name)
```

Add these test methods to `WerTest`:

```python
    def test_wer_parses_utf8_with_and_without_bom(self):
        text = (
            "Version=1\n"
            "EventType=Utf8Report\n"
            "ReportDescription=café\n"
        )
        encodings = {
            "utf8_bom": b"\xef\xbb\xbf" + text.encode("utf-8"),
            "utf8_without_bom": text.encode("utf-8"),
        }

        for label, payload in encodings.items():
            with self.subTest(label=label):
                report, output_file = self.parse_payload(payload, label)
                self.assertEqual(
                    report.num_errors,
                    0,
                    report.last_error,
                )
                self.assertIsNone(report.last_error)
                self.assertEqual(len(report.output_reports), 1)
                with open(output_file, encoding="utf-8") as fp:
                    record = json.loads(fp.readline())
                self.assertEqual(record["version"], 1)
                self.assertEqual(record["event_type"], "Utf8Report")
                self.assertEqual(record["report_description"], "café")

    def test_wer_rejects_non_reports_before_output(self):
        payloads = {
            "invalid_binary_1": b"\xbe\xc6\x97\x00\xff\x81",
            "invalid_binary_2": (
                b"FarmId\tRequestUsage\n" + b"\x00\x00\xff\x81"
            ),
            "valid_utf8_without_wer_structure": (
                b"Version=1\nProduct=SharePoint\n"
            ),
            "utf16be": (
                b"\xfe\xff"
                + "Version=1\nEventType=WrongEndian\n".encode(
                    "utf-16-be"
                )
            ),
        }

        for label, payload in payloads.items():
            with self.subTest(label=label):
                report, output_file = self.parse_payload(payload, label)
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(
                    report.last_error.startswith(
                        "Invalid WER report:"
                    )
                )
                self.assertEqual(len(report.output_reports), 0)
                self.assertFalse(os.path.exists(output_file))

    def test_wer_counts_input_errors(self):
        missing_input = os.path.join(
            TEMP_FOLDER,
            "missing_wer_input.data",
        )
        if os.path.exists(missing_input):
            os.remove(missing_input)
        report, output_file = self.parse_file(
            missing_input,
            "missing_wer_input",
        )

        self.assertEqual(report.num_errors, 1)
        self.assertTrue(report.last_error.startswith("WER input:"))
        self.assertEqual(len(report.output_reports), 0)
        self.assertFalse(os.path.exists(output_file))

    def test_wer_counts_other_phase_exceptions(self):
        payload = b"Version=1\nEventType=ExceptionTest\n"
        failures = (
            (
                "configuration",
                "dfir_ogre_plugin_windows.wer.PluginConfiguration.load",
                "WER configuration:",
            ),
            (
                "record_construction",
                "dfir_ogre_plugin_windows.wer.build_wer_record",
                "WER parsing failed:",
            ),
            (
                "output",
                "dfir_ogre_plugin_windows.wer.Output",
                "WER output:",
            ),
        )

        for label, target, expected_prefix in failures:
            with self.subTest(label=label):
                with patch(
                    target,
                    side_effect=RuntimeError(f"forced {label} failure"),
                ):
                    report, output_file = self.parse_payload(
                        payload,
                        "wer_exception_" + label,
                    )
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(
                    report.last_error.startswith(expected_prefix)
                )
                self.assertEqual(len(report.output_reports), 0)
                self.assertFalse(os.path.exists(output_file))
```

- [ ] **Step 2: Run the new plugin tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer_parses_utf8_with_and_without_bom \
  tests.test_wer.WerTest.test_wer_rejects_non_reports_before_output \
  tests.test_wer.WerTest.test_wer_counts_input_errors \
  tests.test_wer.WerTest.test_wer_counts_other_phase_exceptions -v
```

Expected: failures and errors show the current parser still decodes every
input as UTF-16LE, can create empty output for unrelated text, lets decoding
and other phase exceptions escape, and does not provide `build_wer_record`.

- [ ] **Step 3: Extract record construction and phase `Wer.parse()`**

Add `FieldMapping` to the `dfir_ogre_common` import list in
`src/dfir_ogre_plugin_windows/wer.py`:

```python
    FieldMapping,
```

Replace `Wer.parse()` with:

```python
    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        report = RunReport()
        try:
            plugin_config = PluginConfiguration.load(
                plugin_file,
                python={
                    "AppSessionGuid": GuidParser.build(
                        "app_session_guid"
                    ),
                    "IntegratorReportIdentifier": GuidParser.build(
                        "integrator_report_identifier"
                    ),
                    "ReportIdentifier": GuidParser.build(
                        "report_identifier"
                    ),
                },
            )
            config = plugin_config.data_type_configs[0]
            field_mapping = config.field_mapping
            if not field_mapping:
                raise ValueError("invalid mapping configuration")
        except Exception as exception:
            report.add_error(f"WER configuration: {exception}")
            return report

        try:
            with open(input_file, "rb") as input_stream:
                payload = input_stream.read()
        except Exception as exception:
            report.add_error(f"WER input: {exception}")
            return report

        try:
            text = decode_wer_report(payload)
        except InvalidWerReportError as exception:
            report.add_error(f"Invalid WER report: {exception}")
            return report
        except Exception as exception:
            report.add_error(f"WER parsing failed: {exception}")
            return report

        try:
            record = build_wer_record(text, field_mapping)
        except Exception as exception:
            report.add_error(f"WER parsing failed: {exception}")
            return report

        try:
            with Output(
                run_config,
                plugin_config,
                metadata,
            ) as output:
                output.write(record)
            report.add_output_report(output.get_report())
        except Exception as exception:
            report.add_error(f"WER output: {exception}")
        return report
```

Add this function between `class Wer` and `build_object()`:

```python
def build_wer_record(
    text: str,
    field_mapping: FieldMapping,
) -> Record:
    record = Record()
    tables: Dict[str, ObjectBuilder] = {}
    loaded_module: List[Value] = []
    files: List[Value] = []
    current_file: Optional[Record] = None

    for line in text.splitlines():
        fields = line.split("=", 1)
        if len(fields) != 2:
            continue
        key = fields[0]
        value = fields[1].strip()

        if key.startswith("Sig"):
            build_object(tables, key, value, "Sig")
        elif key.startswith("DynamicSig"):
            build_object(tables, key, value, "DynamicSig")
        elif key.startswith("OsInfo"):
            build_object(tables, key, value, "OsInfo")
        elif key.startswith("State"):
            build_object(tables, key, value, "State")
        elif key.startswith("File"):
            key_type = key.split(".")[1]
            if key_type == "CabName" and current_file:
                files.append(Value.Object(current_file))
                current_file = Record()
            if not current_file:
                current_file = Record()
            current_file.add(key_type, Value.String(value))
        elif key.startswith("LoadedModule"):
            loaded_module.append(Value.String(value))
        else:
            parser = field_mapping.get_parser(key)
            if parser:
                parser.parse(value, record)

    if current_file:
        files.append(Value.Object(current_file))

    for key, value in tables.items():
        record.add(key, Value.Object(value.object))

    record.add("loaded_module", Value.Array(loaded_module))
    record.add("files", Value.Array(files))
    return record
```

Remove the old nested text-file and `Output` loop from `Wer.parse()`; the
extracted function above is its complete replacement and retains the same
field dispatch order and value handling.

- [ ] **Step 4: Run the new plugin tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_wer.WerTest.test_wer_parses_utf8_with_and_without_bom \
  tests.test_wer.WerTest.test_wer_rejects_non_reports_before_output \
  tests.test_wer.WerTest.test_wer_counts_input_errors \
  tests.test_wer.WerTest.test_wer_counts_other_phase_exceptions -v
```

Expected: all four tests pass. Invalid payloads return exactly one counted
error and do not create output; UTF-8 reports emit mapped values; forced
phase exceptions return the expected categorized error.

- [ ] **Step 5: Run the complete WER regression module**

Run:

```bash
.venv/bin/python -m unittest tests.test_wer -v
```

Expected: every decoder, validation, UTF-8, exception-accounting, existing
UTF-16LE, GUID, nested-object, file, module, equals-sign, and timeline test
passes.

- [ ] **Step 6: Commit parser integration**

```bash
git add src/dfir_ogre_plugin_windows/wer.py tests/test_wer.py
git commit -m "Reject invalid WER reports before output"
```

---

## Final verification

- [ ] **Step 1: Run the full repository test suite**

```bash
.venv/bin/python -m unittest discover -v
```

Expected: the suite exits zero with no failures or errors.

- [ ] **Step 2: Compile Python sources and tests**

```bash
.venv/bin/python -m compileall -q src tests
```

Expected: exit zero with no output.

- [ ] **Step 3: Verify the two original payloads**

Run from the plugin repository:

```bash
.venv/bin/python - <<'PY'
import tempfile
from pathlib import Path

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)
from dfir_ogre_plugin_windows import Wer

samples = (
    Path(
        "/home/asalais/dev/dfir-ogre/manual_tests/"
        "debug_data/wer_utf8.1.data"
    ),
    Path(
        "/home/asalais/dev/dfir-ogre/manual_tests/"
        "debug_data/wer_utf8.2.data"
    ),
)

with tempfile.TemporaryDirectory() as temporary:
    output_directory = Path(temporary)
    for index, sample in enumerate(samples, start=1):
        base_name = f"invalid_wer_{index}"
        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_name,
                    str(output_directory),
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        report = Wer().parse(
            str(sample),
            "configuration/wer.xml",
            run_config,
            Metadata("test"),
        )
        output_file = output_directory / f"{base_name}.wer.jsonl"
        assert report.num_errors == 1, report.num_errors
        assert report.last_error.startswith(
            "Invalid WER report:"
        ), report.last_error
        assert len(report.output_reports) == 0
        assert not output_file.exists(), output_file
        print(sample.name, report.last_error)
PY
```

Expected: both lines report `Invalid WER report: ...`; all assertions pass,
and neither payload creates a JSONL file.

- [ ] **Step 4: Check formatting, scope, and repository state**

```bash
git diff --check main
git diff --stat main
git status --short --branch
```

Expected: `git diff --check main` emits no output; the diff is limited to the
approved design/plan, `wer.py`, and `test_wer.py`; the branch is
`fix/wer-validation` with a clean working tree after the implementation
commits.
