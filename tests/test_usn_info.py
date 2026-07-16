import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import USNInfo

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "csv")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class UsnInfoTest(TestCase):
    # python -m unittest tests.test_usn_info.UsnInfoTest.test_usn_info -v
    def test_usn_info(self):
        plugin_file = os.path.join(CONF_FOLDER, "usn_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "USNInfo.csv")
        base_output_name = "usn_info_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".usninfo.jsonl"
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
        parser = USNInfo()
        self.assertEqual("USNInfo", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 100)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 8:
                    self.assertEqual(jsoned["data"]["file_attributes_directory"], True)
                    self.assertEqual(
                        jsoned["data"]["snapshot_id"],
                        "{00000000-0000-0000-0000-000000000000}",
                    )

                i += 1
            self.assertEqual(i, 100)
