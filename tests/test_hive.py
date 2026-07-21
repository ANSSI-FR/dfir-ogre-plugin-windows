import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import HiveKeys

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "hive")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class HiveTest(TestCase):
    # python -m unittest tests.test_hive.HiveTest.test_hive_keys -v
    def test_hive_keys(self):
        plugin_file = os.path.join(CONF_FOLDER, "hive.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "testhive")
        base_output_name = "hive_test"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".hive.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
            {"root_name": "HELLO", "filter": "HELLO\\\\subpath-test\\\\"},
        )

        metadata = Metadata("test")
        parser = HiveKeys()
        description = parser.description()
        self.assertEqual("HiveKey", description.command)  # type: ignore
        self.assertEqual(
            "Extract Keys and Values from Windows Registry File",
            description.description,  # type: ignore
        )

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 6
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            rows = [json.loads(line) for line in fp]

        self.assertEqual(len(rows), expected_lines)
        self.assertEqual(
            rows[3]["data"]["path"],
            "HELLO\\subpath-test\\with-two-levels-of-subkeys",
        )

        for row in rows:
            data = row["data"]
            self.assertEqual("hive", row["data_type"])
            self.assertNotIn("values", data)
            self.assertIn("mtime", data)
            self.assertEqual("Default", data["name"])
            self.assertEqual("", data["data"])
            self.assertEqual("REG_NONE", data["type"])
            self.assertEqual(0, data["size"])
            self.assertTrue(data["is_placeholder"])
            self.assertIn("invalid_signature", data)
            self.assertIn("error", data)
            self.assertIsInstance(data["security_descriptor"], dict)
