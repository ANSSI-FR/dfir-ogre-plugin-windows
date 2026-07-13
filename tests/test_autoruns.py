import json
import os
from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import Autoruns
from dfir_ogre_plugin_windows.autoruns import AutorunsDateParser

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "autoruns")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AutorunsTest(TestCase):
    # python -m unittest tests.test_autoruns.AutorunsTest.test_autoruns -v
    def test_autoruns(self):
        output_file, report = self.parse_autoruns("autoruns.csv")

        self.assertEqual(None, report.last_error)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 99)
        self.assertEqual(
            report.output_reports[0].file_reports[0].file_name,
            output_file,
        )

        with open(output_file) as fp:
            rows = [json.loads(line) for line in fp]

        self.assertEqual(len(rows), 99)
        self.assertEqual(
            rows[3]["additional_description"],
            "enabled: true - category: Hijacks - profile: System-wide - image_path: c:\\program files\\internet explorer\\iexplore.exe",
        )

    # python -m unittest tests.test_autoruns.AutorunsTest.test_autoruns_2 -v
    def test_autoruns_2(self):
        output_file, report = self.parse_autoruns("autoruns_2.csv")

        self.assertEqual(None, report.last_error)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 44)
        self.assertEqual(
            report.output_reports[0].file_reports[0].file_name,
            output_file,
        )

        with open(output_file) as fp:
            rows = [json.loads(line) for line in fp]

        self.assertEqual(len(rows), 44)
        self.assertEqual(
            rows[3]["additional_description"],
            "enabled: true - category: Logon - profile: System-wide - image_path: c:\\windows\\system32\\userinit.exe",
        )

    # python -m unittest tests.test_autoruns.AutorunsTest.test_autoruns_3 -v
    def test_autoruns_3(self):
        output_file, report = self.parse_autoruns("autoruns_3.csv")

        self.assertEqual(None, report.last_error)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 1372)
        self.assertEqual(
            report.output_reports[0].file_reports[0].file_name,
            output_file,
        )

        with open(output_file) as fp:
            rows = [json.loads(line) for line in fp]

        self.assertEqual(len(rows), 1372)
        self.assertEqual(
            rows[3]["additional_description"],
            "enabled: true - category: Hijacks - profile: System-wide - image_path: c:\\program files\\internet explorer\\iexplore.exe",
        )

    def test_date_parser_falls_back_to_best_effort_parsing(self):
        parser = AutorunsDateParser()

        self.assertEqual(
            parser.parse_date("20221122-162341"),
            datetime(2022, 11, 22, 16, 23, 41, tzinfo=timezone.utc),
        )
        self.assertEqual(
            parser.parse_date("01/04/2024 09:26"),
            datetime(2024, 4, 1, 9, 26, tzinfo=timezone.utc),
        )
        self.assertEqual(
            parser.parse_date("April 1, 2024 09:26"),
            datetime(2024, 4, 1, 9, 26, tzinfo=timezone.utc),
        )

    def test_date_parser_returns_empty_record_for_unparseable_dates(self):
        parser = AutorunsDateParser()

        self.assertTrue(parser.parse("", "date").is_empty())
        self.assertTrue(parser.parse("not a date", "date").is_empty())

    def parse_autoruns(self, filename):
        plugin_file = os.path.join(CONF_FOLDER, "autoruns.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", filename)

        base_output_name = os.path.splitext(filename)[0]
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".autoruns.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=True,
        )

        metadata = Metadata("test")
        parser = Autoruns()

        run_configuration = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_configuration, metadata)
        print(report.last_error)

        return output_file, report
