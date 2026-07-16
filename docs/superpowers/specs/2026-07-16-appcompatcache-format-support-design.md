# AppCompatCache Multi-Version Parsing Design

## Problem

`RegAppCompatCache` currently derives one of three header offsets from the first
DWORD and then scans the remaining value byte by byte for `10ts`. This only
handles Windows 8.1 and Windows 10 style entries. Fixed-layout caches from
Windows XP through Windows 7 never contain that marker, and Windows 8.0 uses
`00ts`, so valid values from those systems produce no records and no
diagnostic. An unrecognized value follows the same silent-success path.

The current Windows 8.x body parsing is also unsafe. It unconditionally skips
two bytes before the flags. Windows 8.0 has no such field, while Windows 8.1
stores a two-byte unknown field after the flags, so the flags and FILETIME are
read at the wrong offsets for both layouts.

The Windows XP cache is stored below `Session Manager\AppCompatibility`, while
the plugin only searches `Session Manager\AppCompatCache`.

The failure was reproduced with synthetic valid Windows 7 x64 and Windows 8.0
values and with an unknown signature. Each case produced zero records and zero
`RunReport` errors.

References:

- https://winreg-kb.readthedocs.io/en/latest/sources/system-keys/Application-compatibility-cache.html
- https://winreg-kb.readthedocs.io/en/latest/_modules/winregrc/appcompatcache.html
- https://github.com/mandiant/ShimCacheParser

## Goals

- Parse the documented AppCompatCache formats from Windows XP through Windows
  10, including 32-bit and 64-bit fixed layouts.
- Search both the XP and post-XP registry containers in every available control
  set.
- Preserve the existing output fields and their meanings.
- Preserve all records parsed before a later malformed entry when the next
  entry boundary is trustworthy.
- Report unsupported or malformed data explicitly instead of returning a
  successful empty result.
- Preserve current Windows 10 output ordering and record counts.

## Non-goals

- Add fields for cache format, architecture, file size, last-update time,
  insertion flags, shim flags, or opaque data blobs.
