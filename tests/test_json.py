import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import Json, Jsonl

from . import BASE_TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "json")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class JsonTest(TestCase):
    # python -m unittest tests.test_json.JsonTest.test_json -v
    def test_json(self):
        plugin_file = os.path.join(DATA_FOLDER, "json", "web_history_json.xml")

        input_file = os.path.join(DATA_FOLDER, "json", "web_history_single.json")
        base_output_name = "json_single"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".web_history.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Json()
        self.assertEqual("Json", parser.description().command)  # type: ignore

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
                        jsoned["url"],
                        "http://code.google.com/p/chrome-screen-capture/",
                    )
                    self.assertEqual(
                        jsoned["title"],
                        "chrome-screen-capture",
                    )
                    self.assertEqual(
                        jsoned["visit_date"],
                        "2011-05-16T11:30:05.000000+00:00",
                    )
                    self.assertEqual(
                        jsoned["visit_count"],
                        2,
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_json.JsonTest.test_jsonl -v
    def test_jsonl(self):
        plugin_file = os.path.join(DATA_FOLDER, "json", "web_history_jsonl.xml")

        input_file = os.path.join(DATA_FOLDER, "json", "web_history.jsonl")
        base_output_name = "jsonl"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".web_history.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Jsonl()
        self.assertEqual("Jsonl", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 3
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
                        "http://code.google.com/p/chrome-screen-capture/",
                    )
                    self.assertEqual(
                        jsoned["title"],
                        "chrome-screen-capture",
                    )
                    self.assertEqual(
                        jsoned["visit_date"],
                        "2011-05-16T11:30:05.000000+00:00",
                    )
                    self.assertEqual(
                        jsoned["visit_count"],
                        2,
                    )

                i += 1
            self.assertEqual(i, expected_lines)
