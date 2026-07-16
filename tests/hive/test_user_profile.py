import json
import os
from unittest import TestCase
from unittest.mock import Mock, patch

from dfir_ogre_common import Metadata, OutputConfiguration, Registry, RunConfiguration

from dfir_ogre_plugin_windows import RegUserProfile

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class UserProfile(TestCase):
    def _parse_with_user_list(self, user_list_values):
        plugin_file = os.path.join(CONF_FOLDER, "user_profile.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")
        real_registry = Registry.load(input_file, "\\HKLM\\Software")

        values = []
        for name, data in user_list_values:
            registry_value = Mock()
            registry_value.name.return_value = name
            registry_value.data.return_value = data
            values.append(registry_value)

        user_list_key = Mock()
        user_list_key.values.return_value = values
        user_list_path = (
            "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
            "\\SpecialAccounts\\UserList"
        )

        class RegistryWithUserList:
            def glob_keys(self, path):
                if path == user_list_path:
                    return [user_list_key]
                return real_registry.glob_keys(path)

        base_output_name = "user_profile_hidden_states"
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".user_profile.jsonl"
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

        with patch(
            "dfir_ogre_plugin_windows.registry.user_profile.Registry"
        ) as registry_type:
            registry_type.load.return_value = RegistryWithUserList()
            report = RegUserProfile().parse(
                input_file,
                plugin_file,
                run_config,
                Metadata("test"),
            )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as output:
            return {
                record["data"]["user_name"]: record["data"]
                for record in (json.loads(line) for line in output)
            }

    def test_user_profile_hidden_state_semantics(self):
        records = self._parse_with_user_list([("admin", 0), ("nobody", 1)])

        self.assertIs(records["admin"]["is_hidden"], True)
        self.assertIs(records["nobody"]["is_hidden"], False)
        self.assertIsNone(records["systemprofile"]["is_hidden"])

    # python -m unittest tests.hive.test_user_profile.UserProfile.test_user_profile -v
    def test_user_profile(self):
        plugin_file = os.path.join(CONF_FOLDER, "user_profile.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")

        base_output_name = "user_profile"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".user_profile.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        metadata = Metadata("test")
        parser = RegUserProfile()
        self.assertEqual("RegUserProfile", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 7
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0

            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(js["related_user"], "S-1-5-18")
                    self.assertEqual(
                        js["description"],
                        "path: %systemroot%\\system32\\config\\systemprofile",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "user_name: systemprofile",
                    )
                i += 1
            self.assertEqual(i, expected_lines)
