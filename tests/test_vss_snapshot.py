import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import Csv

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "csv")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class VssSnapshotTest(TestCase):
    """Tests for the VSS snapshot CSV parser."""

    #   python -m unittest tests.test_vss_snapshot.VssSnapshotTest.test_vss_snapshot -v
    def test_vss_snapshot(self):
        plugin_file = os.path.join(CONF_FOLDER, "vss_snapshot.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "VSS_list.csv")

        base_output_name = "vss_snapshot"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.vss_snapshot.jsonl"
        )

        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
                    include_empty=True,
        )

        metadata = Metadata("test")
        parser = Csv()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)


        self.assertIsNone(report.last_error)


        file_report = report.output_reports[0].file_reports[0]
        self.assertEqual(file_report.num_lines, 1)


        self.assertEqual(file_report.file_name, output_file)


        with open(output_file) as fp:
            line = fp.readline().strip()
            jsoned = json.loads(line)

            # Basic field checks.
            self.assertEqual(
                jsoned["snapshot_id"],
                "{dde981e2-0b1d-41d8-8ca5-ba4d87b7d2ca}",
                "SnapshotID should be parsed correctly",
            )
            self.assertEqual(
                jsoned["device_instance"],
                r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1",
                "DeviceInstance should be parsed correctly",
            )
            self.assertEqual(
                jsoned["volume_name"],
                "\\\\?\\Volume{4cada720-c048-4361-96f8-56ae661f8fca}\\",
                "VolumeName should be parsed correctly",
            )

            # CreationTime is parsed by the DateTime parser and output as ISO‑8601.
            self.assertTrue(
                jsoned["creation_time"].startswith("2019-07-24T09:36:44.481"),
                "CreationTime should be an ISO‑8601 timestamp",
            )

            # The Split parser should turn the pipe‑separated attribute string into a list.
            self.assertIsInstance(jsoned["attributes"], list, "Attributes must be a list")
            self.assertEqual(
                len(jsoned["attributes"]), 5, "There should be five attribute flags"
            )
            # At least one known flag should be present.
            self.assertIn(
                "VSS_VOLSNAP_ATTR_PERSISTENT",
                [a.strip() for a in jsoned["attributes"]],
                "Expected attribute flag not found",
            )
