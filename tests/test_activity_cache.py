import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import ActivityCache

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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
