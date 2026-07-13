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


class AmcacheDriverTest(TestCase):

    # python -m unittest tests.amcache_files.test_amcache_driver.AmcacheDriverTest.test_driver_amcache -v
    def test_driver_amcache(self):

        plugin_file = os.path.join(CONF_FOLDER, "amcache_driver_xml.xml")

        input_file = os.path.join(
            DATA_FOLDER, "aeinv", "AEINV_AMI_WER_{32781662-3DBD-4055-A94B-4CE805656B08}_20190102_131746.xml"
        )

        base_output_name = "amcache_driver"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.amcache_driver_xml.jsonl"
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

        self.assertEqual(file_report.num_lines,288)

        self.assertEqual(file_report.file_name, output_file)
        with open(output_file) as fp:
            first_line = fp.readline().strip()
            jsoned = json.loads(first_line)

            self.assertIn("sha1", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("type", jsoned)
            self.assertIn("version", jsoned)
            self.assertIn("compilation_date", jsoned)
            self.assertIn("checksum", jsoned)
            self.assertIn("image_size", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("company", jsoned)
            self.assertIn("product", jsoned)
            self.assertIn("product_version", jsoned)
            self.assertIn("wdf_version", jsoned)

            self.assertEqual(
                jsoned["name"],
                "1394ohci.sys",
            )

            self.assertEqual(
                jsoned["image_size"],
                188416,
            )

            self.assertEqual(
                jsoned["compilation_date"],
                "2012-07-26T02:33:52.000000+00:00",
            )
