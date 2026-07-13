import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import RegExp

# Re‑use the same temporary‑folder helpers that the other tests use
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "systeminfo")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestSystemInfo(TestCase):
    """Validate that the system‑info XML configuration parses the CSV correctly."""
    # python -m unittest tests.test_system_info.TestSystemInfo.test_systeminfo -v
    def test_systeminfo(self):

        plugin_file = os.path.join(CONF_FOLDER, "system_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "Systeminfo.csv")

        base_output_name = "systeminfo"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.systeminfo.jsonl"
        )

        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=True,            # no extra parameters
        )
        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore


        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertIsNone(report.last_error, msg=f"Parse error: {report.last_error}")

        expected_lines = 1
        actual_lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(
            expected_lines,
            actual_lines,
            f"Expected {expected_lines} parsed line(s), got {actual_lines}",
        )

        # Verify that the file name matches what we asked for
        self.assertEqual(report.output_reports[0].file_reports[0].file_name, output_file)

        # ------------------------------------------------------------------
        # Load the generated JSONL and check a few fields
        # ------------------------------------------------------------------
        with open(output_file, "r", encoding="utf-8") as fp:
            line = fp.readline().strip()
            self.assertTrue(line, "Output file is empty")
            js = json.loads(line)

            self.assertEqual(js.get("host_name"), "W2022")
            self.assertEqual(
                js.get("os_name"),
                "Microsoft Windows Server 2022 Standard",
                "OS name field mismatch",
            )
            self.assertEqual(js.get("system_type"), "x64-based PC")
            self.assertEqual(js.get("total_physical_memory"), "2\xa0187 MB")
