# Dedicated Windows Activity Cache Plugin Design

Date: 2026-07-23

## Context

`configuration/activity_cache.xml` currently delegates extraction to the generic
`SQLite` plugin with this query:

```sql
SELECT * FROM Activity ORDER BY StartTime
```

That query works for the supplied schema-version-30 `ActivitiesCache.db`, but it
fails against the schema-version-4 `activities_cache.2016.db` because the older
`Activity` table has no `StartTime` column. The two schemas differ more broadly:
the legacy table has 15 columns and uses `LastModifiedTime` as its useful event
timestamp, while the newer table has 31 columns including `AppActivityId`,
`StartTime`, `EndTime`, and several cloud and grouping fields.

The generic SQLite plugin cannot inspect the schema before compiling its query,
combine `Activity` with `ActivityOperation`, or preserve provenance while
deduplicating logical versions. Activity Cache therefore needs a dedicated
Python plugin.

## Goals

- Parse Activity Cache databases by detected table capabilities rather than by
  a hard-coded Windows or `user_version` label.
- Support both `Activity` and `ActivityOperation`, including legacy and modern
  layouts and intermediate layouts containing a subset of known columns.
- Keep `data_type="activity_cache"` and preserve established output field names.
- Normalize numeric values to JSON integers and binary flags to JSON booleans.
- Preserve distinct operation history while merging duplicate logical versions
  shared by the two source tables.
- Preserve the original evidence files, including avoiding new WAL/SHM files
  beside them.
- Continue using the XML configuration for output selection, descriptions,
  timeline construction, and serialization.
- Produce deterministic output and useful diagnostics.

## Non-goals

- Deleted-record, freelist, or unallocated-space carving.
- Decoding application-specific payload contents.
- Treating `LastModifiedTime` as semantically identical to a native
  `StartTime` without recording the fallback.
- Identifying a precise Windows release solely from SQLite `user_version`.
- Providing a consistent live-acquisition snapshot while Windows is actively
  modifying the source files. The plugin consumes already-collected artifacts.
- Reading the `SmartLookup` view. Its definition varies with the schema, and
  reading its base tables provides clearer provenance.

## Selected approach

Implement a dedicated `ActivityCache` `OgrePlugin`. It will use Python's
standard `sqlite3` module to inspect and read a private snapshot, normalize rows
into a stable internal model, merge cross-table duplicates, and write
`dfir_ogre_common.Record` instances through `Output`.

This follows the repository's multi-version `RegAppCompatCache` pattern:
format/schema interpretation remains in focused Python code, while
`PluginConfiguration` and `Output` retain responsibility for the external
record contract.

### Alternatives considered

1. **Generate schema-specific SQL and continue using `parse_sqlite`.**
   This minimizes new code, but the generic parser writes rows immediately and
   therefore cannot merge records from two tables or attach reliable combined
   provenance.
2. **Create separate legacy and modern plugins/configurations.**
   Each branch would be simpler, but callers would need to choose one and every
   intermediate schema would create another selection and maintenance problem.
3. **Use `SmartLookup` as the sole source.**
   This performs some deduplication inside SQLite, but loses explicit base-table
   provenance and inherits version-specific view semantics.

## Components

### `src/dfir_ogre_plugin_windows/activity_cache.py`

The `ActivityCache` plugin will:

- expose the `ActivityCache` command through `PluginDescription`;
- load `configuration/activity_cache.xml`;
- create and clean up the private SQLite snapshot;
- open the snapshot and request schema inspection and normalized records;
- convert normalized records to `Record`/`Value` objects;
- isolate row-level failures and add contextual diagnostics to `RunReport`;
- write records through `Output`; and
- attach the resulting `OutputReport`.

This module owns orchestration and framework integration, not schema-specific
field selection or merge rules.

### `src/dfir_ogre_plugin_windows/activity_cache_model.py`

This module will contain framework-independent logic:

- immutable schema and normalized-record dataclasses;
- SQLite identifier quoting and table discovery;
- column-capability inspection through `PRAGMA table_info`;
- dynamic selection of known columns that actually exist;
- field-name, value-type, binary-value, and timestamp normalization;
- legacy `start_time` fallback;
- cross-table merge and provenance rules; and
- deterministic record ordering.

The model functions will accept a `sqlite3.Connection` and return plain Python
objects. This keeps the compatibility logic unit-testable without invoking the
output framework.

### `configuration/activity_cache.xml`

The existing configuration will:

- change `parser="SQLite"` to `parser="ActivityCache"`;
- remove the `<query>` element;
- retain `data_type="activity_cache"` and existing output names;
- declare all supported normalized fields explicitly;
- use correct `Int`, `Bool`, `DateTime`, and `String` parsers;
- add provenance, operation, and legacy fields; and
- keep `start_time` as the primary timeline timestamp.

