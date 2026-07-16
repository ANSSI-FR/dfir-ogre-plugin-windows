import json
import os
import struct
from unittest import TestCase
from unittest.mock import Mock, patch

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Registry,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows import RegBamDam

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")


class BamDam(TestCase):
    def test_timestamp_decode_is_independent_of_native_long_size(self):
        registry = Registry.load(
            os.path.join(DATA_FOLDER, "hive", "SYSTEM_2.dat"),
            r"\HKLM\System",
        )
        keys = registry.glob_keys(
            r"\HKLM\System\*ControlSet*\Services\bam\UserSettings\*"
        )
        key = next(key for key in keys if len(key.values()) > 2)

        native_unpack = struct.unpack

        def windows_unpack(format_string, data):
            if format_string == "L":
                return native_unpack("<L", data)
            return native_unpack(format_string, data)

        output = Mock()
        report = RunReport()
        with patch(
            "dfir_ogre_plugin_windows.registry.bamdam.struct.unpack",
            side_effect=windows_unpack,
        ):
            RegBamDam().parse_key(key, output, report)

        self.assertIsNone(report.last_error)
        self.assertEqual(output.write.call_count, 2)
        record = json.loads(output.write.call_args_list[0].args[0].to_string())
        self.assertEqual(
            record["exec_time"],
            "2019-07-18T15:47:14.088154+00:00",
        )

    # python -m unittest tests.hive.test_bamdam.BamDam.test_bamdam -v
    def test_bamdam(self):
        plugin_file = os.path.join(CONF_FOLDER, "bamdam.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM_2.dat")
        base_output_name = "bamdam"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".bam_dam.jsonl")
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
        parser = RegBamDam()
        self.assertEqual("RegBamDam", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 18
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-21-1201245337-4003845736-3689778284-1000",
                    )
                    self.assertEqual(
                        js["description"],
                        "exec_path: Microsoft.Windows.CloudExperienceHost_cw5n1h2txyewy",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
