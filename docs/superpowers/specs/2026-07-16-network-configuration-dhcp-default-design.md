# Network Configuration DHCP Default Design

## Context

`RegNetworkConfig.parse_key` currently checks the `RegKey.values` method object
instead of calling it. Because bound methods are truthy, empty interface keys pass
the guard. A missing `EnableDHCP` value then returns `None`, which enters the
DHCP-enabled branch and fabricates a DHCP record.

## Behavior

- Empty interface keys produce no network configuration records.
- A nonempty interface key without `EnableDHCP` is treated as static
  configuration (`dhcp: false`) so its available forensic data remains visible.
- Explicit `EnableDHCP` values continue to select the existing static (`0`) or
  DHCP-enabled (nonzero) parsing paths.

## Implementation

Call `key.values()` in the empty-key guard. Read `EnableDHCP` with a default of
`0`, then retain the existing static and DHCP parsing logic. No output schema or
configuration changes are required.

For static configuration, records continue to be emitted for paired
`IPAddress` and `SubnetMask` entries. Therefore a nonempty key with a missing
`EnableDHCP` value retains its static addresses, while a key without network
address data does not create a placeholder record.

## Error Handling

The existing exception handling remains unchanged: malformed registry data is
reported through `RunReport`. The new default applies only when `EnableDHCP` is
absent.

## Tests

- Add a focused regression test using a nonempty key with static address data
  but no `EnableDHCP`; assert that one record is written with `dhcp: false` and
  the static address data.
- Update the SYSTEM hive integration expectation from six records to four,
  demonstrating that its two empty interface keys no longer fabricate DHCP
  records while explicit static and DHCP-enabled interfaces remain present.

## Scope

This change does not alter the output schema, reinterpret explicit DHCP values,
or refactor the surrounding parser.
