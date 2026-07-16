# Portable BAM Timestamp Decoding Design

## Context

`RegBamDam.parse_key` decodes the first eight bytes of each BAM/DAM value with
`struct.unpack("L", ...)`. Without a format prefix, Python uses the platform's
native byte order and C type size. Native `unsigned long` is eight bytes on the
current Linux environment but four bytes on Windows, where unpacking an
eight-byte buffer fails.

## Behavior

- Decode the first eight bytes as one little-endian unsigned 64-bit integer.
- Preserve the existing FILETIME conversion, record schema, filtering, and
  per-value error handling.
- Produce the same timestamps on the current little-endian Linux fixture while
  also working where native `unsigned long` is four bytes.

## Implementation

Replace the native `"L"` format with the explicit standard format `"<Q"` in
the existing `struct.unpack` call. Do not add a helper, abstraction, or parser
refactor.

## Tests

Add one focused regression that parses a real BAM key while wrapping
`struct.unpack` to emulate Windows' four-byte native `L`. The current code must
fail to emit records under that emulation; the `"<Q"` implementation must emit
the expected records without a report error. Keep the existing full BAM hive
integration test unchanged.

## Scope

No output configuration, dependencies, or unrelated registry parsing behavior
changes.
