# AppCompatCache Missing-Value Handling Design

## Problem

`RegAppCompatCache` discovers both legacy and modern AppCompatCache container
keys, then treats a missing `AppCompatCache` value as a parser error. A Windows
Server 2003 R2 repair hive demonstrates that the container key can legitimately
exist with no values: the hive contains no AppCompatCache value or cache-format
signature, while the active SYSTEM hive from the same host contains a populated
cache and parses successfully.

The current behavior therefore turns absence of the artifact into a failed
plugin run even though there is no malformed cache data to diagnose. It was
introduced with the multi-version parser integration and is asserted together
with the genuinely invalid non-byte case in one unit test.

## Decision

Keep registry discovery unchanged. In `RegAppCompatCache.parse_key`, if
`key.value("AppCompatCache")` returns `None`, return without logging a warning
or adding a `RunReport` error. This represents “artifact absent” and emits no
records.

This decision supersedes only the missing-value classification in the earlier
multi-version AppCompatCache design. A present value remains parser input and
continues through all existing type and structural validation.

## Alternatives Considered

- Filter empty keys in `cache_keys`. This would avoid calling `parse_key`, but
  it mixes value validation into registry discovery and duplicates knowledge of
  the expected value name.
- Keep a warning without a `RunReport` error. This would still present normal
  artifact absence as exceptional and make batch output noisy.
- Use the localized early return in `parse_key`. This preserves the existing
  separation between discovery and per-key handling and changes only the
  disputed classification. This is the selected approach.

## Preserved Errors

The change does not relax validation for a present value. The plugin will
continue to report:

- a value whose decoded data is not `bytes`;
- a byte value that is too short;
- an unsupported cache signature;
- malformed counts, bounds, entry bodies, paths, or timestamps according to the
  existing recovery rules;
- registry API failures while retrieving or decoding the value.

## Testing

Split the combined missing/non-byte test into focused cases:

- a missing value produces no output, no warning, and no `RunReport` error;
- a present non-byte value still produces no output, one warning, and one
  `RunReport` error.

Run the real repair-hive reproduction to confirm it changes from one error and
zero rows to zero errors and zero rows. Run a populated SYSTEM-hive control to
confirm its records and clean report are unchanged. Finally, run the complete
AppCompatCache unit and format-parser suites.
