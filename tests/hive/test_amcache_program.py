import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegAmCacheProgram

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AmCacheProgram(TestCase):
    # python -m unittest tests.hive.test_amcache_program.AmCacheProgram.test_v8 -v
    def test_v8(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_program.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v8.hve")

        base_output_name = "am_cache_program_v8"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_program.jsonl"
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
        parser = RegAmCacheProgram()
        self.assertEqual("RegAmCacheProgram", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 10
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
                        "S-1-5-18",
                    )

                    self.assertEqual(
                        js["description"],
                        "name: Wireshark 2.6.5 32-bit",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_amcache_program.AmCacheProgram.test_v1607 -v
    def test_v1607(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_program.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1607.hve")

        base_output_name = "am_cache_program_v1607"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_program.jsonl"
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
        parser = RegAmCacheProgram()
        self.assertEqual("RegAmCacheProgram", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 128
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 6:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",
                    )
                    self.assertEqual(
                        js["description"],
                        "name: WinPcap 4.1.3",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "version: 4.1.0.2980 - publisher: Riverbed Technology, Inc. - install_dir: [C:\\Program Files (x86)\\WinPcap] - key_path: AmCache\\Root\\Programs\\00008031ba6c55d6e393bb7b7081898b45020000ffff",
                    )
                    self.assertEqual(
                        js["data"]["install_dir"],
                        ["C:\\Program Files (x86)\\WinPcap"],
                    )
                if i == 26:
                    self.assertEqual(
                        js["data"]["msi_package_code"],
                        "{032c2206-4938-4565-bebf-bad670550a1f}",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_amcache_program.AmCacheProgram.test_v1709 -v
    def test_v1709(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_program.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1709.hve")

        base_output_name = "am_cache_program_v1709"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_program.jsonl"
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
        parser = RegAmCacheProgram()
        self.assertEqual("RegAmCacheProgram", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 79
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
                        "S-1-5-18",
                    )
                    self.assertEqual(
                        js["description"],
                        "name: Microsoft.CredDialogHost",
                    )

                    self.assertEqual(
                        js["additional_description"],
                        "version: 10.0.16299.15 - publisher: CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US - install_dir: C:\\Windows\\SystemApps\\microsoft.creddialoghost_cw5n1h2txyewy - key_path: AmCache\\Root\\InventoryApplication\\000001d8af836d5ce5b71a9cbcdc40b7427d00000904",
                    )
                    self.assertEqual(
                        js["data"]["install_dir"],
                        "C:\\Windows\\SystemApps\\microsoft.creddialoghost_cw5n1h2txyewy",
                    )
                if i == 25:
                    self.assertEqual(
                        js["data"]["msi_product_code"],
                        "{7fed75a1-600c-394b-8376-712e2a8861f2}",
                    )
                    self.assertEqual(
                        js["data"]["msi_package_code"],
                        "{93d97caa-b398-4f6a-8898-9aaa305c718c}",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
