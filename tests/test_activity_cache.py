import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import ActivityCache
from dfir_ogre_plugin_windows.activity_cache_model import (
    ACTIVITY_COLUMNS,
    ACTIVITY_OPERATION_COLUMNS,
)

from . import CONF_FOLDER, DATA_FOLDER


MINIMAL_ACTIVITY_SCHEMA = """
CREATE TABLE Activity(
    Id GUID PRIMARY KEY NOT NULL,
    AppId TEXT NOT NULL,
    ActivityType INT NOT NULL,
    LastModifiedTime DATETIME NOT NULL,
    IsLocalOnly INT,
    ETag INT NOT NULL
)
"""

MINIMAL_OPERATION_SCHEMA = """
CREATE TABLE ActivityOperation(
    OperationOrder INTEGER PRIMARY KEY NOT NULL,
    Id GUID NOT NULL,
    OperationType INT NOT NULL,
    AppId TEXT NOT NULL,
    ActivityType INT NOT NULL,
    LastModifiedTime DATETIME NOT NULL,
    UploadAllowedByPolicy INT,
    ETag INT NOT NULL
)
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_wal_artifact(root: Path) -> Path:
    original = root / "original.db"
    writer = sqlite3.connect(original)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(MINIMAL_ACTIVITY_SCHEMA)
        writer.execute(
            """
            INSERT INTO Activity(
                Id, AppId, ActivityType, LastModifiedTime,
                IsLocalOnly, ETag
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wal-artifact", "wal-app", 1, 200, 0, 6),
        )
        writer.commit()
        database = root / "ActivitiesCache.db"
        shutil.copy2(original, database)
        shutil.copy2(
            Path(f"{original}-wal"),
            Path(f"{database}-wal"),
        )
    finally:
        writer.close()
    return database


