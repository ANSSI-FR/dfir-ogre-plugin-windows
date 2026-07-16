import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import SQLite

from . import BASE_TEMP_FOLDER, CONF_FOLDER, DATA_FOLDER

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "sqlite")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class SqliteTest(TestCase):
    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_activities -v
    def test_sqlite_activities(self):
        plugin_file = os.path.join(CONF_FOLDER, "activity_cache.xml")
        input_file = os.path.join(DATA_FOLDER, "sqlite", "activities_cache.db")

        base_output_name = "sql_activities_test"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".activity_cache.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 23
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["tag"],
                        "windows.data.bluelightreduction.settings",
                    )
                    self.assertEqual(
                        jsoned["app_activity_id"],
                        "default$windows.data.bluelightreduction.settings|"
                        "windows.data.bluelightreduction.settings",
                    )
                if i == 3:
                    self.assertEqual(
                        jsoned["app_activity_id"],
                        "ecb32af3-1440-4086-94e3-5311f97f89c4",
                    )
                if i == 21:
                    self.assertIn(
                        "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}",
                        jsoned["app_id"],
                    )
                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_firefox_history -v
    def test_sqlite_firefox_history(self):
        plugin_file = os.path.join(CONF_FOLDER, "firefox_history.xml")
        input_file = os.path.join(DATA_FOLDER, "sqlite", "firefox_places.sqlite")

        base_output_name = "sql_firefox_history_test"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".browser_history.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 21
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        self.assertEqual(
            records[0]["url"],
            "http://doc.ubuntu-fr.org/visual_studio_code",
        )

        referrer_records = [
            record
            for record in records
            if record["url"] == "https://doc.ubuntu-fr.org/visual_studio_code"
        ]
        self.assertEqual(len(referrer_records), 1)
        self.assertEqual(
            referrer_records[0]["referer"],
            "http://doc.ubuntu-fr.org/visual_studio_code",
        )

    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_chrome_history -v
    def test_sqlite_chrome_history(self):
        plugin_file = os.path.join(CONF_FOLDER, "chrome_history.xml")
        input_file = os.path.join(DATA_FOLDER, "sqlite", "History")

        base_output_name = "sql_chrome_history"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".browser_history.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 69
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        self.assertEqual(
            records[0]["url"],
            "http://code.google.com/p/chrome-screen-capture/",
        )

        referrer_records = [
            record
            for record in records
            if record["url"] == "http://en.softsia.com/download-sk6t.htm"
        ]
        self.assertEqual(len(referrer_records), 1)
        self.assertEqual(
            referrer_records[0]["referer"],
            "http://en.softsia.com/Fun-Cats-Screensaver-download-sk6t.htm",
        )

    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_chrome_history_57 -v
    def test_sqlite_chrome_history_57(self):
        plugin_file = os.path.join(CONF_FOLDER, "chrome_history.xml")
        input_file = os.path.join(DATA_FOLDER, "sqlite", "History-57")

        base_output_name = "sql_chrome_history_57"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".browser_history.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        configuration = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, configuration, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["url"],
                        "https://raw.githubusercontent.com/dfirlabs/chrome-specimens/master/generate-specimens.sh",
                    )
                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_chrome_download_history -v
    def test_sqlite_chrome_download_history(self):
        plugin_file = os.path.join(CONF_FOLDER, "chrome_download_history.xml")
        input_file = os.path.join(DATA_FOLDER, "sqlite", "History-57")

        base_output_name = "sql_chrome_download_history"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".browser_download_history.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        configuration = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, configuration, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["target_path"],
                        "/home/ubuntu/Downloads/plaso-20171231.1.win32.msi",
                    )
                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_sqlite.SqliteTest.test_sqlite_firefox_download_history -v
    def test_sqlite_firefox_download_history(self):
        plugin_file = os.path.join(CONF_FOLDER, "firefox_download_history.xml")
        input_file = os.path.join(
            DATA_FOLDER, "sqlite", "firefox_places.download.sqlite"
        )

        base_output_name = "sql_firefox_download_history"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".browser_download_history.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = SQLite()
        self.assertEqual("SQLite", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["target_path"],
                        "file:///build/Downloads/plaso-static-1.0.2-rc3-win-amd64-vs2010.zip",
                    )
                i += 1
            self.assertEqual(i, expected_lines)
