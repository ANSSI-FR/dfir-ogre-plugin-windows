# Batched Registry Artifact Timezone Fallback Design

## Context

`RegScheduledTask` currently parses one SOFTWARE hive at a time. Scheduled Task
registration dates without an explicit offset are passed directly to
`datetime.astimezone()`, causing Python to interpret them in the timezone of the
analyst machine. The resulting UTC value therefore changes depending on where
the parser runs.

ShellBag and batched LNK parsing already group artifacts with SYSTEM hives by
VSS snapshot and resolve the source Windows timezone through
`system_timezone.resolve_system_timezone`. When no usable SYSTEM timezone is
available, that resolver records the condition in `RunReport.errors`, but the
two parsers currently replace affected local timestamps with null values.

## Architecture

Add a shared `resolve_system_timezone_or_utc` policy helper beside the existing
SYSTEM timezone resolver. It will:

1. Call `resolve_system_timezone`, preserving its existing error reporting.
2. Return the resolved `ZoneInfo` when successful.
3. When resolution fails, log one warning after the attempt and return
   `timezone.utc` as the deterministic fallback.

The helper returns a `tzinfo`, never `None`. Scheduled Task, ShellBag, and
batched LNK parsing will all use this helper once per artifact-bearing VSS
snapshot. A missing or unusable SYSTEM hive will therefore remain visible in
`RunReport.errors`, produce one warning line, and never stop artifact parsing.

## Scheduled Task Batching

Convert `RegScheduledTask` from `OgrePlugin` to `OgreBatchedPlugin` while
retaining its command name and output schema. Mark
`configuration/registry/scheduled_task.xml` with `batch="true"`.

Group input entries by the case-insensitive VSS snapshot identifier using the
existing metadata helpers. Within each snapshot:

- identify SYSTEM hives with the existing `is_system_hive` helper;
- identify SOFTWARE hives by source basename (`SOFTWARE`, `SOFTWARE.*`, or
  `SOFTWARE_*`);
- skip snapshots without a SOFTWARE hive;
- resolve the timezone once; and
- parse every SOFTWARE entry using its own run configuration and metadata.

This preserves separate output attribution when more than one SOFTWARE hive is
present in a snapshot. A direct CLI batch containing only a SOFTWARE hive still
parses successfully through the UTC fallback.

## Timestamp Semantics

Extract Scheduled Task registration-date normalization into a focused helper
that accepts the registry value and the resolved/fallback `tzinfo`.

- Parse the existing supported date formats with `dateutil.parser`.
- If the parsed value already contains an offset, preserve that offset's
  meaning and convert it directly to UTC.
- If the parsed value is timezone-naive, attach the source SYSTEM timezone and
  then convert it to UTC.
- If SYSTEM resolution failed, the shared fallback supplies UTC. Attaching it
  preserves the recorded wall-clock fields exactly while making the result
  deterministic; the analyst machine timezone is never consulted.

Use `fold=0` for ambiguous local wall-clock values, matching Python's default
interpretation and the existing ShellBag/LNK conversion behavior.

ShellBag and LNK retain their current field scope: only timestamps already
recognized as local wall-clock values are normalized. With no resolved SYSTEM
timezone, those values will now be labeled as UTC instead of being emitted as
null. Their parsing and all non-local timestamps remain unchanged.

## Error Handling and Logging

The existing resolver remains responsible for detailed `RunReport.errors`,
including absent hives, hive-load failures, and unknown Windows timezone names.
The new fallback helper adds exactly one warning after an unsuccessful
resolution attempt for a snapshot. The warning states that timestamps are
being interpreted with the naive UTC fallback.

All three consumers continue producing output after this condition. Valid
SYSTEM resolution produces neither an error nor a fallback warning.

Malformed Scheduled Task registration-date values continue through the
parser's existing exception/reporting boundary; this change does not silently
invent a date for an unparseable registry value.

## Tests

- Test the shared fallback policy with no SYSTEM entry: it returns UTC, records
  the resolver error, and logs one warning.
- Test successful resolution with the existing SYSTEM fixture: it returns the
  source `ZoneInfo` without a fallback warning or timezone-resolution error.
- Test Scheduled Task input grouping with multiple VSS snapshots and multiple
  SOFTWARE entries.
- Test registration-date normalization for a naive value with a non-UTC source
  timezone, an offset-aware value, and the UTC fallback. Assert results are
  independent of the process timezone.
- Update the Scheduled Task integration test to pass batched SOFTWARE and
  SYSTEM entries with matching VSS metadata and assert a registration timestamp
  derived from the SYSTEM timezone.
- Add a Scheduled Task integration test without SYSTEM that asserts output is
  still produced, `RunReport.errors` contains the missing-SYSTEM error, the
  warning is logged once, and the registration timestamp uses naive UTC.
- Add missing-SYSTEM continuation regressions for ShellBag and batched LNK.
  Assert each produces output, retains the resolver error, logs one warning,
  and emits its affected local timestamp with the naive UTC fallback rather
  than null.
- Run the complete unit-test suite after the focused regressions pass.

## Scope

No output field names, timeline qualifiers, dependencies, registry task-action
decoding, or non-local timestamp semantics change. The work is limited to
batching Scheduled Task inputs, centralizing missing-timezone fallback policy,
and applying that policy consistently to Scheduled Task, ShellBag, and LNK.
