import json
import os
from unittest import TestCase

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import RegShellBag
from dfir_ogre_plugin_windows.registry.shellbag import group_shellbag_inputs

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestShellBag(TestCase):
    def test_groups_usrclass_and_system_hives_by_vss(self):
        run_config = RunConfiguration(
            [OutputConfiguration("unused", TEMP_FOLDER, with_timeline=False)]
        )

        def entry(file: str, original_filename: str, vss: str) -> BatchEntry:
            metadata = Metadata("test")
            metadata.original_filename = original_filename
            metadata.vss = vss
            return BatchEntry(file, run_config, metadata)

        grouped = group_shellbag_inputs(
            [
                entry("system-2", "C:\\Windows\\System32\\config\\SYSTEM", "vss-2"),
                entry("user-1", "C:\\Users\\one\\UsrClass.dat", "vss-1"),
                entry("user-1b", "C:\\Users\\one-b\\UsrClass.dat", "vss-1"),
                entry("system-1", "C:\\Windows\\System32\\config\\SYSTEM", "vss-1"),
                entry("user-2", "C:\\Users\\two\\UsrClass.dat", "vss-2"),
            ]
        )

        self.assertEqual(
            [entry.file for entry in grouped["vss-1"].usrclass_entries],
            ["user-1", "user-1b"],
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-1"].system_entries], ["system-1"]
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-2"].usrclass_entries], ["user-2"]
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-2"].system_entries], ["system-2"]
        )

    # python -m unittest tests.hive.test_shell_bag.TestShellBag.test_shell_bag -v
    def test_shell_bag(self):
        plugin_file = os.path.join(CONF_FOLDER, "shell_bag.xml")

        usrclass_file = os.path.join(DATA_FOLDER, "hive", "UsrClass_shell.dat")
        system_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat")

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

        usrclass_metadata = Metadata("test")
        usrclass_metadata.vss = "test_vss"
        usrclass_metadata.original_filename = (
            "C:\\Users\\Administrator\\AppData\\Local\\Microsoft\\Windows\\UsrClass.dat"
        )
        system_metadata = Metadata("test")
        system_metadata.vss = "test_vss"
        system_metadata.original_filename = "C:\\Windows\\System32\\config\\SYSTEM"

        entries = [
            BatchEntry(usrclass_file, run_config, usrclass_metadata),
            BatchEntry(system_file, run_config, system_metadata),
        ]

        parser = RegShellBag()
        self.assertEqual("RegShellBag", parser.description().command)  # type: ignore

        report = parser.parse(entries, plugin_file)
        self.assertEqual(None, report.last_error)

        expected_lines = 14
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        records_by_key = {record["key_path"]: record for record in records}
        self.assertEqual(len(records_by_key), expected_lines)

        parent = records_by_key[
            "HKCU\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\BagMRU\\3"
        ]
        self.assertEqual(parent["name"], "Computers and Devices")
        self.assertEqual(parent["path"], "\\Computers and Devices")
        self.assertEqual(
            parent["key_modif_time"], "2021-01-05T14:43:18.814935+00:00"
        )

        leaf = records_by_key[
            "HKCU\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\BagMRU\\3\\0\\0\\1\\0"
        ]
        self.assertEqual(leaf["name"], "EXCH2010")
        self.assertEqual(
            leaf["path"],
            "\\Computers and Devices\\<Users property view>\\\\\\10.0.0.3\\Share\\tmp\\EXCH2010",
        )
        self.assertEqual(
            leaf["modification_time"], "2038-11-06T09:17:10.000000+00:00"
        )
        self.assertNotIn("modification_time_local", leaf)
        self.assertNotIn("timezone_windows", leaf)
        self.assertNotIn("timezone_iana", leaf)
