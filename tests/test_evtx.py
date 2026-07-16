import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import Evtx

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "evtx")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class EvtxTest(TestCase):
    # python -m unittest tests.test_evtx.EvtxTest.test_evtx -v
    def test_evtx(self):
        plugin_file = os.path.join(CONF_FOLDER, "evtx.xml")

        input_file = os.path.join(DATA_FOLDER, "evtx", "kernel_pnp.evtx")
        base_output_name = "kernel_pnp"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".windows_events.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Evtx()
        self.assertEqual("Evtx", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 123)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    data = jsoned["data"]
                    self.assertEqual(
                        data["system"]["provider"]["guid"],
                        "9c205a39-1250-487d-abd7-e831c6290539",
                    )
                    self.assertEqual(
                        data["event_data"]["class_guid"],
                        "4d36e966-e325-11ce-bfc1-08002be10318",
                    )
                    self.assertEqual(
                        data["event_data"]["device_instance_id"],
                        r"ROOT\ACPI_HAL\0000",
                    )
                if i == 3:
                    self.assertEqual(
                        jsoned["data"]["system"]["security"]["user_id"],
                        "S-1-5-18",
                    )

                i += 1
            self.assertEqual(i, 123)
