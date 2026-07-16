# WER OsInfo, State, and Optional BOM Design

## Problem

The WER parser loses three classes of forensic data:

1. Static and dynamic signatures use indexed `Name`/`Value` pairs, but real
   `OsInfo` and `State` sections use indexed `Key`/`Value` pairs. The shared
   builder recognizes only `Name`, so `Key` never establishes the destination
   field and each following value is discarded.
2. The `OsInfo` and `State` mapping objects are not dynamic. Even if their
   arbitrary child fields reach the record, the output mapping filters those
   children out.
3. The parser opens reports as UTF-16LE and then unconditionally consumes one
   decoded character as if it were a BOM. In a BOM-less report this removes the
   first character of `Version`, producing an unknown `ersion` field.

The repository fixtures reproduce the object loss: `report_1.wer` contains 33
`OsInfo` values, while `report_2.wer` contains 37 `OsInfo` values and one
`State` value. Current output contains no usable values from those sections.

## Goals

- Parse both indexed `Name`/`Value` and `Key`/`Value` object pairs.
- Emit all `OsInfo` and `State` entries that have values.
- Continue applying the output framework's standard dynamic-field name
  normalization.
- Accept UTF-16LE reports with or without a leading BOM.
- Preserve existing signature, file, loaded-module, scalar-field, and GUID
  behavior.
- Add regression coverage for the real fixtures and BOM-less input.

## Non-goals

- Detect or support UTF-16BE reports.
- Change WER value types; dynamic object values remain strings.
- Change `OsInfo` or `State` from objects to arrays of key/value records.
- Synthesize values for `Key` entries that have no following `Value` entry.
- Refactor unrelated WER sections or output-field naming.

## Design

### Optional BOM handling

Continue opening the report with `encoding="utf-16-le"`, but remove the
unconditional `input.read(1)`. On the first decoded line only, remove a leading
`\ufeff` with `removeprefix`. A BOM-bearing report therefore loses only its BOM,
while a BOM-less report keeps the first character of its first key. Parsing
remains streamed and does not load the complete report into memory.

### Indexed object construction

Keep one `ObjectBuilder` per WER section. Determine the terminal field type
from the indexed key:

- `Name` or `Key` establishes `builder.current_key`.
- `Value` adds a string under `builder.current_key` when a key is available.
- Any other terminal field type is ignored.
- A `Value` without a preceding `Name` or `Key` is ignored.

This preserves `Sig` and `DynamicSig` behavior while adding the real
`OsInfo`/`State` representation. Entries whose source contains a key but no
value remain absent rather than being fabricated as empty strings.

### Dynamic output mapping

Mark the `OsInfo` and `State` objects in `configuration/wer.xml` with
`dynamic="true"`. This allows previously unknown child fields to pass through
the normal mapping layer. The framework continues to normalize dynamic field
names; for example, `Transport.DoneStage1` is emitted as
`transport._done_stage1`.

## Error Handling

Existing line-level behavior remains unchanged: lines without `=` are skipped,
and unknown scalar fields are ignored when no parser is configured. Malformed
or orphaned indexed-object values are ignored without aborting the rest of the
report, so valid fields continue to be parsed.

## Testing

Extend `tests/test_wer.py` with assertions over the existing real fixtures:

- `report_1.wer` emits 33 `os_info` values, including `vermaj=10` and
  `edition=ServerStandard`.
- `report_2.wer` emits 37 `os_info` values, including `vermaj=10` and
  `edition=Enterprise`.
- `report_2.wer` emits `state.transport._done_stage1=1`.

Add a synthetic UTF-16LE report without a BOM whose first line is `Version=1`.
Assert that both `version` and a following scalar field are emitted. Existing
fixture and GUID tests continue to cover BOM-bearing reports and all previously
supported WER sections.
