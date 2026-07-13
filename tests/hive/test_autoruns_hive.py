import os
import json
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import RegAutorunsSystem,RegAutorunsSoftware, RegAutorunsUser


from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)

class TestAutoruns(TestCase):
    #   python -m unittest tests.hive.test_autoruns_hive.TestAutoruns.test_autoruns_system -v
    def test_autoruns_system(self):
        plugin_file = os.path.join(CONF_FOLDER, "autoruns_system.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat")

        base_output_name = "autoruns_system"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.reg_autoruns.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=True,              # no extra options
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegAutorunsSystem()
        self.assertEqual("RegAutorunsSystem", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)

        expected_lines = 98
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(expected_lines, lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(output_file, filename)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 9:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",
                    )
                    self.assertEqual(
                        js["description"],
                        "type: Security Providers - key_path: HKLM\\SYSTEM\\ControlSet002\\Control\\SecurityProviders",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "values: ['name':'SecurityProviders', 'data':'credssp.dll']",
                    )

                if i == 41:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-32-544",
                    )
                    self.assertEqual(
                        js["description"],
                        "type: Winsock2 Parameters - key_path: HKLM\\SYSTEM\\ControlSet002\\Services\\WinSock2\\Parameters\\NameSpace_Catalog5\\Catalog_Entries64\\000000000005",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "values: ['name':'display', 'data':'Bluetooth Namespace', 'name':'library_path', 'data':'%SystemRoot%\\system32\\wshbth.dll']",
                    )

                if i == 90:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-32-544",
                    )
                    self.assertEqual(
                        js["description"],
                        "type: Winsock2 Parameters - key_path: HKLM\\SYSTEM\\ControlSet002\\Services\\WinSock2\\Parameters\\Protocol_Catalog9\\Catalog_Entries64\\000000000007",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "values: ['name':'PackedCatalogItem', 'data':'%SystemRoot%\\system32\\mswsock.dll']",
                    )

                i += 1
        self.assertEqual(i, expected_lines)

    #  python -m unittest tests.hive.test_autoruns_hive.TestAutoruns.test_autoruns_software -v
    def test_autoruns_software(self):

        plugin_file = os.path.join(CONF_FOLDER, "autoruns_software.xml")

        # Input hive
        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")

        # Output file name (JSON‑Lines)
        base_output_name = "autoruns_software"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.reg_autoruns.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=True,               # no extra options
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegAutorunsSoftware()
        self.assertEqual(
            "RegAutorunsSoftware", parser.description().command  # type: ignore
        )

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)
        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(expected_lines, lines)

        # Verify the output file path is correct
        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(output_file, filename)

        with open(output_file) as fp:
            for i, line in enumerate(fp):
                js = json.loads(line)
                if i == 0:   # line index where the Network Providers entry appears
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",
                    )
                    self.assertEqual(
                        js["description"],
                        "type: Winlogon Shell - key_path: HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "values: ['name':'Shell', 'data':'explorer.exe']",
                    )
                    break


    #   python -m unittest tests.hive.test_autoruns_hive.TestAutoruns.test_autoruns_user -v
    def test_autoruns_user(self):
        """
        Verify that RegAutorunsUser correctly parses the HKCU hive and emits the
        expected number of records and a few spot‑checked fields.
        """

        plugin_file = os.path.join(CONF_FOLDER, "autoruns_user.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "NTUSER.dat")

        base_output_name = "autoruns_user"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.reg_autoruns.jsonl"
        )
        # Ensure a clean start
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
        parser = RegAutorunsUser()
        self.assertEqual(
            "RegAutorunsUser", parser.description().command  # type: ignore
        )

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(expected_lines, lines)

        # Verify that the output file path matches what the OutputConfiguration asked for
        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(output_file, filename)

        with open(output_file) as fp:
            i = 0
            for  line in fp:
                i += 1
                js = json.loads(line)
                if i == 0:   # adjust if you add/remove entries in the fixture
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",               # SID of the test user in the fixture
                    )
                    self.assertEqual(
                        js["description"],
                        "type: Startup Run - key_path: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "values: ['name':'OneDrive', 'data':'\"C:\\Users\\Admin\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe\" /background']",
                    )
                    break
        # Ensure we actually hit the line we expected
        self.assertEqual(i, expected_lines)
