import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegAmCacheFile

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AmCacheFile(TestCase):
    # python -m unittest tests.hive.test_amcache_file.AmCacheFile.test_v8 -v
    def test_v8(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_files.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v8.hve")

        base_output_name = "am_cache_file_v8"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_file.jsonl"
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
        parser = RegAmCacheFile()
        self.assertEqual("RegAmCacheFile", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 388
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
                        "path: c:\\program files\\wireshark\\WinPcap_4_1_3.exe",
                    )
                    self.assertEqual(
                        js["data"]["volume_guid"],
                        "b528e029-0e73-11e9-af9b-806e6f6e6963",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_amcache_file.AmCacheFile.test_v1607 -v
    def test_v1607(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_files.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1607.hve")

        base_output_name = "am_cache_file_v1607"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_file.jsonl"
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
        parser = RegAmCacheFile()
        self.assertEqual("RegAmCacheFile", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 610
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
                        "path: d:\\vboxwindowsadditions-amd64.exe",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "size: 16443832 - program_id: 000612b2c6f35b22970daae0d8d2eeddf56f00000000 - sha1: d14df5ea9601ca2981074516bda8f5226a5c735b - key_path: AmCache\\Root\\File\\ba949c59-1a7f-11e9-bc6d-806e6f6e6963\\019c",
                    )
                    self.assertEqual(
                        js["data"]["file_id"],
                        "0000d14df5ea9601ca2981074516bda8f5226a5c735b",
                    )
                    self.assertEqual(
                        js["data"]["sha1"],
                        "d14df5ea9601ca2981074516bda8f5226a5c735b",
                    )
                    self.assertEqual(
                        js["data"]["volume_guid"],
                        "ba949c59-1a7f-11e9-bc6d-806e6f6e6963",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_amcache_file.AmCacheFile.test_v1709 -v
    def test_v1709(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_files.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1709.hve")

        base_output_name = "am_cache_file_v1709"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_file.jsonl"
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
        parser = RegAmCacheFile()
        self.assertEqual("RegAmCacheFile", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 220
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
                        "path: c:\\program files\\sleuthkit-4.6.6-win32\\bin\\blkcalc.exe",
                    )

                    self.assertEqual(
                        js["additional_description"],
                        "size: 525824 - program_id: 0006e6ae12df2ab4e561a3d2f9480c3a508d0000ffff - sha1: 6dfffe9d80ccafa6e88cce582cf1716fd6d08094 - key_path: AmCache\\Root\\InventoryApplicationFile\\blkcalc.exe|4d759318",
                    )
                    self.assertEqual(
                        js["data"]["file_id"],
                        "00006dfffe9d80ccafa6e88cce582cf1716fd6d08094",
                    )
                    self.assertEqual(
                        js["data"]["sha1"],
                        "6dfffe9d80ccafa6e88cce582cf1716fd6d08094",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
