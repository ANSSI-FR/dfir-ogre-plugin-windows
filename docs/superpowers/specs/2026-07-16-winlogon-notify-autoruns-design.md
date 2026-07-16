# Winlogon Notify Autoruns Design

## Problem

`RegAutorunsSoftware` and `RegAutorunsUser` look for `DllName` directly on the
`Winlogon\Notify` container key. Microsoft documents each Winlogon notification
package as an immediate child key beneath `Notify`, with `DllName` stored in the
package key. The current paths therefore miss documented Winlogon Notify
persistence.

The bundled SOFTWARE and NTUSER test hives do not contain Winlogon Notify
packages, so the existing integration tests cannot expose the omission.

Reference:
https://learn.microsoft.com/en-us/windows/win32/secauthn/registry-entries

## Goals

- Enumerate immediate package keys beneath `Winlogon\Notify`.
- Read `DllName` from each package key.
- Apply the same behavior to HKLM SOFTWARE and HKCU user hives.
- Preserve support for a nonstandard `DllName` stored directly on `Notify`.
- Preserve the existing autoruns record schema and registry metadata.

## Non-goals

- Recursively inspect descendants below a notification package key.
- Parse notification handler values such as `Logon`, `Logoff`, or `Shutdown`.
- Validate that a referenced DLL exists or is executable.
- Add or modify an opaque binary registry-hive fixture.
- Refactor unrelated autoruns persistence mappings.

## Design

Keep the existing data-driven autoruns traversal. For the `Winlogon Notify`
entry in both `SOFTWARE_KEYS` and `USER_KEYS`, retain the exact
`...\Winlogon\Notify` path and add a second path ending in
`...\Winlogon\Notify\*`. Both paths target only `DllName`.

The exact path preserves compatibility with nonstandard hives handled by the
current parser. The single-segment wildcard enumerates the documented package
keys without inspecting deeper descendants. Each matching key continues
through `parse_key`, so a record is emitted only when that specific key has a
non-empty `DllName`.

Records keep the existing `Winlogon Notify` type and values structure. The
`key_path`, `key_modif_time`, and `key_security` fields come from the key that
contains `DllName`. Consequently, a documented package record identifies and
describes the package child key rather than its `Notify` parent.

If both the parent and one or more child keys contain `DllName`, each key is
emitted as a separate forensic artifact. They have distinct registry paths and
metadata even when their DLL strings happen to match.

## Error Handling

No new error handling is required. A parent or package key without a non-empty
`DllName` remains silently skipped by `parse_key`. Registry traversal or value
read failures continue to be caught by the plugin's existing parse boundary and
reported through `RunReport.errors` while preserving any output written before
the failure.

## Testing

Add controlled registry doubles because the bundled binary hives lack Notify
packages. Exercise the SOFTWARE and user plugin paths at parser level and
verify that:

- A direct-parent `DllName` remains supported.
- An immediate child package with `DllName` is emitted.
- A child without `DllName` is not emitted.
- HKLM and HKCU use the same parent-plus-child control flow.
- Child records carry the child key path and metadata through the unchanged
  output schema.

Run the focused autoruns hive tests followed by the complete test suite.
