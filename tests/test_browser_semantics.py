"""Exercise shipped browser queries through the native SQLite parser."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import SQLite

from . import CONF_FOLDER


class BrowserSemanticsTest(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.database = self.folder / "browser.sqlite"

    def parse_browser(self, config, data_type, expected_records, expected_events):
        metadata = Metadata("browser-host")
        metadata.archive = "browser-evidence.zip"
        metadata.original_filename = "browser.sqlite"
        outputs = [
            OutputConfiguration(
                name, str(self.folder), with_timeline=timeline, include_empty=True
            )
            for name, timeline in (("records", False), ("events", True))
        ]
        report = SQLite().parse(
            str(self.database),
            str(Path(CONF_FOLDER) / config),
            RunConfiguration(outputs),
            metadata,
        )
        self.assertIsNone(report.last_error)
        records, events = [
            [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for path in (
                self.folder / f"records.{data_type}.jsonl",
                self.folder / f"events.{data_type}.jsonl",
            )
        ]
        self.assertEqual(
            {
                Path(file.file_name).name: file.num_lines
                for output in report.output_reports
                for file in output.file_reports
            },
            {
                f"records.{data_type}.jsonl": len(expected_records),
                f"events.{data_type}.jsonl": len(expected_events),
            },
        )
        expected_metadata = {
            "computer": "browser-host",
            "data_type": data_type,
            "archive": "browser-evidence.zip",
            "original_filename": "browser.sqlite",
        }
        for record in records:
            self.assertEqual(record.pop("ogre_md"), expected_metadata)
        self.assertCountEqual(records, expected_records)
        self.assertCountEqual(
            [
                (event["data"]["url"], event["timestamp_meaning"], event["timestamp"])
                for event in events
            ],
            expected_events,
        )
        for event in events:
            self.assertEqual(event["metadata"], expected_metadata)
            self.assertEqual(event["data_type"], data_type)
            self.assertEqual(event["description"], f"url: {event['data']['url']}")
            self.assertIn(event["data"], expected_records)
            self.assertEqual(
                event["timestamp"], event["data"][event["timestamp_meaning"]]
            )
        return events

    def assert_history_visits(self, config):
        # Visit IDs deliberately differ from URL IDs: from_visit refers to a
        # visit, and that visit supplies the referring URL. Repeated visits to
        # the same URL must retain their own timestamp and referrer.
        events = self.parse_browser(
            config,
            "browser_history",
            [
                {
                    "url": "https://origin.example/",
                    "title": "Origin",
                    "visit_date": "2024-01-01T00:00:00.123000+00:00",
                    "visit_count": 1,
                    "referer": None,
                    "hidden": 0,
                },
                {
                    "url": "https://target.example/",
                    "title": None,
                    "visit_date": "2024-01-01T00:00:02.456000+00:00",
                    "visit_count": 2,
                    "referer": "https://origin.example/",
                    "hidden": 1,
                },
                {
                    "url": "https://target.example/",
                    "title": None,
                    "visit_date": "2024-01-01T00:00:03.789000+00:00",
                    "visit_count": 2,
                    "referer": None,
                    "hidden": 1,
                },
            ],
            [
                (
                    "https://origin.example/",
                    "visit_date",
                    "2024-01-01T00:00:00.123000+00:00",
                ),
                (
                    "https://target.example/",
                    "visit_date",
                    "2024-01-01T00:00:02.456000+00:00",
                ),
                (
                    "https://target.example/",
                    "visit_date",
                    "2024-01-01T00:00:03.789000+00:00",
                ),
            ],
        )
        referred = next(event for event in events if event["data"]["referer"])
        self.assertEqual(
            referred["additional_description"],
            "visit_count: 2 - referer: https://origin.example/",
        )

    def test_chrome_history_preserves_each_visit_and_its_referrer(self):
        # Chromium stores microseconds since 1601-01-01. The raw values below
        # encode 2024-01-01 00:00:00.123, 00:00:02.456 and 00:00:03.789 UTC.
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript(
                """
                CREATE TABLE urls (
                    id INTEGER PRIMARY KEY, url TEXT, title TEXT,
                    visit_count INTEGER, hidden INTEGER
                );
                CREATE TABLE visits (
                    id INTEGER PRIMARY KEY, url INTEGER,
                    from_visit INTEGER, visit_time INTEGER
                );
                INSERT INTO urls VALUES
                    (10, 'https://origin.example/', 'Origin', 1, 0),
                    (20, 'https://target.example/', NULL, 2, 1);
                INSERT INTO visits VALUES
                    (101, 10, 0, 13348540800123000),
                    (102, 20, 0, 13348540803789000),
                    (103, 20, 101, 13348540802456000);
                """
            )
        self.assert_history_visits("chrome_history.xml")

    def test_firefox_history_preserves_each_visit_and_its_referrer(self):
        # Firefox visit_date uses microseconds since the Unix epoch. The visit
        # IDs put the later target visit first, so expected times are independent
        # of insertion order and the query's traversal order.
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript(
                """
                CREATE TABLE moz_places (
                    id INTEGER PRIMARY KEY, url TEXT, title TEXT,
                    visit_count INTEGER, hidden INTEGER
                );
                CREATE TABLE moz_historyvisits (
                    id INTEGER PRIMARY KEY, place_id INTEGER,
                    from_visit INTEGER, visit_date INTEGER
                );
                INSERT INTO moz_places VALUES
                    (10, 'https://origin.example/', 'Origin', 1, 0),
                    (20, 'https://target.example/', NULL, 2, 1),
                    (30, 'https://unvisited.example/', 'No visit', 0, 0);
                INSERT INTO moz_historyvisits VALUES
                    (101, 10, 0, 1704067200123000),
                    (102, 20, 0, 1704067203789000),
                    (103, 20, 101, 1704067202456000);
                """
            )
        self.assert_history_visits("firefox_history.xml")

    def test_chrome_downloads_preserve_sizes_states_and_optional_end_time(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript(
                """
                CREATE TABLE downloads (
                    id INTEGER PRIMARY KEY, target_path TEXT,
                    received_bytes INTEGER, total_bytes INTEGER,
                    start_time INTEGER, end_time INTEGER, state INTEGER,
                    danger_type INTEGER, interrupt_reason INTEGER, opened INTEGER
                );
                CREATE TABLE downloads_url_chains (id INTEGER, url TEXT);
                INSERT INTO downloads VALUES
                    (10, 'C:\\Downloads\\complete.zip', 5000000123, 5000000123,
                     13348540800123000, 13348540802456000, 1, 0, 0, 1),
                    (20, 'C:\\Downloads\\interrupted.zip', 4096, 8192,
                     13348540803789000, NULL, 2, 4, 21, 0);
                INSERT INTO downloads_url_chains VALUES
                    (10, 'https://download.example/complete.zip'),
                    (20, 'https://download.example/interrupted.zip');
                """
            )
        events = self.parse_browser(
            "chrome_download_history.xml",
            "browser_download_history",
            [
                {
                    "target_path": r"C:\Downloads\complete.zip",
                    "url": "https://download.example/complete.zip",
                    "received_bytes": 5000000123,
                    "total_bytes": 5000000123,
                    "start_time": "2024-01-01T00:00:00.123000+00:00",
                    "end_time": "2024-01-01T00:00:02.456000+00:00",
                    "state": 1,
                    "danger_type": 0,
                    "interrupt_reason": 0,
                    "opened": 1,
                },
                {
                    "target_path": r"C:\Downloads\interrupted.zip",
                    "url": "https://download.example/interrupted.zip",
                    "received_bytes": 4096,
                    "total_bytes": 8192,
                    "start_time": "2024-01-01T00:00:03.789000+00:00",
                    "end_time": None,
                    "state": 2,
                    "danger_type": 4,
                    "interrupt_reason": 21,
                    "opened": 0,
                },
            ],
            [
                (
                    "https://download.example/complete.zip",
                    "start_time",
                    "2024-01-01T00:00:00.123000+00:00",
                ),
                (
                    "https://download.example/complete.zip",
                    "end_time",
                    "2024-01-01T00:00:02.456000+00:00",
                ),
                (
                    "https://download.example/interrupted.zip",
                    "start_time",
                    "2024-01-01T00:00:03.789000+00:00",
                ),
            ],
        )
        completed = next(
            event
            for event in events
            if event["data"]["url"] == "https://download.example/complete.zip"
            and event["timestamp_meaning"] == "end_time"
        )
        self.assertEqual(
            completed["additional_description"],
            "received_bytes: 5000000123 - total_bytes: 5000000123",
        )

    def test_firefox_download_metadata_end_time_is_unix_milliseconds(self):
        # Places annotations use Unix microseconds, but JSON endTime comes from
        # JavaScript Date.now() (milliseconds). These encode 2024-01-01 UTC.
        # https://github.com/mozilla-firefox/firefox/blob/main/browser/components/downloads/DownloadsCommon.sys.mjs
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript(
                """
                CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
                CREATE TABLE moz_anno_attributes (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE moz_annos (
                    place_id INTEGER, anno_attribute_id INTEGER,
                    content TEXT, dateAdded INTEGER
                );
                INSERT INTO moz_places VALUES
                    (10, 'https://download.example/complete.zip'),
                    (20, 'https://download.example/canceled.zip');
                INSERT INTO moz_anno_attributes VALUES
                    (1, 'downloads/destinationFileURI'),
                    (2, 'downloads/metaData');
                """
            )
            db.executemany(
                "INSERT INTO moz_annos VALUES (?, ?, ?, ?)",
                [
                    (10, 1, "file:///Downloads/complete.zip", 1704067200123000),
                    (
                        10,
                        2,
                        json.dumps(
                            {
                                "state": 1,
                                "endTime": 1704067202456,
                                "fileSize": 5000000123,
                                "deleted": False,
                            }
                        ),
                        1704067202456000,
                    ),
                    (20, 1, "file:///Downloads/canceled.zip", 1704067203789000),
                    (
                        20,
                        2,
                        json.dumps({"state": 3, "deleted": True}),
                        1704067204000000,
                    ),
                ],
            )

        events = self.parse_browser(
            "firefox_download_history.xml",
            "browser_download_history",
            [
                {
                    "target_path": "file:///Downloads/complete.zip",
                    "url": "https://download.example/complete.zip",
                    "total_bytes": 5000000123,
                    "start_time": "2024-01-01T00:00:00.123000+00:00",
                    "end_time": "2024-01-01T00:00:02.456000+00:00",
                    "state": 1,
                    "deleted": False,
                },
                {
                    "target_path": "file:///Downloads/canceled.zip",
                    "url": "https://download.example/canceled.zip",
                    "total_bytes": None,
                    "start_time": "2024-01-01T00:00:03.789000+00:00",
                    "end_time": None,
                    "state": 3,
                    "deleted": True,
                },
            ],
            [
                (
                    "https://download.example/complete.zip",
                    "start_time",
                    "2024-01-01T00:00:00.123000+00:00",
                ),
                (
                    "https://download.example/complete.zip",
                    "end_time",
                    "2024-01-01T00:00:02.456000+00:00",
                ),
                (
                    "https://download.example/canceled.zip",
                    "start_time",
                    "2024-01-01T00:00:03.789000+00:00",
                ),
            ],
        )
        completed = next(
            event
            for event in events
            if event["data"]["url"] == "https://download.example/complete.zip"
            and event["timestamp_meaning"] == "end_time"
        )
        canceled = next(
            event
            for event in events
            if event["data"]["url"] == "https://download.example/canceled.zip"
        )
        self.assertIs(completed["data"]["deleted"], False)
        self.assertIs(canceled["data"]["deleted"], True)
        self.assertEqual(
            completed["additional_description"],
            "total_bytes: 5000000123 - deleted: false",
        )
