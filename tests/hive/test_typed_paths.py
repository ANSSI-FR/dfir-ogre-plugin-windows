import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegTypedPaths

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TypedPaths(TestCase):
    # python -m unittest tests.hive.test_typed_paths.TypedPaths.test_typed_paths -v
    def test_typed_paths(self):
        plugin_file = os.path.join(CONF_FOLDER, "typed_paths.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "NTUSER.dat")

        base_output_name = "typed_paths"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".typed_paths.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=True,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegTypedPaths()
        self.assertEqual("RegTypedPaths", parser.description().command)  # type: ignore

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
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(js["description"], "path: C:\\")
                    self.assertEqual(js["additional_description"], "index: url1")

                i += 1
            self.assertEqual(i, expected_lines)
