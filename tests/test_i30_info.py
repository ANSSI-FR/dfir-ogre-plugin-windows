import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import I30Info

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "csv")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class I30InfoTest(TestCase):
    #  python -m unittest tests.test_i30_info.I30InfoTest.test_i30_info -v
    def test_i30_info(self):
        plugin_file = os.path.join(CONF_FOLDER, "i30_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "I30Info.csv")
        base_output_name = "i30_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".i30info.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        plugin_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = I30Info()
        self.assertEqual("I30Info", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, plugin_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 43)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 3:
                    self.assertEqual(
                        jsoned["timestamp_meaning"], "$SI:.... - $FN:MACB"
                    )
                    self.assertEqual(jsoned["data_type"], "i30info")
                    self.assertEqual(jsoned["description"], "name: $Boot")
                    self.assertEqual(
                        jsoned["data"]["snapshot_id"],
                        "{00000000-0000-0000-0000-000000000000}",
                    )

                i += 1
            self.assertEqual(i, 43)
