import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import XML

# Re‑use the temporary folder helpers used throughout the test suite.
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "amcache")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AmcacheInstallerTest(TestCase):

    # python -m unittest tests.amcache_files.test_amcache_installer.AmcacheInstallerTest.test_installer_amcache -v
    def test_installer_amcache(self):

        plugin_file = os.path.join(CONF_FOLDER, "amcache_installer_xml.xml")

        input_file = os.path.join(
            DATA_FOLDER, "aeinv", "AEINV_AMI_WER_{32781662-3DBD-4055-A94B-4CE805656B08}_20190102_131746.xml"
        )

        base_output_name = "amcache_installer"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.amcache_installer_xml.jsonl"
        )
        # Ensure a clean run.
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=True,
        )

        metadata = Metadata("test")
        parser = XML()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)

        file_report = report.output_reports[0].file_reports[0]

        self.assertEqual(file_report.num_lines,1)

        self.assertEqual(file_report.file_name, output_file)
        with open(output_file) as fp:
            first_line = fp.readline().strip()
            jsoned = json.loads(first_line)

            self.assertIn("name", jsoned)
            self.assertIn("complete", jsoned)
            self.assertIn("program_id", jsoned)
            self.assertIn("created_arp_entries", jsoned)
            self.assertIn("start_time", jsoned)
            self.assertIn("stop_time", jsoned)
            self.assertIn("short_name", jsoned)
            self.assertIn("is_os_component", jsoned)
            self.assertIn("size", jsoned)
            self.assertIn("pe_header_hash", jsoned)
            self.assertIn("image_size", jsoned)
            self.assertIn("pe_checksum", jsoned)
            self.assertIn("link_date", jsoned)
            self.assertIn("linker_version", jsoned)
            self.assertIn("bin_file_version", jsoned)
            self.assertIn("bin_product_version", jsoned)
            self.assertIn("binary_type", jsoned)
            self.assertIn("created", jsoned)
            self.assertIn("modified", jsoned)
            self.assertIn("version_language", jsoned)
            self.assertIn("sha1", jsoned)
            self.assertIn("sig_publisher_name", jsoned)
            self.assertIn("file_version", jsoned)
            self.assertIn("company", jsoned)
            self.assertIn("file_description", jsoned)
            self.assertIn("product", jsoned)
            self.assertIn("long_path_hash", jsoned)

            self.assertEqual(
                jsoned["name"],
                "VBoxWindowsAdditions-x86.exe",
            )
            self.assertEqual(
                jsoned["size"],
                10084424,
            )
            self.assertEqual(
                jsoned["image_size"],
                348160,
            )

            self.assertEqual(
                jsoned["created"],
                "2018-05-09T11:25:21.000000+00:00",
            )
