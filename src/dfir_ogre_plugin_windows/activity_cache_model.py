import base64
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from dfir_ogre_plugin_windows.common import normalize_guid


ColumnKind = Literal["string", "guid", "int", "bool", "datetime"]
ActivityValue = str | int | bool | datetime | None


class ActivityCacheError(ValueError):
    """Base error for unsupported or unreadable Activity Cache data."""


class UnsupportedActivityCacheSchema(ActivityCacheError):
    """Raised when no supported Activity Cache source table is present."""


@dataclass(frozen=True)
class ColumnSpec:
    output_name: str
    kind: ColumnKind


@dataclass(frozen=True)
class ActivityCacheSchema:
    user_version: int
    table_columns: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedActivity:
    values: dict[str, ActivityValue]
    source_table: str
    source_row: int


@dataclass(frozen=True)
class TableReadResult:
    records: tuple[NormalizedActivity, ...]
    diagnostics: tuple[str, ...]


ACTIVITY_COLUMNS = {
    "Id": ColumnSpec("id", "guid"),
    "AppId": ColumnSpec("app_id", "string"),
    "PackageIdHash": ColumnSpec("package_id_hash", "string"),
    "AppActivityId": ColumnSpec("app_activity_id", "guid"),
    "ActivityType": ColumnSpec("activity_type", "int"),
    "ActivityStatus": ColumnSpec("activity_status", "int"),
    "ParentActivityId": ColumnSpec("parent_activity_id", "guid"),
    "Tag": ColumnSpec("tag", "string"),
    "Group": ColumnSpec("group", "string"),
    "MatchId": ColumnSpec("match_id", "guid"),
    "LastModifiedTime": ColumnSpec("last_modified_time", "datetime"),
    "ExpirationTime": ColumnSpec("expiration_time", "datetime"),
    "Payload": ColumnSpec("payload", "string"),
    "Priority": ColumnSpec("priority", "int"),
    "OriginatingDevice": ColumnSpec("originating_device", "string"),
    "IsLocalOnly": ColumnSpec("is_local_only", "bool"),
    "PlatformDeviceId": ColumnSpec("platform_device_id", "guid"),
    "DdsDeviceId": ColumnSpec("dds_device_id", "guid"),
    "CreatedInCloud": ColumnSpec("created_in_cloud", "datetime"),
    "StartTime": ColumnSpec("start_time", "datetime"),
    "EndTime": ColumnSpec("end_time", "datetime"),
    "LastModifiedOnClient": ColumnSpec(
        "last_modified_on_client",
        "datetime",
    ),
    "GroupAppActivityId": ColumnSpec("group_app_activity_id", "guid"),
    "ClipboardPayload": ColumnSpec("clipboard_payload", "string"),
    "EnterpriseId": ColumnSpec("enterprise_id", "guid"),
    "OriginalPayload": ColumnSpec("original_payload", "string"),
    "UserActionState": ColumnSpec("user_action_state", "int"),
    "IsRead": ColumnSpec("is_read", "bool"),
    "OriginalLastModifiedOnClient": ColumnSpec(
        "original_last_modified_on_client",
        "datetime",
    ),
    "GroupItems": ColumnSpec("group_items", "string"),
    "LocalExpirationTime": ColumnSpec("local_expiration_time", "datetime"),
    "ETag": ColumnSpec("e_tag", "int"),
}

