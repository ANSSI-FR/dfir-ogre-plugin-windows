# Hive Common Schema Compatibility Design

## Context

The upcoming `dfir-ogre-common` release changes `parse_hive_values` to emit
one flat record per registry value. Keys without values receive a placeholder
record so key metadata is retained. The accompanying reference mapping is
`../dfir-ogre-common/test_data/hive/hive.xml`.

This plugin already calls `parse_hive_values`, but `configuration/hive.xml`
still describes the previous nested key/value output. The reference mapping
also uses the parser command `Hive`, while the Windows plugin's established
public description is:

- command: `HiveKey`;
- description: `Extract Keys and Values from Windows Registry File`.

Both description values must remain unchanged.

## Approaches Considered

### Keep the established command in the updated mapping

Adopt the common reference mapping's new output schema while retaining
`parser="HiveKey"` on the root element. This keeps plugin discovery and
existing caller configuration stable while matching the new common record
shape. This is the selected approach.

### Register an additional `Hive` plugin command

An alias plugin could consume the reference mapping unchanged. This would
add a second public command for the same implementation and make plugin
selection and documentation ambiguous, so it is rejected.

### Preserve the complete legacy mapping

Keeping the `reg_keys` data type and nested `values` mapping would preserve
the previous output filename, but it would no longer describe the records
emitted by `parse_hive_values`. This is rejected because it would silently
drop or misrepresent data.

## Output Contract

The Python plugin description remains byte-for-byte unchanged. The XML root
continues to select it with `parser="HiveKey"`.

The output mapping adopts the common schema:

- data type `hive`, producing the `.hive` output suffix;
- one record per real registry value;
- one placeholder record for a key without values;
- flat `path`, `mtime`, `name`, `data`, `type`, and `size` fields;
- `security_descriptor` containing owner, group, control flags, SACL ACEs,
  and DACL ACEs;
- `is_placeholder`, `invalid_signature`, and `error` diagnostic fields; and
- timeline descriptions containing both the key path and value name.

The former nested `values` array and `descriptor` object are removed from the
mapping because the common parser no longer emits them.

## Implementation

Replace `configuration/hive.xml` with the common reference mapping, changing
only its root parser command from `Hive` to `HiveKey`.

Leave `HiveKeys.description()` unchanged. Remove the unused
`parse_hive_keys` import because the implementation delegates exclusively to
`parse_hive_values`.

Update the hive integration test to retain assertions for the `HiveKey`
command and description text while expecting the `.hive.jsonl` filename and
flat output schema. Update the configuration schema test to recognize the
renamed `security_descriptor` object.

## Error Handling

No Python compatibility adapter is introduced. Parse errors, malformed value
signatures, and empty keys remain represented by the common parser's
`error`, `invalid_signature`, and `is_placeholder` fields respectively.
Existing `RunReport.last_error` handling remains unchanged.

## Tests and Verification

- First run the updated hive/configuration tests against the new common
  checkout to demonstrate the legacy mapping expectations fail.
- Assert the plugin command and description text remain exactly unchanged.
- Assert the output filename uses the new `hive` data type.
- Assert emitted rows use the flat schema, including placeholder and security
  descriptor fields and no nested `values` field.
- Run the complete test suite with `../dfir-ogre-common` installed as an
  editable dependency.

## Scope

This migration changes only the generic hive mapping and its tests. It does
not rename the Python class, change the plugin description, modify registry
plugins using `Registry`, or alter the common checkout.
