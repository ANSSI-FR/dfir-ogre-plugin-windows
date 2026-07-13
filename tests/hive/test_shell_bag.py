import json
import os
from unittest import TestCase

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import RegShellBag

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestShellBag(TestCase):
    # python -m unittest tests.hive.test_shell_bag.TestShellBag.test_shell_bag -v
    def test_shell_bag(self):
        plugin_file = os.path.join(CONF_FOLDER, "shell_bag.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "UsrClass_shell.dat")

        base_output_name = "shell_bag"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".shellbags.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegShellBag()
        self.assertEqual("RegShellBag", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 6
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 4:
                    self.assertEqual(
                        jsoned["name"],
                        "EXCH2010",
                    )
                    self.assertEqual(
                        jsoned["path"],
                        "\\Computers and Devices\\<Users property view>\\\\\\10.0.0.3\\Share\\tmp\\EXCH2010",
                    )
                i += 1
            self.assertEqual(i, expected_lines)
