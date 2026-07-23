import sqlite3
from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_plugin_windows.activity_cache_model import (
    ActivityValue,
    NormalizedActivity,
    UnsupportedActivityCacheSchema,
    inspect_activity_cache_schema,
    merge_activity_cache_records,
    parse_activity_cache,
    read_normalized_table,
)


LEGACY_ACTIVITY_SCHEMA = """
CREATE TABLE Activity(
    Id GUID PRIMARY KEY NOT NULL,
    AppId TEXT NOT NULL,
    ActivityType INT NOT NULL,
    ParentActivityId GUID,
    Tag TEXT,
    "Group" TEXT,
    MatchId TEXT,
    LastModifiedTime DATETIME NOT NULL,
    ExpirationTime DATETIME,
    Payload BLOB,
    Priority INT,
    OriginatingDevice TEXT,
    IsLocalOnly INT,
    PlatformDeviceId TEXT,
    ETag INT NOT NULL
)
"""

LEGACY_OPERATION_SCHEMA = """
CREATE TABLE ActivityOperation(
    OperationOrder INTEGER PRIMARY KEY NOT NULL,
    Id GUID NOT NULL,
    OperationType INT NOT NULL,
    AppId TEXT NOT NULL,
    ActivityType INT NOT NULL,
    LastModifiedTime DATETIME NOT NULL,
    OriginatingDevice TEXT,
    CreatedTime DATETIME,
    Attachments TEXT,
    ETag INT NOT NULL
)
"""


def normalized(
    source: str,
    row: int,
    **values: ActivityValue,
) -> NormalizedActivity:
    return NormalizedActivity(dict(values), source, row)


