# WER Structure Validation and Encoding Detection

Date: 2026-07-24
Status: Approved for implementation

## Problem

The WER plugin currently opens every routed `Report.wer` as UTF-16LE and
creates its output before it knows whether the input is a Windows Error
Reporting report. Two acquired payloads routed to the plugin are unrelated
or corrupt binary data. They consequently raise decoding errors after output
creation. The exception path outside the plugin can also leave the run report
with `last_error` set while `num_errors` remains zero.

The parser must reject such payloads as invalid WER reports, count the error,
and avoid creating output for them. Genuine WER reports encoded as UTF-8 must
also be supported deliberately rather than by lossy or accidental decoding.

## Goals

- Validate that decoded input has a recognizable WER structure before opening
  `Output`.
- Represent validation and decoding failures internally with a typed
  `InvalidWerReportError`.
- Return those failures through the plugin's normal `RunReport` contract with
  one counted error and a stable `Invalid WER report:` message prefix.
- Support strict decoding of:
  - UTF-16LE with BOM;
  - UTF-16LE without BOM;
  - UTF-8 with BOM;
  - UTF-8 without BOM.
- Preserve existing WER field parsing, including unknown-field tolerance,
  embedded equals signs, GUID normalization, nested tables, file entries,
  loaded modules, and timeline output.
- Ensure other exceptions handled by the plugin are added through
  `RunReport.add_error()` so `num_errors` agrees with `last_error`.

## Non-goals

- Repairing or partially recovering truncated or mixed-encoding reports.
- Supporting UTF-16BE or legacy Windows code pages.
- Changing filename-based plugin routing in the parent application.
- Changing the public `OgrePlugin.parse()` interface to raise exceptions.
- Reclassifying unrelated acquisition artifacts outside this plugin.

## Public error contract

`InvalidWerReportError(ValueError)` is an internal typed exception used by
decoding and structure-validation helpers. `Wer.parse()` catches it and
returns a `RunReport` for consistency with the other plugins:

- `num_errors == 1`;
- `last_error` starts with `Invalid WER report:`;
- no output report is added;
- no output file is created.

The typed exception is available to helper-level tests and future internal
callers, while callers of the plugin continue to receive the established
`RunReport` result.

Configuration, input I/O, record-construction, and output failures are also
reported with `RunReport.add_error()` and return immediately. They use
category-specific messages rather than being mislabeled as invalid input.
Only decoding and structural-validation failures use
`InvalidWerReportError`.

## Decode and validation pipeline

The parser reads the input as bytes before constructing a record.

1. Detect an explicit BOM:
   - `FF FE`: decode the remaining bytes strictly as UTF-16LE;
   - `EF BB BF`: decode strictly as UTF-8 with the BOM removed;
   - `FE FF`: reject as unsupported UTF-16BE.
2. With no BOM, strictly try UTF-16LE and UTF-8.
3. Validate each successfully decoded candidate as WER.
4. Select the one valid candidate. Reject the input if neither candidate is
   valid. If both are valid, use deterministic UTF-8 preference for
   all-ASCII byte sequences; otherwise use UTF-16LE. In practice, WER
   structural validation disambiguates the encodings because a wrong decode
   contains NULs or cannot form the required keys.

No decoder uses replacement characters or ignores errors. Decode failures
are summarized in the final typed invalid-report error without embedding raw
payload contents.

A decoded report is structurally valid when:

- it contains a `Version=<decimal integer>` field; and
- it contains at least one additional WER marker:
  `EventType`, `ReportIdentifier`, `IntegratorReportIdentifier`,
  `AppSessionGuid`, or a `Sig`, `DynamicSig`, `OsInfo`, `State`, `File`, or
  `LoadedModule` field.

Blank lines and unknown `key=value` fields remain tolerated. The existing
parser's behavior of ignoring non-key lines is preserved after the report has
passed the minimum structural check. Requiring two independent markers avoids
accepting arbitrary text that merely happens to contain `Version=`.

After validation, the plugin parses all lines into an in-memory `Record`.
Only after record construction succeeds does it enter the `Output` context
and write the record. This ordering is the mechanism that guarantees invalid
or unparsable input does not create an output artifact.

## Exception accounting

Each failure path adds exactly one error and returns:

- configuration failure: `WER configuration: ...`;
- input read failure: `WER input: ...`;
- invalid encoding or structure: `Invalid WER report: ...`;
- unexpected record-construction failure: `WER parsing failed: ...`;
- output failure: `WER output: ...`.

Successful runs retain zero errors and one output report. The implementation
must not set `last_error` directly; it uses `RunReport.add_error()` so the
counter and last error cannot diverge.

## Testing

Tests are written before implementation and cover:

- existing UTF-16LE-with-BOM reports;
- existing BOM-less UTF-16LE behavior;
- UTF-8 with BOM;
- UTF-8 without BOM;
- a validly decoded text file without WER markers;
- unsupported UTF-16BE;
- binary/non-UTF-8 data representative of `wer_utf8.1.data`;
- a text-prefix-plus-binary payload representative of `wer_utf8.2.data`;
- invalid input returning one counted error with the stable prefix;
- invalid input leaving no output file and no output report;
- a forced unexpected parsing exception being counted;
- the existing WER regression suite.

Repository tests use small, synthetic payloads so they are deterministic and
do not retain unrelated forensic content. The two original payloads are also
run manually against the finished parser as an integration check.

## Compatibility and risk

Valid UTF-16LE WER reports continue through the same field-mapping logic.
Reading the complete report before output uses more memory than streaming, but
WER text reports are small and this makes validation atomic. The strict
minimum structure intentionally rejects empty, unrelated, corrupt, or
partially recovered files rather than emitting misleading empty records.

No new dependency is required.
