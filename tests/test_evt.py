import json
import os
import unittest


from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import WinEvt

# The test suite defines a couple of handy constants that point to temporary
# directories and the location of the configuration files.
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "evt")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestWinEvt(unittest.TestCase):
    """Integration test for the ``WinEvt`` plugin (EVT‑format)."""

    # python -m unittest tests.test_evt.TestWinEvt.test_evt_file -v
    def test_evt_file(self):
        plugin_file = os.path.join(CONF_FOLDER, "evt.xml")
        input_file = os.path.join(DATA_FOLDER, "evt", "SysEvent.Evt")

        base_output_name = "sys_event"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.evt.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_cfg = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=False,           # no extra options
        )
        run_cfg = RunConfiguration([output_cfg])

        metadata = Metadata("test")
        parser = WinEvt()
        self.assertEqual("WinEvt", parser.description().command) # type: ignore

        report = parser.parse(input_file, plugin_file, run_cfg, metadata)

        self.assertIsNone(report.last_error)


        expected_lines = 6611
        output_report = report.output_reports[0]
        file_report = output_report.file_reports[0]

        self.assertEqual(file_report.num_lines, expected_lines)
        self.assertEqual(file_report.file_name, output_file)

        with open(output_file, "r", encoding="utf-8") as fp:
            i =0
            for line in fp:
                js = json.loads(line)
                if i == 2420:
                    self.assertEqual(
                        js["description"],
                        "Service Control Manager:7036",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "[Google Update Service (gupdate), running]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
        # If we reach this point, the EVT parser behaved as expected.
