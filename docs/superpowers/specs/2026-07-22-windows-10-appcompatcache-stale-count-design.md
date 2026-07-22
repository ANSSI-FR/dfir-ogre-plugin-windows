# Windows 10 AppCompatCache Stale-Count Handling Design

## Problem

`RegAppCompatCache` treats a mismatch between the Windows 10 header's cached-entry
count and the number of structurally parsed entries as an error. The supplied
Windows Server 2016 hive contains clean, fully bounded cache values whose header
counts are stale: `ControlSet001` declares 1 while containing 747 entries, and
`ControlSet002` declares 0 while containing 746 entries. All 1,493 entries parse
without marker, body-size, path, FILETIME, data-size, or boundary errors, yet the
plugin reports both values as failures after writing their records.

## Decision

Treat the Windows 10 header count as advisory rather than an integrity boundary.
The parser will no longer compare that field with the number of sequential
entries or emit a diagnostic for a mismatch. It will continue to identify the
entry-array offset from the 48-byte or 52-byte header and walk entries using the
existing bounded `10ts` envelope.

This is preferred over a Server 2016 exception because stale metadata can occur
in any Windows 10-format cache. It is also preferred over adding a warning-only
path because parser diagnostics currently represent actionable `RunReport`
errors, and exposing advisory metadata would require a broader reporting API
change.

## Preserved Validation

The change does not relax structural validation. The parser will continue to
report:

- a missing or misplaced `10ts` entry marker;
- a truncated 12-byte entry header;
- an entry body extending outside the cache value;
- an invalid UTF-16LE path or path size;
- a malformed FILETIME;
- data whose declared extent does not exactly match the bounded entry body.

Output fields, record ordering, per-key indexes, and handling of all non-Windows
10 formats remain unchanged.

## Testing

Add focused regressions proving that:

- valid 48-byte and 52-byte Windows 10 caches parse without diagnostics when
  their advisory header count is stale;
- `RegAppCompatCache` does not add a `RunReport` error for that condition;
- existing malformed and truncated Windows 10 entry tests still diagnose
  structural corruption;
- the supplied Server 2016 hive runs without warnings or errors and emits 747
  records from `ControlSet001` plus 746 from `ControlSet002`.

Run the focused AppCompatCache tests and the complete repository test suite.