class ActivityCacheModelTest(TestCase):
    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        return connection

    def test_schema_detection_uses_capabilities_and_reports_unknown_columns(self):
        connection = self.connection()
        connection.execute(LEGACY_ACTIVITY_SCHEMA)
        connection.execute("ALTER TABLE Activity ADD COLUMN FutureColumn TEXT")
        connection.execute("PRAGMA user_version=4")

        schema = inspect_activity_cache_schema(connection)

        self.assertEqual(schema.user_version, 4)
        self.assertEqual(set(schema.table_columns), {"Activity"})
        self.assertIn("LastModifiedTime", schema.table_columns["Activity"])
        self.assertEqual(
            schema.warnings,
            ("Activity: ignoring unknown column FutureColumn",),
        )

    def test_schema_without_supported_source_table_is_rejected(self):
        connection = self.connection()
        connection.execute("CREATE TABLE Metadata(Key TEXT, Value TEXT)")

        with self.assertRaisesRegex(
            UnsupportedActivityCacheSchema,
            "neither Activity nor ActivityOperation",
        ):
            inspect_activity_cache_schema(connection)

    def test_legacy_activity_row_is_typed_and_binary_safe(self):
        connection = self.connection()
        connection.execute(LEGACY_ACTIVITY_SCHEMA)
        connection.execute("PRAGMA user_version=4")
        connection.execute(
            """
            INSERT INTO Activity(
                Id, AppId, ActivityType, LastModifiedTime, Payload,
                Priority, OriginatingDevice, IsLocalOnly, ETag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bytes(range(16)),
                "legacy.test.app",
                1,
                1470000000,
                b"\xfb\xef",
                3,
                "legacy-device",
                1,
                7,
            ),
        )
        schema = inspect_activity_cache_schema(connection)

        result = read_normalized_table(
            connection,
            schema,
            "Activity",
        )

        self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(result.records), 1)
        values = result.records[0].values
        self.assertEqual(values["id"], "AAECAwQFBgcICQoLDA0ODw")
        self.assertEqual(values["payload"], "--8")
        self.assertEqual(values["activity_type"], 1)
        self.assertIs(type(values["activity_type"]), int)
        self.assertEqual(values["priority"], 3)
        self.assertEqual(values["e_tag"], 7)
        self.assertIs(values["is_local_only"], True)
        self.assertEqual(values["originating_device"], "legacy-device")
        self.assertEqual(
            values["last_modified_time"],
            datetime(2016, 7, 31, 21, 20, tzinfo=timezone.utc),
        )
        self.assertNotIn("start_time", values)
        self.assertEqual(values["database_user_version"], 4)

    def test_legacy_operation_columns_are_normalized(self):
        connection = self.connection()
        connection.execute(LEGACY_OPERATION_SCHEMA)
        connection.execute("PRAGMA user_version=4")
        connection.execute(
            """
            INSERT INTO ActivityOperation(
                OperationOrder, Id, OperationType, AppId, ActivityType,
                LastModifiedTime, OriginatingDevice, CreatedTime,
                Attachments, ETag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                12,
                "legacy-operation",
                2,
                "legacy-app",
                1,
                1470000000,
                "legacy-device",
                1470000001,
                "legacy-attachment",
                8,
            ),
        )
        schema = inspect_activity_cache_schema(connection)

        result = read_normalized_table(
            connection,
            schema,
            "ActivityOperation",
        )

        self.assertEqual(result.diagnostics, ())
        values = result.records[0].values
        self.assertEqual(values["operation_order"], 12)
        self.assertEqual(values["operation_type"], 2)
        self.assertEqual(values["originating_device"], "legacy-device")
        self.assertEqual(values["attachments"], "legacy-attachment")
        self.assertEqual(
            values["created_time"],
            datetime(2016, 7, 31, 21, 20, 1, tzinfo=timezone.utc),
        )

    def test_modern_optional_operation_columns_are_typed(self):
        connection = self.connection()
        connection.execute(
            """
            CREATE TABLE ActivityOperation(
                OperationOrder INTEGER PRIMARY KEY NOT NULL,
                Id GUID NOT NULL,
                OperationType INT NOT NULL,
                AppId TEXT NOT NULL,
                ActivityType INT NOT NULL,
                LastModifiedTime DATETIME NOT NULL,
                StartTime DATETIME,
                UploadAllowedByPolicy INT,
                PatchFields BLOB,
                PublishProcessStatus INT,
                ETag INT NOT NULL
            )
            """
        )
        connection.execute("PRAGMA user_version=30")
        connection.execute(
            """
            INSERT INTO ActivityOperation(
                OperationOrder, Id, OperationType, AppId, ActivityType,
                LastModifiedTime, StartTime, UploadAllowedByPolicy,
                PatchFields, PublishProcessStatus, ETag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                20,
                "modern-operation",
                1,
                "modern-app",
                5,
                1700000000,
                1700000001,
                0,
                b"\xfb\xef",
                3,
                9,
            ),
        )
        schema = inspect_activity_cache_schema(connection)

        result = read_normalized_table(
            connection,
            schema,
            "ActivityOperation",
        )

        values = result.records[0].values
        self.assertIs(values["upload_allowed_by_policy"], False)
        self.assertEqual(values["patch_fields"], "--8")
        self.assertEqual(values["publish_process_status"], 3)
        self.assertIsInstance(values["start_time"], datetime)

    def test_matching_versions_merge_without_collapsing_operations(self):
        activity = normalized(
            "Activity",
            0,
            id="activity-1",
            e_tag=9,
            app_id="persisted-app",
            activity_status=1,
            last_modified_time=datetime(
                2024,
                1,
                1,
                tzinfo=timezone.utc,
            ),
            start_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            database_user_version=30,
        )
        operations = (
            normalized(
                "ActivityOperation",
                0,
                id="activity-1",
                e_tag=9,
                app_id="queued-app",
                operation_order=10,
                operation_type=2,
                last_modified_time=datetime(
                    2024,
                    1,
                    3,
                    tzinfo=timezone.utc,
                ),
                database_user_version=30,
            ),
            normalized(
                "ActivityOperation",
                1,
                id="activity-1",
                e_tag=9,
                operation_order=11,
                operation_type=3,
                database_user_version=30,
            ),
        )

        result = merge_activity_cache_records((activity,), operations)

        self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(result.records), 2)
        first, second = result.records
        self.assertEqual(
            first.values["record_source"],
            "activity+activity_operation",
        )
        self.assertEqual(first.values["app_id"], "queued-app")
        self.assertEqual(first.values["activity_status"], 1)
        self.assertEqual(first.values["operation_type"], 2)
        self.assertEqual(first.values["operation_order"], 10)
        self.assertEqual(second.values["operation_order"], 11)
        self.assertEqual(
            [record.values["start_time_source"] for record in result.records],
            ["start_time", "start_time"],
        )

    def test_different_etags_and_missing_keys_remain_independent(self):
        rows = (
            normalized(
                "Activity",
                0,
                id="same-id",
                e_tag=1,
                last_modified_time=datetime(
                    2024,
                    2,
                    1,
                    tzinfo=timezone.utc,
                ),
                database_user_version=30,
            ),
            normalized(
                "Activity",
                1,
                id=None,
                e_tag=2,
                last_modified_time=datetime(
                    2024,
                    2,
                    2,
                    tzinfo=timezone.utc,
                ),
                database_user_version=30,
            ),
        )
        operations = (
            normalized(
                "ActivityOperation",
                0,
                id="same-id",
                e_tag=2,
                operation_order=8,
                last_modified_time=datetime(
                    2024,
                    2,
                    3,
                    tzinfo=timezone.utc,
                ),
                database_user_version=30,
            ),
        )

        result = merge_activity_cache_records(rows, operations)

        self.assertEqual(len(result.records), 3)
        self.assertEqual(
            {record.values["record_source"] for record in result.records},
            {"activity", "activity_operation"},
        )
        self.assertTrue(
            all(
                record.values["start_time_source"] == "last_modified_time"
                for record in result.records
            )
        )

    def test_ambiguous_activity_key_preserves_every_row(self):
        activities = (
            normalized(
                "Activity",
                0,
                id="duplicate",
                e_tag=1,
                database_user_version=30,
            ),
            normalized(
                "Activity",
                1,
                id="duplicate",
                e_tag=1,
                database_user_version=30,
            ),
        )
        operation = normalized(
            "ActivityOperation",
            0,
            id="duplicate",
            e_tag=1,
            operation_order=1,
            database_user_version=30,
        )

        result = merge_activity_cache_records(activities, (operation,))

        self.assertEqual(len(result.records), 3)
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("ambiguous Activity key", result.diagnostics[0])
        self.assertTrue(
            all(
                record.values["start_time"] is None
                and record.values["start_time_source"] == "unavailable"
                for record in result.records
            )
        )

    def test_parse_skips_bad_row_and_sorts_deterministically(self):
        connection = self.connection()
        connection.execute(LEGACY_ACTIVITY_SCHEMA)
        connection.execute("PRAGMA user_version=4")
        connection.executemany(
            """
            INSERT INTO Activity(
                Id, AppId, ActivityType, LastModifiedTime,
                IsLocalOnly, ETag
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ("later", "app", 1, 200, 0, 2),
                ("bad", "app", 1, 150, 2, 3),
                ("earlier", "app", 1, 100, 1, 1),
            ),
        )

        result = parse_activity_cache(connection)

        self.assertEqual(len(result.records), 2)
        self.assertEqual(
            [record.values["id"] for record in result.records],
            ["earlier", "later"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("expects 0 or 1", result.diagnostics[0])
        self.assertEqual(
            [record.values["start_time_source"] for record in result.records],
            ["last_modified_time", "last_modified_time"],
        )
