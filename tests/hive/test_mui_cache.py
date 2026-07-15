import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegMuiCache

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


# TODO find data to properly test MuiCache
class MuiCache(TestCase):
    # python -m unittest tests.hive.test_mui_cache.MuiCache.test_mui_cache -v
    def test_mui_cache(self):
        plugin_file = os.path.join(CONF_FOLDER, "mui_cache.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "UsrClass.dat")

        base_output_name = "mui_cache"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".mui_cache.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
                    include_empty=True,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegMuiCache()
        self.assertEqual("RegMuiCache", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 12
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            executables = [json.loads(line)["executable"] for line in fp]

        self.assertEqual(len(executables), expected_lines)
        self.assertIn("C:\\Windows\\System32\\winver.exe", executables)
        self.assertNotIn("C", executables)
