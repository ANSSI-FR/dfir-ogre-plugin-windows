# Scheduled Task Security Descriptor Migration Design

## Context

The `fix/security-descriptor-robustness` branch in `dfir-ogre-common` changes
the Python-facing security descriptor schema. The optional singular
`sacl_ace` and `dacl_ace` objects become the `sacl_aces` and `dacl_aces`
arrays. ACE records can also contain `ace_size`, `object_type_guid`,
`inherited_object_type_guid`, and `raw_hex`, while `account_sid` becomes
optional.

Scheduled Tasks is the pilot migration because it emits two security
descriptor records:

- `security_descriptor`, parsed from the task's SDDL value by the local
  `security_descriptor.py` implementation; and
- `key_security`, provided by `RegKey.security_descriptor` from
  `dfir-ogre-common`.

The local SDDL implementation is the only Python code in this repository that
directly implements the old singular ACE field names. Other registry plugins
call `SecurityDescriptor.to_record()` without accessing those names directly.

## Output Contract

Both Scheduled Task descriptor records will expose `sacl_aces` and
`dacl_aces` as arrays. Empty or absent ACLs remain empty or omitted according
to the existing producer behavior; consumers must not receive the old
singular names.

The local SDDL record retains its existing owner, group, ACL flag, ACE flag,
rights, SID, resource attribute, and GUID semantics. This pilot only renames
its ACE containers to match the plural common schema.

The common `key_security` mapping will declare both ACE arrays and all fields
available from the robustness branch:

- `ace_type`;
- `ace_flags`;
- `rights`;
- `account_sid`;
- `ace_size`;
- `object_type_guid`;
- `inherited_object_type_guid`; and
- `raw_hex`.

Optional ACE fields may be absent without causing the Scheduled Task record to
be rejected.

## Python Changes

Rename the local `SecurityDescriptor` attributes and serialized record keys
from `dacl_ace` and `sacl_ace` to `dacl_aces` and `sacl_aces`. Parsing remains
best-effort and preserves ACE order.

The calls in `registry/scheduled_task.py` already serialize both descriptor
producers through `to_record()`, so they require no artificial wrapper or
compatibility branch. The local serializer is imported only by Scheduled
Tasks, keeping the pilot isolated.

## XML Changes

In `configuration/registry/scheduled_task.xml`, expand the task SDDL
`security_descriptor` mapping to declare its plural ACE arrays and existing
SDDL fields.

Replace the singular `key_security.dacl_ace` object with plural
`key_security.sacl_aces` and `key_security.dacl_aces` array/object mappings.
Each common ACE mapping includes the optional diagnostic fields introduced by
the sibling branch.

Timeline paths and top-level output field names remain unchanged.

## Error Handling and Compatibility

No dual-write compatibility aliases will be emitted. Producing both singular
and plural names would duplicate forensic data and hide incomplete migrations.

Malformed or partial common ACEs remain representable because every new
diagnostic field is optional. Existing SDDL parsing and omission behavior is
unchanged apart from the plural container names.

## Tests and Verification

Follow a red/green cycle:

1. Add a local serializer test that requires `dacl_aces` and `sacl_aces` and
   rejects the singular keys; run it and observe the expected failure.
2. Add a Scheduled Task XML contract test requiring array/object mappings for
   both descriptors and the new common ACE fields; run it and observe the
   expected failure.
3. Make the minimal Python and XML changes and rerun the focused tests.
4. Build the sibling robustness branch and run the Scheduled Task integration
   tests against that build, not the older common package currently installed
   in the Windows plugin virtual environment.
5. Run configuration validation and the complete Windows plugin test suite.

## Scope

This pilot changes only the shared local SDDL serializer, Scheduled Task XML,
and their focused tests. It does not migrate the other affected registry XML
files, add compatibility aliases, alter registry traversal, or change
Scheduled Task timeline behavior. Once reviewed, the same common
`key_security` XML pattern can be applied mechanically to the remaining
plugins.
