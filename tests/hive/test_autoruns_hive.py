import json
import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    Value,
)
from dfir_ogre_plugin_windows import (
    RegAutorunsSoftware,
    RegAutorunsSystem,
    RegAutorunsUser,
)


from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)

class TestAutoruns(TestCase):
    @staticmethod
    def _make_notify_key(path, dll_name, owner_sid, mtime):
        security_record = Record()
        security_record.add("owner_sid", Value.String(owner_sid))
        security_record.add("group_sid", Value.String(owner_sid))
        security_descriptor = Mock()
        security_descriptor.to_record.return_value = security_record

        key = Mock()
        key.path = path
        key.mtime = mtime
        key.security_descriptor = security_descriptor

        def value_data(name, default=None):
            return dll_name if name == "DllName" else default

        key.value_data.side_effect = value_data
        return key

    def _parse_notify_keys(self, parser, config_name, hive_root, output_name):
        notify_query = (
            f"\\{hive_root}\\Microsoft\\Windows NT\\CurrentVersion"
            "\\Winlogon\\Notify"
        )
        parent_path = notify_query.removeprefix("\\")
        package_path = parent_path + "\\ExamplePackage"
        missing_dll_path = parent_path + "\\MissingDllName"
        parent_time = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        package_time = datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

        parent_key = self._make_notify_key(
            parent_path,
            "legacy-notify.dll",
            "S-1-5-21-100",
            parent_time,
        )
        package_key = self._make_notify_key(
            package_path,
            "package-notify.dll",
            "S-1-5-21-200",
            package_time,
        )
        missing_dll_key = self._make_notify_key(
            missing_dll_path,
            None,
            "S-1-5-21-300",
            datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc),
        )

        class RegistryWithNotify:
            def __init__(self):
                self.queries = []

            def glob_keys(self, path):
                self.queries.append(path)
                if path == notify_query:
                    return [parent_key]
                if path == notify_query + "\\*":
                    return [package_key, missing_dll_key]
                return []

        registry = RegistryWithNotify()
        plugin_file = os.path.join(CONF_FOLDER, config_name)
        output_file = os.path.join(
            TEMP_FOLDER, f"{output_name}.reg_autoruns.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    output_name,
                    TEMP_FOLDER,
                    with_timeline=True,
                    include_empty=True,
                )
            ]
        )
        with patch(
            "dfir_ogre_plugin_windows.registry.autoruns_hive.Registry"
        ) as registry_type:
            registry_type.load.return_value = registry
            report = parser.parse(
                "unused-hive",
                plugin_file,
                run_config,
                Metadata("test"),
            )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as output:
            records = [json.loads(line) for line in output]

        return {
            "records": {
                record["data"]["key_path"]: record for record in records
            },
            "queries": registry.queries,
            "notify_query": notify_query,
            "parent_path": parent_path,
            "package_path": package_path,
            "missing_dll_path": missing_dll_path,
            "package_time": package_time,
        }

    def test_winlogon_notify_reads_parent_and_package_keys(self):
        cases = (
            (
                RegAutorunsSoftware(),
                "autoruns_software.xml",
                "HKLM\\SOFTWARE",
                "winlogon_notify_software",
            ),
            (
                RegAutorunsUser(),
                "autoruns_user.xml",
                "HKCU\\Software",
                "winlogon_notify_user",
            ),
        )

        for parser, config_name, hive_root, output_name in cases:
            with self.subTest(parser=parser.description().command):
                result = self._parse_notify_keys(
                    parser, config_name, hive_root, output_name
                )
                records = result["records"]

                self.assertEqual(
                    set(records),
                    {result["parent_path"], result["package_path"]},
                )
                self.assertIn(
                    result["notify_query"] + "\\*", result["queries"]
                )
                self.assertNotIn(
                    result["notify_query"] + "\\*\\*", result["queries"]
                )
                self.assertNotIn(result["missing_dll_path"], records)

                parent_record = records[result["parent_path"]]
                self.assertEqual(
                    parent_record["data"]["values"],
                    [{"name": "DllName", "data": "legacy-notify.dll"}],
                )

                package_record = records[result["package_path"]]
                self.assertEqual(
                    package_record["data"]["type"], "Winlogon Notify"
                )
                self.assertEqual(
                    package_record["data"]["values"],
                    [{"name": "DllName", "data": "package-notify.dll"}],
                )
                self.assertEqual(
                    package_record["timestamp"],
                    result["package_time"].isoformat(timespec="microseconds"),
                )
                self.assertEqual(
                    package_record["data"]["key_modif_time"],
                    result["package_time"].isoformat(timespec="microseconds"),
                )
                self.assertEqual(
                    package_record["related_user"], "S-1-5-21-200"
                )
                self.assertEqual(
                    package_record["data"]["key_security"]["owner_sid"],
                    "S-1-5-21-200",
                )

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
                    self.assertEqual(
                        js["data"]["values"],
                        [{"name": "SecurityProviders", "data": "credssp.dll"}],
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
                    self.assertEqual(
                        js["data"]["values"],
                        [{"name": "Shell", "data": "explorer.exe"}],
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
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        js = records[0]
        self.assertEqual(
            js["related_user"],
            "S-1-5-18",
        )
        self.assertEqual(
            js["description"],
            "type: Startup Run - key_path: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        )
        self.assertEqual(
            js["additional_description"],
            "values: ['name':'OneDrive', 'data':'\"C:\\Users\\Admin\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe\" /background']",
        )
        self.assertEqual(
            js["data"]["values"],
            [
                {
                    "name": "OneDrive",
                    "data": '"C:\\Users\\Admin\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe" /background',
                }
            ],
        )
