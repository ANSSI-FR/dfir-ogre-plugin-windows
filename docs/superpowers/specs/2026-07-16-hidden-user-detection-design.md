# Hidden User Detection Design

## Problem

`RegUserProfile` reads account visibility overrides from
`HKLM\Software\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList`.
It currently treats every nonzero registry value as hidden. Microsoft-hosted
guidance documents the opposite behavior: DWORD `0` hides the named account,
while DWORD `1` or removing the value makes it visible.

The existing `SOFTWARE.dat` test fixture has no `UserList` values, so the
integration test cannot detect this reversal.

Reference:
https://learn.microsoft.com/en-us/answers/questions/3862202/why-windows-11-not-saving-multiple-users-username

## Goals

- Parse DWORD `0` as `is_hidden: true`.
- Parse a nonzero DWORD as `is_hidden: false`.
- Preserve `is_hidden: null` when no matching `UserList` value exists.
- Match registry value names to profile directory names without regard to
  letter case.
- Add a regression test that exercises the real parser and output mapping.

## Non-goals

- Change how profile names, SIDs, state flags, or registry metadata are emitted.
- Infer visibility from policies outside `SpecialAccounts\UserList`.
- Add or modify an opaque binary registry-hive fixture.

## Design

Extract collection of `UserList` values into a small helper. The helper will
return a mapping from case-normalized account names to their explicit hidden
state:

- `value.data() == 0` maps to `True`.
- Any nonzero value maps to `False`.

Profile parsing will use a case-normalized lookup key while preserving the
existing `user_name` output format. It will emit `is_hidden` whenever an
explicit mapping exists, including `False`. If no mapping exists, it will omit
the field and the configured output will continue to represent it as `null`.

This retains three distinct forensic states:

| Registry evidence | Output |
| --- | --- |
| Matching value is `0` | `is_hidden: true` |
| Matching value is nonzero | `is_hidden: false` |
| No matching value | `is_hidden: null` |

## Error Handling

Registry loading and profile-key error handling remain unchanged. The registry
API currently returns DWORD data as integers; the helper uses the same direct
value comparison as the existing parser, with only the hidden/visible meaning
corrected.

## Testing

Extend `tests/hive/test_user_profile.py` with a registry wrapper that delegates
profile enumeration to the real `SOFTWARE.dat` fixture and injects synthetic
`UserList` values. This keeps the test at parser/output level without adding a
binary hive.

The regression test will verify:

- A mixed-case account name with value `0` produces `true`.
- A mixed-case account name with value `1` produces `false`.
- A profile with no `UserList` entry remains `null`.
- The complete test suite still passes.