class ActivityCacheTest(TestCase):
    def parse(
        self,
        database: Path,
        output_directory: Path,
        base_name: str = "activity_cache_test",
        with_timeline: bool = False,
    ):
        output = OutputConfiguration(
            base_name,
            str(output_directory),
            with_timeline=with_timeline,
            include_empty=False,
        )
        run_config = RunConfiguration([output], True)
        return ActivityCache().parse(
            str(database),
            os.path.join(CONF_FOLDER, "activity_cache.xml"),
            run_config,
            Metadata("test"),
        )

    def read_output(
        self,
        output_directory: Path,
        base_name: str = "activity_cache_test",
    ) -> list[dict[str, object]]:
        path = output_directory / f"{base_name}.activity_cache.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]

    def report_line_count(self, report) -> int:
        return sum(
            file_report.num_lines
            for output_report in report.output_reports
            for file_report in output_report.file_reports
        )

    def test_plugin_uses_fallback_timestamp_and_typed_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            connection = sqlite3.connect(database)
            connection.execute(MINIMAL_ACTIVITY_SCHEMA)
            connection.execute("PRAGMA user_version=4")
            connection.execute(
                """
                INSERT INTO Activity(
                    Id, AppId, ActivityType, LastModifiedTime,
                    IsLocalOnly, ETag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("legacy-id", "legacy-app", 1, 100, 1, 5),
            )
            connection.commit()
            connection.close()
            output_directory = root / "output"

            report = self.parse(database, output_directory)

            self.assertIsNone(report.last_error)
            records = self.read_output(output_directory)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["activity_type"], 1)
            self.assertIs(records[0]["is_local_only"], True)
            self.assertEqual(records[0]["e_tag"], 5)
            self.assertEqual(
                records[0]["start_time_source"],
                "last_modified_time",
            )
            self.assertEqual(
                records[0]["record_source"],
                "activity",
            )

    def test_plugin_emits_merged_and_unmatched_operation_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            connection = sqlite3.connect(database)
            connection.execute(MINIMAL_ACTIVITY_SCHEMA)
            connection.execute(MINIMAL_OPERATION_SCHEMA)
            connection.execute(
                """
                INSERT INTO Activity(
                    Id, AppId, ActivityType, LastModifiedTime,
                    IsLocalOnly, ETag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("shared", "persisted-app", 1, 100, 1, 1),
            )
            connection.executemany(
                """
                INSERT INTO ActivityOperation(
                    OperationOrder, Id, OperationType, AppId,
                    ActivityType, LastModifiedTime,
                    UploadAllowedByPolicy, ETag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (10, "shared", 2, "queued-app", 1, 101, 1, 1),
                    (11, "operation-only", 3, "op-app", 1, 200, 0, 2),
                ),
            )
            connection.commit()
            connection.close()
            output_directory = root / "output"

            report = self.parse(database, output_directory)

            self.assertIsNone(report.last_error)
            records = {
                record["id"]: record
                for record in self.read_output(output_directory)
            }
            self.assertEqual(set(records), {"shared", "operation-only"})
            self.assertEqual(
                records["shared"]["record_source"],
                "activity+activity_operation",
            )
            self.assertEqual(records["shared"]["app_id"], "queued-app")
            self.assertEqual(records["shared"]["operation_order"], 10)
            self.assertEqual(records["shared"]["operation_type"], 2)
            self.assertIs(
                records["shared"]["upload_allowed_by_policy"],
                True,
            )
            self.assertEqual(
                records["operation-only"]["record_source"],
                "activity_operation",
            )
            self.assertEqual(
                records["operation-only"]["operation_order"],
                11,
            )
            self.assertIs(
                records["operation-only"]["upload_allowed_by_policy"],
                False,
            )

    def test_xml_field_contract_matches_model(self):
        configuration = ET.parse(
            os.path.join(CONF_FOLDER, "activity_cache.xml")
        ).getroot()
        xml_fields = {
            field.attrib["input"]: field.attrib["parser"]
            for field in configuration.findall("./mapping/fields/field")
        }
        parser_by_kind = {
            "string": "String",
            "guid": "String",
            "int": "Int",
            "bool": "Bool",
            "datetime": "DateTime",
        }
        expected_fields = {
            "record_source": "String",
            "database_user_version": "Int",
            "start_time_source": "String",
        }
        for column in (
            *ACTIVITY_COLUMNS.values(),
            *ACTIVITY_OPERATION_COLUMNS.values(),
        ):
            expected_fields[column.output_name] = parser_by_kind[column.kind]

        self.assertEqual(configuration.attrib["parser"], "ActivityCache")
        self.assertEqual(
            configuration.find("./mapping/default_parser").attrib["value"],
            "Ignore",
        )
        self.assertEqual(xml_fields, expected_fields)

    def test_fallback_start_time_is_emitted_on_timeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            connection = sqlite3.connect(database)
            connection.execute(MINIMAL_ACTIVITY_SCHEMA)
            connection.execute(
                """
                INSERT INTO Activity(
                    Id, AppId, ActivityType, LastModifiedTime,
                    IsLocalOnly, ETag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("timeline-id", "timeline-app", 1, 100, 1, 1),
            )
            connection.commit()
            connection.close()
            output_directory = root / "output"

            report = self.parse(
                database,
                output_directory,
                "timeline_test",
                with_timeline=True,
            )

            self.assertIsNone(report.last_error)
            records = self.read_output(output_directory, "timeline_test")
            start_records = [
                record
                for record in records
                if "Activity start" in record["timestamp_meaning"]
            ]
            self.assertEqual(len(start_records), 1)
            self.assertEqual(
                start_records[0]["timestamp"],
                "1970-01-01T00:01:40.000000+00:00",
            )
            self.assertEqual(
                start_records[0]["data"]["start_time_source"],
                "last_modified_time",
            )

    def test_wal_is_read_without_modifying_source_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            writer = sqlite3.connect(database)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute(MINIMAL_ACTIVITY_SCHEMA)
            writer.execute("PRAGMA user_version=4")
            writer.execute(
                """
                INSERT INTO Activity(
                    Id, AppId, ActivityType, LastModifiedTime,
                    IsLocalOnly, ETag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("wal-only", "wal-app", 1, 200, 0, 6),
            )
            writer.commit()
            wal = Path(f"{database}-wal")
            self.assertTrue(wal.exists())
            self.assertGreater(wal.stat().st_size, 0)
            source_files = {
                path.name: digest(path)
                for path in root.glob("ActivitiesCache.db*")
            }
            output_directory = root / "output"
            try:
                report = self.parse(database, output_directory)
                self.assertIsNone(report.last_error)
                records = self.read_output(output_directory)
                self.assertEqual(
                    [record["id"] for record in records],
                    ["wal-only"],
                )
                self.assertEqual(
                    {
                        path.name: digest(path)
                        for path in root.glob("ActivitiesCache.db*")
                    },
                    source_files,
                )
            finally:
                writer.close()

    def test_reused_wal_with_stale_tail_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            writer = sqlite3.connect(database)
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute(MINIMAL_ACTIVITY_SCHEMA)
                writer.executemany(
                    """
                    INSERT INTO Activity(
                        Id, AppId, ActivityType, LastModifiedTime,
                        IsLocalOnly, ETag
                    ) VALUES (?, ?, 1, 100, 0, ?)
                    """,
                    (
                        (f"bulk-{index}", "x" * 500, index)
                        for index in range(200)
                    ),
                )
                writer.commit()
                wal = Path(f"{database}-wal")
                initial_size = wal.stat().st_size
                writer.execute("PRAGMA wal_checkpoint(RESTART)").fetchone()
                writer.execute(
                    """
                    INSERT INTO Activity(
                        Id, AppId, ActivityType, LastModifiedTime,
                        IsLocalOnly, ETag
                    ) VALUES (?, ?, 1, 200, 0, ?)
                    """,
                    ("after-restart", "small", 1000),
                )
                writer.commit()
                self.assertEqual(wal.stat().st_size, initial_size)
                source_files = {
                    path.name: digest(path)
                    for path in root.glob("ActivitiesCache.db*")
                }
                output_directory = root / "output"

                report = self.parse(database, output_directory)

                self.assertIsNone(report.last_error)
                self.assertIn(
                    "after-restart",
                    {
                        record["id"]
                        for record in self.read_output(output_directory)
                    },
                )
                self.assertEqual(
                    {
                        path.name: digest(path)
                        for path in root.glob("ActivitiesCache.db*")
                    },
                    source_files,
                )
            finally:
                writer.close()

    def test_malformed_wal_is_rejected_without_modifying_source_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            connection = sqlite3.connect(database)
            connection.execute(MINIMAL_ACTIVITY_SCHEMA)
            connection.commit()
            connection.close()
            Path(f"{database}-wal").write_bytes(b"malformed-wal")
            source_files = {
                path.name: digest(path)
                for path in root.glob("ActivitiesCache.db*")
            }

            report = self.parse(database, root / "output")

            self.assertEqual(report.num_errors, 1)
            self.assertIn("malformed SQLite WAL", report.last_error)
            self.assertEqual(
                {
                    path.name: digest(path)
                    for path in root.glob("ActivitiesCache.db*")
                },
                source_files,
            )

    def test_wal_with_invalid_header_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = create_wal_artifact(root)
            wal = Path(f"{database}-wal")
            wal_data = bytearray(wal.read_bytes())
            wal_data[24] ^= 1
            wal.write_bytes(wal_data)
            source_files = {
                path.name: digest(path)
                for path in root.glob("ActivitiesCache.db*")
            }

            report = self.parse(database, root / "output")

            self.assertEqual(report.num_errors, 1)
            self.assertIn("invalid header checksum", report.last_error)
            self.assertEqual(
                {
                    path.name: digest(path)
                    for path in root.glob("ActivitiesCache.db*")
                },
                source_files,
            )

    def test_wal_with_incompatible_page_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = create_wal_artifact(root)
            database_header = database.read_bytes()[:20]
            encoded_page_size = int.from_bytes(
                database_header[16:18],
                "big",
            )
            database_page_size = (
                65536 if encoded_page_size == 1 else encoded_page_size
            )
            incompatible_page_size = (
                8192 if database_page_size != 8192 else 4096
            )
            wal = Path(f"{database}-wal")
            wal_data = bytearray(wal.read_bytes())
            wal_data[8:12] = incompatible_page_size.to_bytes(4, "big")
            wal.write_bytes(wal_data)
            source_files = {
                path.name: digest(path)
                for path in root.glob("ActivitiesCache.db*")
            }

            report = self.parse(database, root / "output")

            self.assertEqual(report.num_errors, 1)
            self.assertIn(
                "does not match database page size",
                report.last_error,
            )
            self.assertEqual(
                {
                    path.name: digest(path)
                    for path in root.glob("ActivitiesCache.db*")
                },
                source_files,
            )

    def test_database_without_activity_tables_returns_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "not-activity.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE Metadata(Key TEXT, Value TEXT)")
            connection.commit()
            connection.close()

            report = self.parse(database, root / "output")

            self.assertEqual(report.num_errors, 1)
            self.assertIn(
                "neither Activity nor ActivityOperation",
                report.last_error,
            )

    def test_corrupt_database_returns_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "corrupt.db"
            database.write_bytes(b"not a SQLite database")

            report = self.parse(database, root / "output")

            self.assertEqual(report.num_errors, 1)
            self.assertIn("file is not a database", report.last_error)

    def test_bad_row_is_reported_while_valid_row_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "ActivitiesCache.db"
            connection = sqlite3.connect(database)
            connection.execute(MINIMAL_ACTIVITY_SCHEMA)
            connection.executemany(
                """
                INSERT INTO Activity(
                    Id, AppId, ActivityType, LastModifiedTime,
                    IsLocalOnly, ETag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ("good", "app", 1, 100, 1, 1),
                    ("bad", "app", 1, 200, 2, 2),
                ),
            )
            connection.commit()
            connection.close()
            output_directory = root / "output"

            report = self.parse(database, output_directory)

            self.assertEqual(report.num_errors, 1)
            self.assertIn("expects 0 or 1", report.last_error)
            records = self.read_output(output_directory)
            self.assertEqual([record["id"] for record in records], ["good"])

    def test_empty_legacy_fixture_is_supported_without_source_sidecars(self):
        database = Path(
            DATA_FOLDER,
            "sqlite",
            "activities_cache.2016.db",
        )
        source_sidecars = tuple(
            database.parent.glob(f"{database.name}-*")
        )
        self.assertEqual(source_sidecars, ())
        with tempfile.TemporaryDirectory() as temporary:
            report = self.parse(database, Path(temporary), "legacy_fixture")

        self.assertIsNone(report.last_error)
        self.assertEqual(self.report_line_count(report), 0)
        self.assertEqual(
            tuple(database.parent.glob(f"{database.name}-*")),
            (),
        )

    def test_modern_fixture_preserves_fields_with_typed_scalars(self):
        database = Path(DATA_FOLDER, "sqlite", "activities_cache.db")
        with tempfile.TemporaryDirectory() as temporary:
            output_directory = Path(temporary)
            report = self.parse(
                database,
                output_directory,
                "modern_fixture",
            )
            records = self.read_output(
                output_directory,
                "modern_fixture",
            )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 23)
        first = records[0]
        self.assertEqual(
            first["tag"],
            "windows.data.bluelightreduction.settings",
        )
        self.assertEqual(
            first["app_activity_id"],
            "default$windows.data.bluelightreduction.settings|"
            "windows.data.bluelightreduction.settings",
        )
        self.assertIs(type(first["activity_type"]), int)
        self.assertIs(type(first["e_tag"]), int)
        self.assertIs(type(first["is_local_only"]), bool)
        self.assertEqual(first["record_source"], "activity")
        self.assertEqual(first["start_time_source"], "start_time")
        self.assertEqual(
            records[3]["app_activity_id"],
            "ecb32af3-1440-4086-94e3-5311f97f89c4",
        )
        self.assertIn(
            "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}",
            records[21]["app_id"],
        )
