import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import XML

from . import BASE_TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "xml")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class XmlTest(TestCase):
    # python -m unittest tests.test_xml.XmlTest.test_xml -v
    def test_xml(self):
        plugin_file = os.path.join(DATA_FOLDER, "xml", "library_config.xml")

        input_file = os.path.join(DATA_FOLDER, "xml", "library.xml")
        base_output_name = "library"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".library.jsonl")
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
        parser = XML()
        self.assertEqual("XML", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
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
                        jsoned["library"],
                        "my library",
                    )
                    self.assertEqual(
                        jsoned["id"],
                        "b1",
                    )
                    self.assertEqual(
                        jsoned["title"],
                        "Programming Rust",
                    )
                    self.assertEqual(
                        jsoned["versions"][0],
                        {"version": "1", "year": "2017", "title": "first version"},
                    )

                i += 1
            self.assertEqual(i, expected_lines)
