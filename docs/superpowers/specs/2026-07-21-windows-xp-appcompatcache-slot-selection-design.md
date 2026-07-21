# Windows XP AppCompatCache Slot Selection Design

## Problem

The Windows XP AppCompatCache parser treats the DWORD at offset `0x04` as the
number of populated records and parses every declared fixed-size slot. Real XP
caches can serialize all 96 slots while using the LRU metadata at offset `0x08`
and the index table at offset `0x10` to identify the populated slots.

`tests/data/hive/SYSTEM_WIN_XP_SP2.data` contains two such caches. Both allocate
96 slots, while their LRU tables reference 18 and 12 populated slots. The
current parser recovers those 30 records but also attempts to decode the 162
unused all-zero slots. Each empty path becomes a recoverable parser diagnostic,
which `RegAppCompatCache` promotes to a `RunReport` error.

The synthetic XP test builder does not reproduce this layout: it makes the
allocated count, LRU count, and serialized slot count all equal to the number
of populated paths. Consequently, all existing tests pass while the real XP
fixture produces false errors.

## Goals

- Parse only the populated Windows XP slots identified by valid LRU indexes.
- Continue using the allocated slot count for cache-size and slot-boundary
  validation.
- Preserve the current output schema and deterministic physical-slot ordering.
- Continue reporting genuine corruption in an active slot.
- Add regression coverage for the real fixed-capacity XP representation.
- Leave every post-XP format parser unchanged.

## Non-goals

- Recover unreferenced nonzero XP slots as active records.
- Add a slack-space or deleted-entry recovery mode.
- Interpret the LRU table as evidence of execution or expose recency metadata.
- Change record fields, registry discovery, output configuration, or diagnostic
  plumbing.
- Refactor the Windows 2003/Vista, Windows 7, Windows 8.x, or Windows 10 parser.

## Selected Design

The XP header will be interpreted as two related bounds:

- the DWORD at offset `0x04` is the number of allocated fixed-size slots;
- the DWORD at offset `0x08` is the number of active LRU index values;
- each DWORD beginning at offset `0x10` identifies an active slot.

The allocated count remains bounded to 96. It continues to determine the end of
the 552-byte slot array, so truncated arrays and true trailing data retain their
existing diagnostics.

The LRU count must not exceed the allocated count. Every LRU index must be less
than the allocated count and must occur only once. An invalid count, duplicate,
or out-of-range index makes the XP header inconsistent and raises an
`AppCompatCacheParseError`; parsing arbitrary slots after that point would risk
presenting stale data as active evidence.

After validation, the parser will parse the referenced slot indexes in ascending
numeric order. Sorting preserves the existing physical-slot output order rather
than changing records to an undocumented most- or least-recently-used order.
The public `index` field remains a zero-based sequence assigned by
`RegAppCompatCache`, as it is today.

An empty or malformed path in a referenced slot remains a diagnostic and the
parser continues at the next trustworthy fixed boundary. Unreferenced slots are
not decoded and therefore produce neither records nor diagnostics. This avoids
mixing inactive or remnant data into canonical AppCompatCache output.

## Alternatives Considered

### Ignore structurally empty slots

The parser could continue scanning all allocated slots and silently skip an
all-zero entry. This is a smaller code change, but it ignores authoritative LRU
metadata and can still emit unreferenced remnant data as an active record.

### Parse the first LRU-count slots

This fixes the supplied fixture because its populated slots are contiguous. It
is not correct for a cache whose LRU table references non-contiguous or reused
slot indexes.

### Parse slots in LRU order

This uses the right active set but changes output order and assigns a meaning to
the LRU direction that the format documentation does not establish. Physical
slot order is safer and backward-compatible.

## Error Handling

The XP parser will reject these header-level inconsistencies before decoding
entries:

- allocated slot count greater than 96;
- LRU count greater than the allocated slot count;
- an LRU index outside the allocated slot array;
- a duplicate LRU index;
- an allocated array extending beyond the cache value.

Existing recoverable entry diagnostics remain unchanged for invalid UTF-16,
missing terminators, and invalid FILETIMEs in referenced slots. Bytes after the
complete allocated array remain a trailing-data diagnostic.

## Testing

Automated test-first coverage will include:

1. A 96-slot XP cache with two active records and 94 unused zero slots. It must
   return two entries and no diagnostics.
2. A cache whose LRU table references non-contiguous slots in non-physical
   order. It must return only those slots in ascending physical order.
3. Invalid LRU metadata: count overflow, out-of-range index, and duplicate
   index.
4. Existing malformed referenced-entry and trailing-data behavior.
5. The complete AppCompatCache test modules, covering all supported Windows
   format families.

The fixed-capacity XP regression must fail against the current parser before
production code is changed. After the fix, all existing post-XP snapshots and
tests must remain unchanged.

The untracked `SYSTEM_WIN_XP_SP2.data` fixture will remain untouched and will
not be added to the repository. A local end-to-end verification will run the
plugin against it after the automated tests, expecting 30 unique cache records
and no `RunReport` errors.

## Compatibility and Expected Impact

Only `_parse_windows_xp()` and XP-specific test data/builders will change.
Windows XP real-hive parsing will stop reporting unused capacity as corruption.
Windows 2003/Vista, Windows 7, Windows 8.x, and Windows 10 use independent
parsing functions and receive no behavioral improvement or output change from
this fix. Running their existing tests provides regression assurance only.
