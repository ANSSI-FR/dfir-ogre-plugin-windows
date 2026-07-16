import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import GetThis

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "evtx")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class GetThisTest(TestCase):
    # python -m unittest tests.test_get_this.GetThisTest.test_get_this -v
    def test_get_this(self):
        plugin_file = os.path.join(CONF_FOLDER, "get_this.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "GetThis.csv")
        base_output_name = "get_this_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".getthis.jsonl"
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
        parser = GetThis()
        self.assertEqual("GetThis", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 365)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 20:
                    self.assertEqual(
                        jsoned["data"]["parent_sequence_number"], 6
                    )
                    self.assertEqual(
                        jsoned["data"]["snapshot_id"],
                        "{00000000-0000-0000-0000-000000000000}",
                    )

                i += 1
            self.assertEqual(i, 365)
