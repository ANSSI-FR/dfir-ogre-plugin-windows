# RecentApps, ACMru, and Explorer Search History Design

Date: 2026-07-23

## Context

`RegRecentApp` and `RegAcMru` currently have no positive end-to-end hive tests.
Their existing tests run against `tests/data/hive/NTUSER.dat`, which contains
neither artifact, and consider zero output successful.

Review against public implementations and compact public hives identified these
correctness gaps:

- `RegRecentApp` converts a missing `Arguments` value into the literal text
  `None` and appends it to `Path`.
- `RegRecentApp` omits the application-level `AppPath` value.
- `RegRecentApp` describes the artifact as generally available on Windows 10
  and later, although the key was populated only during a narrow Windows 10
  release period.
- `RegAcMru` does not expose the Search Assistant category subkey.
- `RegAcMru` emits registry values in hive enumeration order rather than
  numeric MRU order.
- `RegAcMru` attaches the category key LastWrite time to every search even
  though only the newest `000` entry can be correlated with that timestamp.
- `RegAcMru` is not explicitly described as a legacy Windows XP artifact.

Windows 7 and later use
`Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery` rather than
the Windows XP Search Assistant ACMru layout. WordWheelQuery uses binary
UTF-16LE values and a binary `MRUListEx` ordering value. Because its format,
path, version scope, and provenance differ from ACMru, it will be implemented as
a separate plugin.

## Goals

- Correct RecentApps path and argument handling without creating synthetic
  `"None"` text.
- Extract RecentApps `AppPath`.
- Give ACMru records deterministic numeric ordering and explicit category
  provenance.
- Associate registry LastWrite time only with the newest search in each MRU.
- Add a dedicated Explorer Search History parser for the `WordWheelQuery`
  artifact with correct `MRUListEx` ordering and UTF-16LE decoding.
- Replace zero-row end-to-end assertions with positive tests against two small
  public hives.
- Preserve immutable source URLs, SHA-256 hashes, and complete redistribution
  license texts for all newly committed fixtures.
- Keep existing parser command names and data types compatible. The new,
  previously unreleased search-history parser uses a descriptive public name
  rather than exposing the registry key's internal name.

## Non-goals

- Combining ACMru and WordWheelQuery into a generic `RegSearchHistory` command.
- Changing the common registry API.
- Recovering deleted registry values or slack space.
- Inferring timestamps for older MRU entries that do not have individual
  timestamps.
- Adding a downloaded Windows XP ACMru hive. No compact, redistributable public
  fixture containing the artifact was identified; ACMru behavior will therefore
  use focused in-memory key tests.

## Selected architecture

Keep three artifact-specific plugins:

1. `RegRecentApp` for the short-lived Windows 10 RecentApps artifact.
2. `RegAcMru` for the Windows XP Search Assistant ACMru artifact.
3. `RegExplorerSearchHistory` for Windows 7 and later Explorer search history
   stored in `WordWheelQuery`.

The search-history plugins will use similar output field names where their
semantics match, but will retain separate configurations and data types. This
preserves artifact provenance and avoids making one parser silently interpret
two unrelated binary layouts.

### Alternatives considered

1. **Extend `RegAcMru` to parse WordWheelQuery.**
   This requires fewer public commands, but makes the command name and
   description inaccurate and mixes category-based string values with a binary
   `MRUListEx` format.
2. **Replace both with `RegSearchHistory`.**
   This gives callers one cross-version command, but breaks existing
   `RegAcMru` configuration and weakens artifact-specific provenance.
3. **Keep separate plugins.**
   Each plugin has one registry path, format, and OS scope. Existing ACMru
   callers remain compatible, and WordWheelQuery failures cannot affect ACMru
   extraction. This is the selected approach.

## `RegRecentApp` changes

### Output behavior

For each application key:

- retain `guid_app`, `app_id`, `launch_count`, and
  `app_last_accessed_time`;