- Change the XML output schema.
- Interpret AppCompatCache presence as proof of execution.
- Parse the separate Windows 2000 `AppCompatibility` model.
- Normalize or remove stored path prefixes such as `\??\`.
- Identify Server 2003 versus Vista from the shared `0xbadc0ffe` signature when
  that distinction does not affect the retained output fields.
- Add a third-party parsing dependency.

## Format Detection

Replace the marker scan with a dispatcher that recognizes a format only at its
documented location:

| Family | Discriminator | Header | Entry layout |
| --- | --- | ---: | --- |
| Windows XP x86 | DWORD `0xdeadbeef` | 400 bytes | fixed 552 bytes |
| XP x64 / Server 2003 / Vista / Server 2008 | DWORD `0xbadc0ffe` | 8 bytes | fixed 24-byte x86 or 32-byte x64 |
| Windows 7 / Server 2008 R2 | DWORD `0xbadc0fee` | 128 bytes | fixed 32-byte x86 or 48-byte x64 |
| Windows 8.0 / Server 2012 | `00ts` at offset 128 | 128 bytes | variable |
| Windows 8.1 / Server 2012 R2 | `10ts` at offset 128 | 128 bytes | variable |
| Windows 10 | `10ts` at offset 48 or 52 | 48 or 52 bytes | variable |

Windows 8.x is gated by the entry marker at offset 128 rather than solely by
the first DWORD because zero-valued first DWORDs have been observed. Windows 10
requires its header length and marker to agree.

A fixed format uses its declared cached-entry count. For XP, the cached-entry
count at offset 4 controls the array; the LRU count and index table are header
metadata and are validated separately. Counts and computed table boundaries
must fit within the value before parsing starts.

For the shared post-XP fixed layouts, determine x86 versus x64 from the
serialized `UNICODE_STRING`: the x64 form has alignment padding and a 64-bit
path offset. Validate the candidate entry size, path lengths, path offset, and
array bounds. If neither candidate is internally consistent, treat the value
as malformed rather than guessing.

A recognized header with no bytes beyond its declared header size is a valid
empty cache. In particular, an exact 128-byte value beginning with the Windows
8 header size and exact 48-byte or 52-byte values beginning with the matching
Windows 10 header size are accepted without requiring a first entry marker. A
recognized header followed by unexpected bytes is malformed. A value that
matches no supported discriminator is unsupported.

## Entry Parsing

Use small, format-specific parsing functions that return a common internal
entry containing only the values needed by the existing output:

- path;
- modification FILETIME;
- optional raw `flag1` and `flag2` bytes for Windows 8.x.

XP entries decode the null-terminated UTF-16LE path from the fixed path field
and the modification FILETIME at its fixed offset. Other fixed layouts decode
the UTF-16LE path through the validated absolute offset and length and read the
modification FILETIME from the architecture-specific entry structure. Other
documented fields are consumed or bounds-checked as necessary but not emitted.

Windows 8.0 and 8.1 entries advance sequentially using the 12-byte entry header
and declared body size. After the path, Windows 8.0 stores `flag1`, `flag2`, the
modification FILETIME, and a trailing data size. Windows 8.1 stores `flag1`,
`flag2`, a two-byte unknown field, the modification FILETIME, and a trailing
data size. Any trailing data must fit within the declared body. `flag1` and
`flag2` remain raw four-byte values so `value()` continues to emit the same
`0x...` strings.

Windows 10 entries use the same bounded variable-entry envelope but read only
the path and immediately following modification FILETIME. The cached-entry
count at header offset 36 for a 48-byte header or offset 40 for a 52-byte header
is validated against the sequential entries. The parser never searches
arbitrary payload bytes for another entry marker.

Paths are decoded strictly as UTF-16LE and kept as stored, excluding only the
format's terminator. Entry indexes remain zero-based and restart for each
registry key, matching current behavior.

## Output Compatibility

Every successful entry continues to emit exactly:

- `index`;
- `path`;
- `modification_date`;
- `flag1` and `flag2` only for Windows 8.x;
- `key_path`;
- `key_modif_time`;
- `key_security`.

No configuration change is required. Registry metadata is copied from the key
containing the `AppCompatCache` value. Existing Windows 10 fixtures must retain
their current paths, ordering, timeline metadata, and record counts.

## Registry Discovery

For every `*ControlSet*`, query both:

- `Control\Session Manager\AppCompatibility` for Windows XP;
- `Control\Session Manager\AppCompatCache` for later systems.

Each matching key is parsed independently. A failure in one container or
control set must not prevent the remaining matching keys from being attempted.

## Error Handling and Recovery

Use a single diagnostic helper that logs one warning and calls
`RunReport.add_error()` with the key path, format or signature, and concise
reason.

- Missing or non-byte `AppCompatCache` values are malformed inputs.
- Values shorter than the minimum discriminator are malformed.
- Unknown signatures are unsupported.
- Invalid counts, entry sizes, path ranges, UTF-16LE strings, or FILETIMEs are
  malformed.
- An invalid FILETIME produces a null `modification_date` and a diagnostic, but
  does not discard an entry whose path and boundary are otherwise valid.
- A bad fixed entry can be skipped and the following fixed boundary attempted.
- A bad variable entry can be skipped only when its declared total size is
  valid and in bounds.
- If the next boundary cannot be trusted, stop parsing that cache value.
- Continue with other registry keys after any per-key failure.

This preserves useful records before and, where safe, after localized damage
without byte-scanning into payload data or silently accepting corruption.

## Testing

Add synthetic binary builders and focused parser tests covering:

- XP x86, including discovery through `AppCompatibility`;
- the `0xbadc0ffe` x86 and x64 layouts;
- Windows 7 x86 and x64;
- Windows 8.0 `00ts`;
- Windows 8.1 `10ts` at offset 128;
- distinct Windows 8.0 and 8.1 bodies to prove the two-byte Windows 8.1 field
  is handled at the correct position;
- Windows 8.x entries with trailing data to prove declared-size validation;
- Windows 10 headers of 48 and 52 bytes;
- valid empty caches;
- an unsupported signature producing no records, one warning, and one
  `RunReport` error;
- truncated headers, out-of-range fixed paths, oversized variable entries, and
  malformed UTF-16LE;
- safe recovery after a damaged entry and safe termination when the next
  boundary is unknowable;
- unchanged field names and absence of newly proposed forensic fields.

Retain the existing real-hive integration tests as Windows 10 regression tests,
then run the complete test suite.
