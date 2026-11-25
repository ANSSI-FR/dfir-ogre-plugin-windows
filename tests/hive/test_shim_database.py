import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegShimDb

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class test_shim_database(TestCase):
    def test_shim_database(self):
        plugin_file = os.path.join(CONF_FOLDER, "shim_database.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")

        base_output_name = "shim_database"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".shim_db.jsonl"
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
        parser = RegShimDb()
        self.assertEqual("RegShimDb", parser.description().command)  # type: ignore

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
                        jsoned["additional_description"],
                        "file_path: C:\\Windows\\AppPatch\\Custom\\Custom64\\{08274920-8908-45c2-9258-8ad67ff77b09}.sdb",
                    )
                    self.assertEqual(jsoned["related_user"], "S-1-5-18")
                    self.assertEqual(
                        jsoned["data"]["key_modif_time"],
                        "2016-01-22T10:42:10.436312+00:00",
                    )
                    self.assertTrue(
                        jsoned["data"]["key_path"].endswith(
                            "\\AppCompatFlags\\InstalledSDB\\{08274920-8908-45c2-9258-8ad67ff77b09}"
                        )
                    )
                if i == 1:
                    self.assertEqual(jsoned["description"], "target: [iisexpress.exe]")

                i += 1
            self.assertEqual(i, expected_lines)
