# Common Security Descriptor XML Migration Design

## Context

The `fix/security-descriptor-robustness` branch in `dfir-ogre-common` changes
the Python-facing binary security descriptor schema. The optional singular
`sacl_ace` and `dacl_ace` objects become the `sacl_aces` and `dacl_aces`
arrays. ACE records can also contain `ace_size`, `object_type_guid`,
`inherited_object_type_guid`, and `raw_hex`, while `account_sid` becomes
optional.

The Windows plugin repository contains 28 XML mappings for records produced
by this common parser: 27 objects named `key_security` and the generic Hive
parser object named `descriptor`.

Scheduled Tasks also emits a field named `security_descriptor`. That field is
different: it parses an SDDL string with the local Python
`security_descriptor.py` implementation. It does not consume the binary
descriptor API from `dfir-ogre-common` and remains unchanged.

## Output Contract

Every common-produced descriptor mapping will declare `sacl_aces` and
`dacl_aces` as arrays of ACE objects. Each ACE mapping includes:

- `ace_type`;
- `ace_flags`;
- `rights`;
- `account_sid`;
- `ace_size`;
- `object_type_guid`;
- `inherited_object_type_guid`; and
- `raw_hex`.

Optional ACE fields may be absent without rejecting the containing record.
The old singular object names will not remain in common-produced XML
mappings.

Scheduled Task `security_descriptor` retains its existing local SDDL schema,
including the list-valued singular keys `sacl_ace` and `dacl_ace`. The field
remains a dynamic XML object so this migration cannot accidentally couple it
to the binary common schema.

## Python Changes

No production Python changes are required. Registry plugins already call
`RegKey.security_descriptor.to_record()` and do not access the renamed common
attributes directly. The local Scheduled Task SDDL serializer remains
unchanged.

## XML Changes

Replace each common descriptor's singular `dacl_ace` object with two
array/object mappings, one for `sacl_aces` and one for `dacl_aces`. Preserve
the existing owner SID, group SID, control flag, timeline, qualifier, and
top-level output mappings.

The migration covers all 27 `key_security` configurations plus
`configuration/hive.xml`. It does not expand or otherwise change
`configuration/registry/scheduled_task.xml`'s local `security_descriptor`
object.

## Error Handling and Compatibility

No dual-write aliases are emitted for common-produced records. Keeping both
singular and plural common names would duplicate forensic data and hide
incomplete migrations.

Malformed, unknown, or partial binary ACEs remain representable because the
new diagnostic fields are optional. Local SDDL parsing and omission behavior
are outside this common API migration and stay unchanged.

## Tests and Verification

- Assert that Scheduled Task's local SDDL serializer and dynamic XML object
  retain their original singular schema.
- Validate all 28 common descriptor mappings repository-wide, including both
  plural arrays, nested array fields, scalar ACE fields, and absence of the
  old singular XML objects.
- Run Scheduled Task integration against a fresh build of common commit
  `ff2c2e4` to prove local SDDL remains singular while `key_security` is
  plural.
- Parse every XML configuration and run the complete Windows plugin test
  suite against that common build.

## Scope

This change migrates only binary security descriptor records produced by
`dfir-ogre-common`. It does not change registry traversal, plugin selection,
timeline behavior, the local SDDL parser, or unrelated descriptor-like data.