The default parser will be `Ignore`, preventing a newly observed database
column from silently entering the public schema with an arbitrary type.

### Registration

`src/dfir_ogre_plugin_windows/__init__.py` will import and export
`ActivityCache`. Configuration registration tests will then resolve
`parser="ActivityCache"` automatically through `OgrePlugin.__subclasses__()`.

## Evidence-preserving SQLite access

The plugin must not open the supplied evidence path with a writable SQLite
connection because doing so can create or modify `-wal` and `-shm` sidecars.

For each run it will:

1. Create a private temporary directory.
2. Copy the main database to that directory without changing its basename.
3. If a matching `<database>-wal` exists, copy it beside the temporary main
   database.
4. Do not copy the source `-shm`; SQLite may safely rebuild the transient index
   for the private copy.
5. Open only the private copy and set `PRAGMA query_only=ON`.
6. Run `PRAGMA quick_check`; stop with a fatal diagnostic unless its single
   result is `ok`.
7. Close the connection before the temporary directory is removed.

The source main database and source sidecars are never opened by SQLite.
Copying is appropriate for collected, quiescent forensic artifacts. A caller
requiring a consistent live snapshot remains responsible for acquisition.

## Schema discovery

The parser will read `PRAGMA user_version` for provenance only. Selection logic
will instead inspect:

- whether `Activity` exists;
- whether `ActivityOperation` exists; and
- the exact column-name set returned by `PRAGMA table_info` for each table.

At least one source table is required. A database containing only one of them is
valid and will be parsed. If neither exists, the run returns a clear unsupported
schema error.

Queries will explicitly select the intersection of:

- columns known to the plugin for that table; and
- columns present in the inspected schema.

All table and column identifiers will be quoted by a dedicated helper; no
artifact value is interpolated into SQL. Unknown additional columns produce a
logger warning but do not make an otherwise supported database fail.

## Normalized output contract

The plugin retains `data_type="activity_cache"` and the established snake-case
field names. The change intentionally corrects serialized types:

- counts, statuses, activity types, ETags, priorities, operation orders, and
  other numeric values are JSON integers;
- `IsLocalOnly`, `IsRead`, `UploadAllowedByPolicy`, and equivalent binary flags
  are JSON booleans;
- known timestamp columns are timezone-aware UTC datetimes;
- textual columns remain strings; and
- SQL `NULL` remains a null/absent value according to the selected output
  configuration.

Existing identifiers and payloads must not silently change identity:

- textual identifiers remain unchanged except for the existing complete-GUID
  lowercase normalization;
- binary identifier values retain the current URL-safe base64 representation
  without padding rather than being reinterpreted with uncertain GUID byte
  order; and
- other binary values retain the current encoded representation unless a field
  has a separately documented decoder.

The configuration will retain the existing fields observed in modern output,
including:

- `id`, `app_id`, `package_id_hash`, `app_activity_id`;
- `activity_type`, `activity_status`, `parent_activity_id`;
- `tag`, `group`, `match_id`, `group_app_activity_id`, `group_items`;
- `last_modified_time`, `expiration_time`, `created_in_cloud`, `start_time`,
  `end_time`, `last_modified_on_client`, `original_last_modified_on_client`,
  and `local_expiration_time`;
- `payload`, `original_payload`, `clipboard_payload`, `priority`,
  `is_local_only`, `platform_device_id`, `dds_device_id`;
- `user_action_state`, `is_read`, `enterprise_id`; and
- `e_tag`.

It will add known fields needed by either source table or legacy layouts,
including:

- `record_source`;
- `database_user_version`;
- `start_time_source`;
- `operation_order`, `operation_type`, `created_time`,
  `operation_expiration_time`, `correlation_vector`,
  `upload_allowed_by_policy`, `patch_fields`, `throttle_release_time`, and
  `publish_process_status`;
- `originating_device` and `attachments`; and
- other currently known Activity/ActivityOperation columns that are not already
  represented.

The explicit field union therefore covers every column in the inspected
schema-version-4 and schema-version-30 `Activity` and `ActivityOperation`
tables. Nullable fields remain part of the declared contract even when they do
not appear in an `include_empty=False` sample.

## Legacy timestamp fallback

For each normalized row:

1. If native `StartTime` is non-null, emit it as `start_time` and set
   `start_time_source="start_time"`.
2. Otherwise, if `LastModifiedTime` is non-null, emit that value as
   `start_time` and set
   `start_time_source="last_modified_time"`.
3. If both are null, omit/null `start_time` and set
   `start_time_source="unavailable"`.

The original `last_modified_time` field remains present. The fallback therefore
supports one common timeline while making the timestamp's provenance explicit.
No fallback is invented for absent `AppActivityId`.

## Cross-table merge rules