ACTIVITY_OPERATION_COLUMNS = {
    "OperationOrder": ColumnSpec("operation_order", "int"),
    "Id": ColumnSpec("id", "guid"),
    "OperationType": ColumnSpec("operation_type", "int"),
    "AppId": ColumnSpec("app_id", "string"),
    "PackageIdHash": ColumnSpec("package_id_hash", "string"),
    "AppActivityId": ColumnSpec("app_activity_id", "guid"),
    "ActivityType": ColumnSpec("activity_type", "int"),
    "ParentActivityId": ColumnSpec("parent_activity_id", "guid"),
    "Tag": ColumnSpec("tag", "string"),
    "Group": ColumnSpec("group", "string"),
    "MatchId": ColumnSpec("match_id", "guid"),
    "LastModifiedTime": ColumnSpec("last_modified_time", "datetime"),
    "ExpirationTime": ColumnSpec("expiration_time", "datetime"),
    "Payload": ColumnSpec("payload", "string"),
    "Priority": ColumnSpec("priority", "int"),
    "OriginatingDevice": ColumnSpec("originating_device", "string"),
    "CreatedTime": ColumnSpec("created_time", "datetime"),
    "Attachments": ColumnSpec("attachments", "string"),
    "OperationExpirationTime": ColumnSpec(
        "operation_expiration_time",
        "datetime",
    ),
    "PlatformDeviceId": ColumnSpec("platform_device_id", "guid"),
    "DdsDeviceId": ColumnSpec("dds_device_id", "guid"),
    "CreatedInCloud": ColumnSpec("created_in_cloud", "datetime"),
    "StartTime": ColumnSpec("start_time", "datetime"),
    "EndTime": ColumnSpec("end_time", "datetime"),
    "LastModifiedOnClient": ColumnSpec(
        "last_modified_on_client",
        "datetime",
    ),
    "CorrelationVector": ColumnSpec("correlation_vector", "string"),
    "GroupAppActivityId": ColumnSpec("group_app_activity_id", "guid"),
    "ClipboardPayload": ColumnSpec("clipboard_payload", "string"),
    "EnterpriseId": ColumnSpec("enterprise_id", "guid"),
    "UserActionState": ColumnSpec("user_action_state", "int"),
    "IsRead": ColumnSpec("is_read", "bool"),
    "OriginalPayload": ColumnSpec("original_payload", "string"),
    "OriginalLastModifiedOnClient": ColumnSpec(
        "original_last_modified_on_client",
        "datetime",
    ),
    "UploadAllowedByPolicy": ColumnSpec(
        "upload_allowed_by_policy",
        "bool",
    ),
    "PatchFields": ColumnSpec("patch_fields", "string"),
    "GroupItems": ColumnSpec("group_items", "string"),
    "ThrottleReleaseTime": ColumnSpec("throttle_release_time", "datetime"),
    "ETag": ColumnSpec("e_tag", "int"),
    "PublishProcessStatus": ColumnSpec("publish_process_status", "int"),
}

