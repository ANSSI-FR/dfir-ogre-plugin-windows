# Windows 8.x AppCompatCache Package-Only Entry Design

## Problem

The Windows 8.x AppCompatCache format can contain a structurally valid entry
with no file path and a populated package field. The supplied Windows 8.1
SYSTEM hive contains one such entry for
`microsoft.windowscommunicationsapps`: its path size is zero, its package size
is 186 bytes, and its flags, FILETIME, data size, declared body boundary, and
following entry marker are all valid.

The shared UTF-16 decoder currently rejects every zero-byte string before the
Windows 8.x parser reads the package field. The plugin therefore reports a
malformed-path error for a valid package-only entry. It still emits the other
112 path records, but the false diagnostic marks the parser run as failed.

## Decision

Treat a Windows 8.x entry as a valid, non-emitting package record when:

- its path size is zero;
- its package size is nonzero; and
- the package extent, flags, FILETIME, data size, optional data, and exact body
  boundary all pass the existing structural validation.

The Windows 8.x parser will not send this entry to the path-oriented output
schema and will not add a diagnostic. Other formats will keep the shared
nonempty-path requirement.

Represent this outcome explicitly in the internal body-parser contract:
`AppCompatCacheEntry | None`. The variable-entry loop will append a parsed
entry only when the body parser returns an `AppCompatCacheEntry`; diagnostics
will still be preserved for both emitting and non-emitting entries.

## Alternatives Considered

- Return an `AppCompatCacheEntry` with an empty path and filter it in
  `RegAppCompatCache`. This would leak a non-path record through the parser
  model and make the registry plugin responsible for a binary-format detail.
- Extend the public record schema with a package-identity field. This would
  preserve the package metadata but expands the schema and downstream
  compatibility surface beyond the requested error correction.
- Return an explicit non-emitting result from the Windows 8.x body parser.
  This keeps format semantics in the format parser and preserves the current
  output schema. This is the selected approach.

## Preserved Errors

The exception is limited to a nonempty package record. The parser will continue
to report:

- a zero-length path with no package data;
- an odd-length or invalid nonempty UTF-16 path;
- a package extent that leaves the flags outside the bounded entry body;
- truncated flags, FILETIME, data-size, or data fields;
- a declared body layout that does not consume the body exactly;
- invalid FILETIME values according to the existing recoverable-diagnostic
  behavior; and
- malformed values in Windows XP through Windows 11 formats.

Package bytes remain opaque, as in the existing Windows 8.x parser. A nonzero
package length is validated by its bounded extent rather than by assuming a
text encoding.

## Testing

Add regression coverage that:

- places a valid package-only entry between two normal entries for both
  Windows 8.0 and Windows 8.1;
- verifies only the two path entries are returned and no diagnostic is added;
- verifies a zero-path entry with a package extent outside its bounded body is
  still diagnosed while the following valid entry is recovered; and
- verifies a zero-path, zero-package entry remains malformed.

Run the focused format and plugin suites. Finally, run the supplied Windows 8.1
hive through the CLI and verify it produces the same 112 path records without a
warning or parser error.
