# GUID Lowercase and CLSID TreatAs Design

## Context

The registry CLSID parser opens a `TreatAs` subkey but reads the default value
from the parent CLSID key. This emits the CLSID description (for example,
`Sound (OLE2)`) instead of the redirect CLSID stored in `TreatAs\(default)`.

GUID-like identifiers are also emitted with inconsistent casing. Values built
with Python's `uuid.UUID` are lowercase, several LNK fields are explicitly
lowercased, and the primary CLSID field is lowercase, while passthrough fields
such as VSS snapshot IDs, EVTX provider GUIDs, and Amcache CLSIDs can retain
uppercase source text. Casing should not depend on which parser produced a
semantically equivalent identifier.

## Output Policy

Emit canonical hyphenated GUID, UUID, and CLSID values in lowercase whenever
the output field semantically represents one of those identifiers. Preserve
the source representation apart from letter case:

- keep surrounding braces when the source has braces;
- keep the canonical hyphens;
- leave null, malformed, and non-GUID values unchanged; and
- lowercase an exact GUID value only, never a GUID substring embedded in a
  path, command, description, JSON value, or other free-form text.

The policy applies equally to registry, XML, CSV, SQLite, EVTX, WER, LNK, and
other structured sources. It includes polymorphic fields only when the complete
value has canonical GUID syntax. It does not reinterpret volume serials, hashes,
SIDs, OIDs, collection snapshot labels, or arbitrary registry value names as
GUIDs.

Raw evidence containers remain untouched. Examples include Scheduled Task
registry subrecords, legacy EVT message arrays, generic dynamic payload values,
and descriptive or path fields. Their typed, top-level GUID counterparts are
normalized, while the raw copies retain the evidence as stored.

## Shared Normalization

Add a small shared normalizer in `common.py`. It recognizes only a complete
canonical GUID in `8-4-4-4-12` hexadecimal form, with optional matching braces,
and returns its lowercase form. All other input is returned unchanged. A
recursive companion handles list/tuple values used by registry fields without
changing their container type or output schema.

Expose the same behavior through an `AbstractParser` implementation for
configuration-driven parsers. XML configurations can select that parser for
known GUID fields while retaining the existing default string parser for all
other data. This is safer than globally lowercasing strings and allows fields
such as Activity Cache's `AppActivityId` to preserve non-GUID identifiers.

Fields already produced through `uuid.UUID`, or already configured with the
equivalent lowercase parser, keep their current implementation unless a shared
helper materially improves correctness. Regression tests will establish that
their output follows the same policy.

## CLSID TreatAs Correction

After opening the optional `TreatAs` subkey, read its own `(default)` value.
When it contains a GUID, emit the normalized lowercase value in `treat_as`.
When the subkey or its default value is absent, omit `treat_as` as before.
Malformed data continues through the parser's existing reporting boundary, so
one bad CLSID cannot stop parsing the rest of the hive.

The primary CLSID key name remains the source of `guid` and is routed through
the shared normalizer. Descriptions remain unchanged even if their text happens
to resemble or contain a GUID.

## Structured Integration Points

Apply the policy at typed output boundaries rather than as a global output
rewrite:

- registry CLSID and `TreatAs` values;
- Scheduled Task primary GUIDs, storage volume GUIDs, Amcache GUID fields and
  MSI codes, and security-descriptor object GUIDs;
- VSS snapshot and shadow-copy identifiers whose source columns are explicitly
  GUIDs;
- Amcache IE add-on CLSIDs;
- WER report/session GUIDs;
- EVTX provider GUIDs and explicitly typed `ClassGuid` event-data fields;
- Activity Cache activity IDs when their complete value is a GUID; and
- LNK header, target-item, property-store, known-folder, product-code, and
  Droid identifiers.

Python-generated UUID fields in Recent App, Shim Database, Scheduled Task COM
handlers, SIP, and IE WebCache remain naturally lowercase and are covered by
focused or existing tests. Generic fields named `snapshot_id` that carry an
analyst-defined collection label are not normalized merely because of their
name.

## Error Handling

GUID case normalization is lossless and does not add warnings or
`RunReport.errors`. Invalid values are preserved rather than rejected so the
parser continues and forensic evidence remains available. The CLSID parser's
existing per-key error reporting remains responsible for genuine read or parse
failures.

## Tests

- Unit-test the normalizer with braced and unbraced mixed-case GUIDs, invalid
  strings, embedded GUID text, nulls, and list/tuple inputs.
- Update the CLSID fixture expectation to the real `TreatAs` child value and
  assert lowercase output.
- Add focused parser tests using uppercase fixture or synthetic values for each
  newly configured integration point, including polymorphic Activity Cache and
  EVTX dynamic event data.
- Assert non-GUID identifiers and GUIDs embedded in paths/descriptions remain
  byte-for-byte unchanged.
- Validate every XML parser configuration and run the complete unit-test suite.

## Scope

No field names, braces, schemas, timeline qualifiers, registry traversal, or
artifact selection rules change. The work fixes the `TreatAs` source key and
standardizes only the casing of semantically typed GUID/UUID/CLSID outputs.