- add `app_path` from the application-level `AppPath` value; and
- continue emitting one application-only record when `RecentItems` is absent
  or empty.

For each recent item:

- retain `guid_file`, `display_name`, `path`, and
  `file_last_accessed_time`;
- make `path` the unmodified registry `Path` value;
- add a separate `arguments` field when the registry value is present; and
- leave `path` or `arguments` null/absent when their source value is missing.

The parser must never stringify a missing registry value into `"None"`.
Separating `path` and `arguments` also corrects the existing configuration text,
which labels a combined command line as a path.

### Description and configuration

The plugin description and XML documentation will identify RecentApps as a
short-lived Windows 10 artifact introduced in version 1607 and removed in
version 1709. The configuration will declare `app_path` and `arguments`, and
will describe `path` as the recent item's path rather than a synthesized command
line.

### Error handling

An invalid application or item GUID remains a per-key error recorded in
`RunReport`; it must not stop parsing unrelated application keys. Missing
optional values are normal and do not produce errors.

## `RegAcMru` changes

### Scope and discovery

The parser remains scoped to:

```text
\HKCU\Software\Microsoft\Search Assistant\ACMru\*
```

Its description and configuration will explicitly identify the artifact as
Windows XP Search Assistant history.

### Output behavior

For every non-empty ASCII decimal-named value below a category subkey, emit:

- `search_request`: the registry value data;
- `order_index`: the decimal value name converted to an integer;
- `category`: the category subkey name, such as `5001`, `5603`, `5604`, or
  `5647`;
- `key_path`; and
- `key_security`.

Values will be sorted by numeric `order_index` before output. Signed,
whitespace-padded, underscore-separated, non-ASCII, and otherwise non-decimal
value names will produce contextual `RunReport` errors and will be skipped
without suppressing valid sibling values.

Only the record with `order_index == 0` will contain `key_modif_time`. Older
records will leave that field null/absent because the category key LastWrite
time cannot be attributed to those searches. The existing timeline qualifier
can therefore remain attached to `key_modif_time` without generating falsely
timestamped events for older queries.

The unused `parse_date` and `parse_int` helpers will be removed.

Unexpected failures while enumerating or decoding one category will be reported
with that category's path and will not escape `parse_key` or suppress later
category keys.

## `RegExplorerSearchHistory`

### Registration and discovery

Add:

- `src/dfir_ogre_plugin_windows/registry/explorer_search_history.py`;
- `configuration/registry/explorer_search_history.xml`;
- an export from `src/dfir_ogre_plugin_windows/__init__.py`; and
- `tests/hive/test_explorer_search_history.py`.

The plugin command will be `RegExplorerSearchHistory`, and its output data type
will be `explorer_search_history`. The public name describes the evidence to a
user; `WordWheelQuery` remains in the technical description and error messages
because it is the literal registry key and format name. It will inspect:

```text
\HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\WordWheelQuery
```

An absent key or absent `MRUListEx` value is normal artifact absence and emits
no records or errors.

### MRU decoding

`MRUListEx` is parsed as a sequence of little-endian unsigned 32-bit integers.
Parsing stops at the `0xffffffff` terminator. The preceding integers are
registry value identifiers in most-recent-first order.

For each referenced value:

- require binary data;
- decode it as UTF-16LE;
- remove trailing UTF-16 NUL terminators without removing meaningful
  whitespace; and
- emit records in `MRUListEx` order.

Each record contains:

- `search_request`: decoded search text;
- `order_index`: zero-based position in the MRU sequence, where zero is newest;
- `value_index`: the numeric registry value identifier referenced by
  `MRUListEx`;
- `key_path`; and
- `key_security`.

Only `order_index == 0` receives `key_modif_time`, for the same timestamp
provenance reason as ACMru.

### Error handling

A malformed `MRUListEx` byte length, missing terminator, non-binary referenced
value, invalid UTF-16LE value, or reference to a missing value will add a
contextual error to `RunReport`.

