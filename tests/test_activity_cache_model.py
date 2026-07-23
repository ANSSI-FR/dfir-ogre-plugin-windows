import sqlite3
from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_plugin_windows.activity_cache_model import (
    UnsupportedActivityCacheSchema,
    inspect_activity_cache_schema,
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