Deduplication occurs only between `Activity` and `ActivityOperation`. Records
within `ActivityOperation` are not collapsed because separate operation orders
are forensic history.

### Merge identity

- A row is mergeable only when both `Id` and `ETag` are non-null.
- The cross-table key is `(Id, ETag)` using normalized, stable identifier
  values.
- Rows missing either key component are emitted independently.

### Merge algorithm

1. Index Activity rows by `(Id, ETag)`.
2. For every ActivityOperation row:
   - if exactly one Activity row has the same key, create a merged row;
   - if no Activity row matches, emit the operation independently; and
   - if the Activity key is ambiguous, warn and emit all affected rows without
     destructive merging.
3. Suppress the standalone Activity row once at least one operation has been
   merged with it.
4. If multiple operation rows share the same key, emit one merged record for
   each operation order, combining each with the same Activity row.
5. Emit all unmatched Activity rows.

### Field precedence and provenance

- A non-null ActivityOperation value wins for a field present in both sources
  because it represents the queued operation state.
- Activity values fill null or unavailable shared fields and supply
  Activity-only fields.
- An Activity-only row uses `record_source="activity"`.
- An operation-only row uses `record_source="activity_operation"`.
- A merged row uses
  `record_source="activity+activity_operation"`.
- `activity_status` remains sourced from Activity; `operation_type` remains
  sourced from ActivityOperation. The plugin does not conflate the two.

## Ordering

Records will be sorted after normalization and merging by:

1. `start_time`, with unavailable timestamps last;
2. `operation_order`, with non-operation records before operations at the same
   timestamp;
3. normalized `id`;
4. numeric `e_tag`; and
5. `record_source` as a final stable tie-breaker.

This produces deterministic output without depending on SQLite's unspecified
row order.

## Diagnostics and failure behavior

Fatal run errors include:

- failure to copy or open the database snapshot;
- SQLite integrity/query failures that prevent reliable table reading;
- a malformed or incompatible WAL;
- absence of both supported source tables; and
- failure to load the plugin configuration or initialize output.

Fatal errors are added to `RunReport`, the connection/output resources are
closed, and no misleading partial-success claim is made.

Row-level normalization failures include the table name and the best available
row identity in `RunReport`. The affected row is skipped and parsing continues.
Rows with missing optional values are not failures.

Unknown extra columns are logged as forward-compatibility warnings without
setting `RunReport.last_error`, because all recognized evidence can still be
parsed. Ambiguous merge keys are reported and the involved rows are preserved
independently.

## Testing strategy

Tests will be split between pure model tests and plugin integration tests.

### Model tests

Synthetic temporary SQLite databases will cover:

- populated schema-version-4 Activity rows;
- populated schema-version-4 ActivityOperation rows;
- modern Activity and ActivityOperation layouts;
- intermediate layouts with optional columns absent;
- native and fallback `start_time` values and their source markers;
- integer and boolean normalization;
- binary identifier and payload representation compatibility;
- matching `(Id, ETag)` rows;
- unmatched rows from both tables;
- one ID with different ETags;
- multiple operation orders sharing a merge key;
- operation precedence and Activity field completion;
- missing merge-key components;
- ambiguous merge keys;
- deterministic ordering; and
- isolated malformed row values.

### Integration and regression tests

Plugin-level tests will cover:

- the supplied empty `activities_cache.2016.db`, expecting no parser error and
  zero output records; this file will be tracked at its existing fixture path;
- the existing modern `activities_cache.db`, expecting the established field
  names and 23 Activity-derived records;
- the intentional numeric/boolean JSON type changes;
- configuration loading and parser registration;
- timeline output using native and fallback `start_time`;
- a transaction visible only through a matching WAL;
- unsupported and corrupt databases;
- per-row diagnostic continuation;
- source database and sidecar hashes remaining unchanged; and
- no new sidecars appearing beside the evidence.

The existing browser-history tests remain under the generic SQLite plugin. The
Activity Cache test moves to the dedicated plugin's test module so that generic
SQLite behavior and artifact-specific behavior stay separate.

## Success criteria

- Both supplied Activity Cache databases complete without a schema-related SQL
  error.
- The supplied schema-version-4 database produces zero records because its
  source tables are empty, not because parsing failed.
- A populated synthetic schema-version-4 database produces typed records with
  explicit `LastModifiedTime` fallback provenance.
- The modern fixture continues to expose its established field names and 23
  Activity records, with the approved integer/boolean type normalization.
- Matching `(Id, ETag)` cross-table versions merge without dropping distinct
  operations or unmatched rows.
- Matching WAL data is included from the private snapshot.
- Input evidence and sidecars are byte-for-byte unchanged and no new source
  sidecars are created.
- Plugin registration, configuration validation, focused tests, and the full
  relevant test suite pass.