Structural `MRUListEx` errors prevent output from that key because ordering is
not reliable. A bad individual referenced value is skipped while later valid
references continue to be parsed.

## Test fixtures

Add two raw, unmodified hive files under `tests/data/hive`:

### RecentApps

- Repository source:
  `mkorman90/regipy/regipy_tests/data/transactions_NTUSER.DAT.xz`
- Stored filename: `NTUSER_RECENT_APPS.dat`
- Stored size: 1,048,576 bytes
- Stored-file SHA-256:
  `e47f18fb696e4f18ff7432348561e4393f20336b80d0dd88e9c134e5575ecae1`

The source is XZ-compressed; the repository fixture will be the decompressed
hive so it can be consumed directly by `Registry.load`.

### Explorer Search History (`WordWheelQuery`)

- Repository source: `log2timeline/plaso/test_data/NTUSER-WIN7.DAT`
- Stored filename: `NTUSER_WORD_WHEEL_QUERY.dat`
- Stored size: 1,310,720 bytes
- Stored-file SHA-256:
  `672abb15ae62fa8c002c5ee0a730cf83cd5f40706d5ffdec8f1179cf47a0bd03`

Add `tests/data/hive/SOURCES.md` with immutable commit-pinned source URLs,
stored filenames, byte sizes, SHA-256 hashes, decompression information, and
links to complete locally redistributed upstream license texts. Tests must not
access the network.

## Test strategy

### RecentApps

Replace the existing zero-row real-hive assertion with an end-to-end test
against `NTUSER_RECENT_APPS.dat`. Assert one clean output record containing:

- GUID `da8dc440-0faa-417d-8af4-8f4b2eb50409`;
- `app_id` equal to `D:\setup64.exe`;
- `launch_count` equal to `1`;
- application last-access time
  `2017-07-12T07:34:32.178000+00:00`; and
- no recent-item fields.

Extend the focused item test so one item has arguments and one omits them.
Assert raw paths, separate arguments, application path propagation, one record
per item, and the absence of the string `"None"`.

### ACMru

Use an in-memory registry-key double containing category `5603` and values
supplied out of order. Assert:

- deterministic numeric output order;
- integer `order_index`;
- `category == "5603"` on every record;
- only index zero contains `key_modif_time`; and
- malformed and decorated value names are reported and skipped without losing
  valid values; and
- an unexpected failure in one category does not suppress a later category.

### Explorer Search History (`WordWheelQuery`)

Use `NTUSER_WORD_WHEEL_QUERY.dat` for a positive end-to-end test. Its
`MRUListEx` is `[1, 0, 0xffffffff]`, so assert two clean records in this order:

1. `rar.exe`, `order_index == 0`, `value_index == 1`, with
   `key_modif_time`;
2. `hyth`, `order_index == 1`, `value_index == 0`, without
   `key_modif_time`.

Add focused decoder tests for malformed `MRUListEx`, missing referenced values,
and invalid UTF-16LE data so error behavior is independent of the public hive.

### Verification

Run:

```bash
uv run python -m unittest \
  tests.hive.test_recent_app \
  tests.hive.test_acmru \
  tests.hive.test_explorer_search_history -v
```

Then run the repository's complete unit-test suite and any configured formatter,
lint, or type checks used by the project.

## Compatibility

- Existing `RegRecentApp` and `RegAcMru` command names and data types remain
  available.
- Existing RecentApps `path` consumers will now receive the actual path rather
  than a synthesized path-and-arguments string. This is an intentional
  correctness change; arguments remain available in their own field.
- Existing ACMru consumers will receive `order_index` as an integer rather than
  a string and will gain `category`.
- Older ACMru records will no longer carry an unsupported timestamp.
- Explorer Search History is additive and has its own command, configuration,
  and data type. `WordWheelQuery` remains visible as the underlying registry
  artifact name, not as the user-facing plugin name.
