import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import IeWebCache
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "ie_webcache")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestIeWebCache(TestCase):
    """Validate the Webcache (IE WebCacheV01.dat) parser."""

    # python -m unittest tests.test_ie_webcache.TestIeWebCache.test_parse -v
    def test_parse(self):
        plugin_file = os.path.join(CONF_FOLDER, "ie_webcache.xml")
        input_file = os.path.join(DATA_FOLDER, "iewebcache", "WebCacheV01.dat")

        base_output_name = "ie_webcache"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.ie_webcache_history.jsonl"
        )
        # Remove any stale output from a previous run
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=True,           # no extra options
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = IeWebCache()
        # sanity‑check that the plugin reports the correct command name
        self.assertEqual("IeWebCache", parser.description().command)   # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error, "Parser reported an unexpected error")
        self.assertEqual(
            report.output_reports[0].file_reports[0].num_lines,
            17,
        )

        output_path = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(output_path, output_file, "Output path mismatch")
        self.assertTrue(os.path.isfile(output_path), "Output file was not created")

        with open(output_path, "r", encoding="utf-8") as fp:
            first_line = fp.readline().strip()
            self.assertTrue(first_line, "Output file is empty")

            record_json = json.loads(first_line)

            result= record_json["url"]
            self.assertEqual(result,"Visited: test@http://code.google.com/p/libyal/wiki/Overview")

            # Core fields that the plugin always attempts to add
            for expected_key in ("url", "type", "access_count"):
                self.assertIn(
                    expected_key,
                    record_json,
                    f"Missing expected field '{expected_key}' in the first record",
                )
