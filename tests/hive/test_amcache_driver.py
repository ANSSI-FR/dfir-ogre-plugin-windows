import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegAmCacheDriver

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AmCacheDriver(TestCase):
    # python -m unittest tests.hive.test_amcache_driver.AmCacheDriver.test_v1607 -v
    def test_v1607(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_driver.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1607.hve")

        base_output_name = "am_cache_driver_v1607"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_driver.jsonl"
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
        parser = RegAmCacheDriver()
        self.assertEqual("RegAmCacheDriver", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 622
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
                        "name: vmgencounter.sys",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "service: gencounter - sha1: 01703a19605e9a190a1d3960e0865dc23046aa16 - key_path: AmCache\\Root\\InventoryDriverBinary\\000001703a19605e9a190a1d3960e0865dc23046aa16",
                    )
                    self.assertEqual(
                        js["data"]["driver_id"],
                        "000001703a19605e9a190a1d3960e0865dc23046aa16",
                    )
                    self.assertEqual(
                        js["data"]["sha1"],
                        "01703a19605e9a190a1d3960e0865dc23046aa16",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_amcache_driver.AmCacheDriver.test_v1709 -v
    def test_v1709(self):
        plugin_file = os.path.join(CONF_FOLDER, "amcache_driver.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "amcache_v1709.hve")

        base_output_name = "am_cache_driver_v1709"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".amcache_driver.jsonl"
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
        parser = RegAmCacheDriver()
        self.assertEqual("RegAmCacheDriver", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 628
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
                        "name: mpksl541f4c03.sys",
                    )

                    self.assertEqual(
                        js["additional_description"],
                        "path: \\??\\c:\\programdata\\microsoft\\windows defender\\definition updates\\default\\mpksl541f4c03.sys - service: mpksl541f4c03 - sha1: 33ba0027ab12e6d05d1580bdea961f533f06131f - key_path: AmCache\\Root\\InventoryDriverBinary\\/??/c:/programdata/microsoft/windows defender/definition updates/default/mpksl541f4c03.sys",
                    )
                    self.assertEqual(
                        js["data"]["driver_id"],
                        "000033ba0027ab12e6d05d1580bdea961f533f06131f",
                    )
                    self.assertEqual(
                        js["data"]["sha1"],
                        "33ba0027ab12e6d05d1580bdea961f533f06131f",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
