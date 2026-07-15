import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegMassStorageSystem

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")


class TestMassStorage(TestCase):
    # python -m unittest tests.hive.test_mass_storage.TestMassStorage.test_system_mass_storage -v
    def test_system_mass_storage(self):
        plugin_file = os.path.join(CONF_FOLDER, "mass_storage_system.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM_WITH_STORAGE.dat")

        base_output_name = "mass_storage_system"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".mass_storage.jsonl"
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
        parser = RegMassStorageSystem()
        self.assertEqual("RegMassStorageSystem", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 5
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        self.assertEqual(
            records[0]["description"],
            "type: Disk - vendor: JetFlash - product: Transcend_16GB - instance_id: 23NPMBDVM3GMSLXI&0",
        )

        device_records = [
            record
            for record in records
            if record["data"]["instance_id"] == "23NPMBDVM3GMSLXI&0"
        ]
        self.assertEqual(len(device_records), 4)

        expected_lifecycle = {
            "usbstor_install": "2017-04-21T18:57:39.111785+00:00",
            "usbstor_first_install": "2017-04-21T18:57:39.111785+00:00",
            "usbstor_last_arrival": "2017-06-22T18:31:48.873043+00:00",
            "usbstor_last_removal": "2017-06-22T22:20:21.101502+00:00",
        }
        self.assertEqual(
            {
                field: device_records[0]["data"][field]
                for field in expected_lifecycle
            },
            expected_lifecycle,
        )

        expected_timeline_fields = {
            "Usb install": "usbstor_install",
            "Usb first install": "usbstor_first_install",
            "Usb last arrival": "usbstor_last_arrival",
            "Usb last removal": "usbstor_last_removal",
        }
        for meaning, field in expected_timeline_fields.items():
            timeline_records = [
                record
                for record in device_records
                if meaning in record["timestamp_meaning"].split(" - ")
            ]
            self.assertEqual(len(timeline_records), 1)
            self.assertEqual(
                timeline_records[0]["timestamp"],
                expected_lifecycle[field],
            )