KNOWN_COLUMNS = {
    "Activity": ACTIVITY_COLUMNS,
    "ActivityOperation": ACTIVITY_OPERATION_COLUMNS,
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _encode_binary(value: bytes | bytearray) -> str:
    return base64.urlsafe_b64encode(bytes(value)).decode("ascii").rstrip("=")


def _normalize_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"unsupported timestamp value {value!r}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_value(value: object, spec: ColumnSpec) -> ActivityValue:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        if spec.kind in ("string", "guid"):
            return _encode_binary(value)
        expected = {
            "int": "an integer",
            "bool": "0 or 1",
            "datetime": "a datetime",
        }[spec.kind]
        raise ValueError(
            f"{spec.output_name} expects {expected}, "
            f"found binary value"
        )
    if spec.kind == "datetime":
        return _normalize_datetime(value)
    if spec.kind == "bool":
        try:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            numeric = int(value)
        except (OverflowError, TypeError, ValueError) as exception:
            raise ValueError(
                f"{spec.output_name} expects 0 or 1, found {value!r}"
            ) from exception
        if numeric not in (0, 1):
            raise ValueError(
                f"{spec.output_name} expects 0 or 1, found {value!r}"
            )
        return bool(numeric)
    if spec.kind == "int":
        try:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            return int(value)
        except (OverflowError, TypeError, ValueError) as exception:
            raise ValueError(
                f"{spec.output_name} expects an integer, "
                f"found {value!r}"
            ) from exception
    if spec.kind == "guid":
        return normalize_guid(str(value))
    return str(value)


def inspect_activity_cache_schema(
    connection: sqlite3.Connection,
) -> ActivityCacheSchema:
    user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    present_tables = {
        str(row[0]).lower(): str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    table_columns: dict[str, tuple[str, ...]] = {}
    warnings: list[str] = []

    for canonical_table, known in KNOWN_COLUMNS.items():
        actual_table = present_tables.get(canonical_table.lower())
        if actual_table is None:
            continue
        pragma = f"PRAGMA table_info({_quote_identifier(actual_table)})"
        actual_columns = tuple(str(row[1]) for row in connection.execute(pragma))
        known_lower = {name.lower() for name in known}
        recognized = tuple(
            name for name in actual_columns if name.lower() in known_lower
        )
        for name in actual_columns:
            if name.lower() not in known_lower:
                warnings.append(
                    f"{canonical_table}: ignoring unknown column {name}"
                )
        if not recognized:
            warnings.append(
                f"{canonical_table}: no recognized columns; ignoring table"
            )
            continue
        table_columns[canonical_table] = actual_columns

    if not table_columns:
        raise UnsupportedActivityCacheSchema(
            "database contains neither Activity nor ActivityOperation "
            "with recognized columns"
        )

    return ActivityCacheSchema(
        user_version,
        table_columns,
        tuple(warnings),
    )


def read_normalized_table(
    connection: sqlite3.Connection,
    schema: ActivityCacheSchema,
    table_name: str,
) -> TableReadResult:
    if table_name not in schema.table_columns:
        return TableReadResult((), ())

    specs = KNOWN_COLUMNS[table_name]
    specs_lower = {name.lower(): (name, spec) for name, spec in specs.items()}
    selected = [
        (actual, specs_lower[actual.lower()][1])
        for actual in schema.table_columns[table_name]
        if actual.lower() in specs_lower
    ]
    sql = "SELECT " + ", ".join(
        _quote_identifier(name) for name, _ in selected
    ) + " FROM " + _quote_identifier(table_name)

    records: list[NormalizedActivity] = []
    diagnostics: list[str] = []
    for row_number, row in enumerate(connection.execute(sql)):
        raw = dict(row)
        raw_lower = {
            str(name).lower(): raw_value
            for name, raw_value in raw.items()
        }
        try:
            values = {
                spec.output_name: _normalize_value(raw[actual], spec)
                for actual, spec in selected
            }
            values["database_user_version"] = schema.user_version
            records.append(
                NormalizedActivity(values, table_name, row_number)
            )
        except (OverflowError, TypeError, ValueError) as exception:
            identity = (
                f"Id={raw_lower.get('id')!r}, "
                f"ETag={raw_lower.get('etag')!r}"
            )
            diagnostics.append(
                f"{table_name} row {row_number} ({identity}): {exception}"
            )

    return TableReadResult(tuple(records), tuple(diagnostics))


@dataclass(frozen=True)
class MergeResult:
    records: tuple[NormalizedActivity, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ActivityCacheParseResult:
    records: tuple[NormalizedActivity, ...]
    diagnostics: tuple[str, ...]
    warnings: tuple[str, ...]
    user_version: int


def _merge_key(record: NormalizedActivity) -> tuple[str, int] | None:
    identifier = record.values.get("id")
    e_tag = record.values.get("e_tag")
    if not isinstance(identifier, str) or not isinstance(e_tag, int):
        return None
    return identifier, e_tag


def _finalize_record(record: NormalizedActivity) -> NormalizedActivity:
    values = dict(record.values)
    if values.get("start_time") is not None:
        values["start_time_source"] = "start_time"
    elif values.get("last_modified_time") is not None:
        values["start_time"] = values["last_modified_time"]
        values["start_time_source"] = "last_modified_time"
    else:
        values["start_time"] = None
        values["start_time_source"] = "unavailable"
    source_labels = {
        "Activity": "activity",
        "ActivityOperation": "activity_operation",
        "activity+activity_operation": "activity+activity_operation",
    }
    values["record_source"] = source_labels[record.source_table]
    return NormalizedActivity(values, record.source_table, record.source_row)


def _activity_value_sort_key(value: ActivityValue) -> tuple[str, str]:
    if isinstance(value, datetime):
        return "datetime", value.isoformat(timespec="microseconds")
    if value is None:
        return "none", ""
    if isinstance(value, bool):
        return "bool", "1" if value else "0"
    if isinstance(value, int):
        return "int", str(value)
    return "string", value


def _record_sort_key(
    record: NormalizedActivity,
) -> tuple[
    datetime,
    int,
    int,
    str,
    int,
    str,
    tuple[tuple[str, str, str], ...],
]:
    start_time = record.values.get("start_time")
    if not isinstance(start_time, datetime):
        start_time = datetime.max.replace(tzinfo=timezone.utc)
    operation_order = record.values.get("operation_order")
    operation_rank = 0 if record.source_table == "Activity" else 1
    if not isinstance(operation_order, int):
        operation_order = 0
    identifier = record.values.get("id")
    if not isinstance(identifier, str):
        identifier = ""
    e_tag = record.values.get("e_tag")
    if not isinstance(e_tag, int):
        e_tag = -1
    stable_values = tuple(
        (name, *_activity_value_sort_key(value))
        for name, value in sorted(record.values.items())
    )
    return (
        start_time,
        operation_rank,
        operation_order,
        identifier,
        e_tag,
        record.source_table,
        stable_values,
    )


def merge_activity_cache_records(
    activity_rows: tuple[NormalizedActivity, ...],
    operation_rows: tuple[NormalizedActivity, ...],
) -> MergeResult:
    activity_by_key: dict[
        tuple[str, int],
        list[NormalizedActivity],
    ] = {}
    for activity in activity_rows:
        key = _merge_key(activity)
        if key is not None:
            activity_by_key.setdefault(key, []).append(activity)

    merged_activity_rows: set[int] = set()
    output: list[NormalizedActivity] = []
    diagnostics: list[str] = []

    for operation in operation_rows:
        key = _merge_key(operation)
        candidates = activity_by_key.get(key, []) if key is not None else []
        if len(candidates) == 1:
            activity = candidates[0]
            values = dict(activity.values)
            values.update(
                name_value
                for name_value in operation.values.items()
                if name_value[1] is not None
            )
            output.append(
                NormalizedActivity(
                    values,
                    "activity+activity_operation",
                    operation.source_row,
                )
            )
            merged_activity_rows.add(activity.source_row)
        elif len(candidates) > 1:
            diagnostics.append(
                f"ambiguous Activity key {key!r}: "
                f"{len(candidates)} rows; preserving all rows"
            )
            output.append(operation)
        else:
            output.append(operation)

    output.extend(
        activity
        for activity in activity_rows
        if activity.source_row not in merged_activity_rows
    )
    finalized = tuple(
        sorted(
            (_finalize_record(record) for record in output),
            key=_record_sort_key,
        )
    )
    return MergeResult(finalized, tuple(diagnostics))


def parse_activity_cache(
    connection: sqlite3.Connection,
) -> ActivityCacheParseResult:
    schema = inspect_activity_cache_schema(connection)
    activity = read_normalized_table(connection, schema, "Activity")
    operations = read_normalized_table(
        connection,
        schema,
        "ActivityOperation",
    )
    merged = merge_activity_cache_records(
        activity.records,
        operations.records,
    )
    diagnostics = (
        activity.diagnostics
        + operations.diagnostics
        + merged.diagnostics
    )
    return ActivityCacheParseResult(
        merged.records,
        diagnostics,
        schema.warnings,
        schema.user_version,
    )
