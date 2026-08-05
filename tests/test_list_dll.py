import json
import os
from unittest import TestCase

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import ListDll

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "list_dll")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class ListDllTest(TestCase):
    """Tests for the ListDLLs text parser."""

    def test_timeline_include_undated_emits_all_list_dll_rows(self):
        plugin_file = os.path.join(CONF_FOLDER, "list_dll.xml")
        input_file = os.path.join(DATA_FOLDER, "list_dll", "Listdlls.214.txt")

        base_output_name = "Listdlls.214.timeline_undated"
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".listdlls.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=True,
            timeline_include_undated=True,
        )

        report = ListDll().parse(
            input_file,
            plugin_file,
            RunConfiguration([output_config]),
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        file_report = report.output_reports[0].file_reports[0]
        self.assertTrue(file_report.with_timeline)
        self.assertTrue(file_report.timeline_include_undated)
        self.assertEqual(file_report.num_lines, 188)
        self.assertEqual(file_report.file_name, output_file)

        with open(output_file, encoding="utf-8") as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), 188)
        self.assertTrue(all(record["timestamp"] is None for record in records))

    # python -m unittest tests.test_list_dll.ListDllTest.test_list_dll -v
    def test_list_dll(self):
        plugin_file = os.path.join(CONF_FOLDER, "list_dll.xml")
        input_file = os.path.join(DATA_FOLDER, "list_dll", "Listdlls.214.txt")

        base_output_name = "Listdlls.214"
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".listdlls.jsonl"
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
        parser = ListDll()

        run_configuration = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_configuration, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_lines = 188
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)

                # Test first DLL entry (winlogon.exe)
                if i == 0:
                    self.assertEqual(jsoned["process_name"], "winlogon.exe")
                    self.assertEqual(jsoned["pid"], 616)
                    self.assertIn("winlogon.exe", jsoned.get("command_line", ""))
                    self.assertEqual(jsoned["base_addr"], "0x00000000fd270000")
                    self.assertEqual(jsoned["size"], 892928)
                    self.assertEqual(
                        jsoned["path"], "C:\\Windows\\system32\\winlogon.exe"
                    )

                # Test ntdll.dll entry (second entry in first process)
                if i == 1:
                    self.assertEqual(jsoned["process_name"], "winlogon.exe")
                    self.assertEqual(jsoned["pid"], 616)
                    self.assertEqual(jsoned["base_addr"], "0x00000000b89f0000")
                    self.assertEqual(jsoned["size"], 2097152)
                    self.assertEqual(jsoned["path"], "C:\\Windows\\SYSTEM32\\ntdll.dll")

                # Test first DLL entry for lsass.exe (after winlogon section)
                if i == 38:  # After winlogon's entries
                    self.assertEqual(jsoned["process_name"], "lsass.exe")
                    self.assertEqual(jsoned["pid"], 716)
                    self.assertIn("lsass.exe", jsoned.get("command_line", ""))
                    self.assertEqual(jsoned["base_addr"], "0x00000000ed2c0000")
                    self.assertEqual(jsoned["size"], 73728)
                    self.assertEqual(
                        jsoned["path"], "C:\\Windows\\system32\\lsass.exe"
                    )

                # Test first DLL entry for svchost.exe (after lsass section)
                if i == 112:  # After winlogon's 24 + lsass's 57 = 81
                    self.assertEqual(jsoned["process_name"], "svchost.exe")
                    self.assertEqual(jsoned["pid"], 836)
                    self.assertIn("svchost.exe", jsoned.get("command_line", ""))
                    self.assertEqual(jsoned["base_addr"], "0x0000000097a10000")
                    self.assertEqual(jsoned["size"], 69632)
                    self.assertEqual(
                        jsoned["path"], "C:\\Windows\\system32\\svchost.exe"
                    )

                # Test first DLL entry for fontdrvhost.exe (after svchost section)
                if i == 181:  # After winlogon(24) + lsass(57) + svchost(60) = 141
                    self.assertEqual(jsoned["process_name"], "fontdrvhost.exe")
                    self.assertEqual(jsoned["pid"], 872)
                    self.assertIn("fontdrvhost.exe", jsoned.get("command_line", ""))
                    self.assertEqual(jsoned["base_addr"], "0x00000000bb680000")
                    self.assertEqual(jsoned["size"], 856064)
                    self.assertEqual(
                        jsoned["path"], "C:\\Windows\\system32\\fontdrvhost.exe"
                    )

                i += 1
            self.assertEqual(i, expected_lines)
