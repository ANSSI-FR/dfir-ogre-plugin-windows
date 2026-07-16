import json
import os
from unittest import TestCase

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import Csv

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "csv")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class CSVTest(TestCase):
    # python -m unittest tests.test_csv.CSVTest.test_volstat_10_2_2 -v
    def test_volstat_10_2_2(self):
        plugin_file = os.path.join(CONF_FOLDER, "volstat.xml")

        input_file = os.path.join(DATA_FOLDER, "csv", "volstats-10-2-2.csv")
        base_output_name = "volstats-10-2-2"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".volstats.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
                    include_empty=True,
        )

        metadata = Metadata("test")
        parser = Csv()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        print(report.last_error)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 2)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["volumeid"],
                        "0x38CAE3A6CAE35E9E",
                    )

                i += 1
            self.assertEqual(i, 2)

    # python -m unittest tests.test_csv.CSVTest.test_volstat_10_2_4 -v
    def test_volstat_10_2_4(self):
        plugin_file = os.path.join(CONF_FOLDER, "volstat.xml")

        input_file = os.path.join(DATA_FOLDER, "csv", "volstats-10-2-4.csv")
        base_output_name = "volstats-10-2-4"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".volstats.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
                    include_empty=True,
        )

        metadata = Metadata("test")
        parser = Csv()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        print(report.last_error)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_lines = 5
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 3:
                    self.assertEqual(
                        jsoned["volumeid"],
                        "0x6A96C20E96C1DAA9",
                    )
                if i == 1:
                    self.assertEqual(
                        jsoned["shadow_copy"],
                        "{92437215-85cd-4038-8549-63d4a8c26806}",
                    )
                    self.assertEqual(jsoned["volumeid"], "0x0000000000000000")

                i += 1
            self.assertEqual(i, expected_lines)
