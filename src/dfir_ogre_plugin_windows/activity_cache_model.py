import base64
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from dfir_ogre_plugin_windows.common import normalize_guid


ColumnKind = Literal["string", "int", "bool", "datetime"]
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
    "Id": ColumnSpec("id", "string"),
    "AppId": ColumnSpec("app_id", "string"),
    "PackageIdHash": ColumnSpec("package_id_hash", "string"),
    "AppActivityId": ColumnSpec("app_activity_id", "string"),
    "ActivityType": ColumnSpec("activity_type", "int"),
    "ActivityStatus": ColumnSpec("activity_status", "int"),
    "ParentActivityId": ColumnSpec("parent_activity_id", "string"),
    "Tag": ColumnSpec("tag", "string"),
    "Group": ColumnSpec("group", "string"),
    "MatchId": ColumnSpec("match_id", "string"),
    "LastModifiedTime": ColumnSpec("last_modified_time", "datetime"),
    "ExpirationTime": ColumnSpec("expiration_time", "datetime"),
    "Payload": ColumnSpec("payload", "string"),
    "Priority": ColumnSpec("priority", "int"),
    "OriginatingDevice": ColumnSpec("originating_device", "string"),
    "IsLocalOnly": ColumnSpec("is_local_only", "bool"),
    "PlatformDeviceId": ColumnSpec("platform_device_id", "string"),
    "DdsDeviceId": ColumnSpec("dds_device_id", "string"),
    "CreatedInCloud": ColumnSpec("created_in_cloud", "datetime"),
    "StartTime": ColumnSpec("start_time", "datetime"),
    "EndTime": ColumnSpec("end_time", "datetime"),
    "LastModifiedOnClient": ColumnSpec(
        "last_modified_on_client",
        "datetime",
    ),
    "GroupAppActivityId": ColumnSpec("group_app_activity_id", "string"),
    "ClipboardPayload": ColumnSpec("clipboard_payload", "string"),
    "EnterpriseId": ColumnSpec("enterprise_id", "string"),
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
    "Id": ColumnSpec("id", "string"),
    "OperationType": ColumnSpec("operation_type", "int"),
    "AppId": ColumnSpec("app_id", "string"),
    "PackageIdHash": ColumnSpec("package_id_hash", "string"),
    "AppActivityId": ColumnSpec("app_activity_id", "string"),
    "ActivityType": ColumnSpec("activity_type", "int"),
    "ParentActivityId": ColumnSpec("parent_activity_id", "string"),
    "Tag": ColumnSpec("tag", "string"),
    "Group": ColumnSpec("group", "string"),
    "MatchId": ColumnSpec("match_id", "string"),
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
    "PlatformDeviceId": ColumnSpec("platform_device_id", "string"),
    "DdsDeviceId": ColumnSpec("dds_device_id", "string"),
    "CreatedInCloud": ColumnSpec("created_in_cloud", "datetime"),
    "StartTime": ColumnSpec("start_time", "datetime"),
    "EndTime": ColumnSpec("end_time", "datetime"),
    "LastModifiedOnClient": ColumnSpec(
        "last_modified_on_client",
        "datetime",
    ),
    "CorrelationVector": ColumnSpec("correlation_vector", "string"),
    "GroupAppActivityId": ColumnSpec("group_app_activity_id", "string"),
    "ClipboardPayload": ColumnSpec("clipboard_payload", "string"),
    "EnterpriseId": ColumnSpec("enterprise_id", "string"),
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
        return _encode_binary(value)
    if spec.kind == "datetime":
        return _normalize_datetime(value)
    if spec.kind == "bool":
        numeric = int(value)
        if numeric not in (0, 1):
            raise ValueError(
                f"{spec.output_name} expects 0 or 1, found {value!r}"
            )
        return bool(numeric)
    if spec.kind == "int":
        return int(value)
    return normalize_guid(str(value))


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
        if not recognized:
            raise UnsupportedActivityCacheSchema(
                f"{canonical_table} has no recognized columns"
            )
        for name in actual_columns:
            if name.lower() not in known_lower:
                warnings.append(
                    f"{canonical_table}: ignoring unknown column {name}"
                )
        table_columns[canonical_table] = actual_columns

    if not table_columns:
        raise UnsupportedActivityCacheSchema(
            "database contains neither Activity nor ActivityOperation"
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
                f"Id={raw.get('Id')!r}, ETag={raw.get('ETag')!r}"
            )
            diagnostics.append(
                f"{table_name} row {row_number} ({identity}): {exception}"
            )

    return TableReadResult(tuple(records), tuple(diagnostics))
