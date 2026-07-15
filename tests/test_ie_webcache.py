import json
import os
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import IeWebCache
from dfir_ogre_plugin_windows.ie_webcache import parse_response_properties

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "ie_webcache")
os.makedirs(TEMP_FOLDER, exist_ok=True)
DATE_FIELDS = {
    "sync_date",
    "creation_date",
    "expiry_date",
    "modified_date",
    "accessed_date",
    "post_check_date",
}


class TestIeWebCache(TestCase):
    """Validate the Webcache (IE WebCacheV01.dat) parser."""

    def test_malformed_response_properties_are_reported(self):
        properties, errors = parse_response_properties(b"\x02\x00\x00\x00")

        self.assertEqual(properties, [])
        self.assertEqual(
            errors,
            ["store 0: invalid store size 2 at offset 0"],
        )

    def test_timestamp_fields_match_date_schema(self):
        column_names = [
            "SyncTime",
            "CreationTime",
            "ExpiryTime",
            "ModifiedTime",
            "AccessedTime",
            "PostCheckTime",
        ]
        raw_record = Mock()
        raw_record.get_number_of_values.return_value = len(column_names)
        raw_record.get_column_name.side_effect = column_names.__getitem__

        parser = IeWebCache()
        parser._get_value_data = Mock(return_value=132537600000000000)
        decoded = json.loads(parser._parse_record(raw_record).to_string())

        self.assertTrue(DATE_FIELDS.issubset(decoded))
        self.assertTrue(all(not field.endswith("_time") for field in decoded))

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
            with_timeline=True,
            include_empty=True,
            timeline_include_undated=True,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = IeWebCache()
        # sanity‑check that the plugin reports the correct command name
        self.assertEqual("IeWebCache", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error, "Parser reported an unexpected error")
        self.assertEqual(
            report.output_reports[0].file_reports[0].num_lines,
            92,
        )
        self.assertTrue(
            report.output_reports[0].file_reports[0].timeline_include_undated
        )

        output_path = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(output_path, output_file, "Output path mismatch")
        self.assertTrue(os.path.isfile(output_path), "Output file was not created")

        with open(output_path, "r", encoding="utf-8") as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), 92)
        target_url = "Visited: test@http://code.google.com/p/libyal/wiki/Overview"
        target_records = [
            record for record in records if record["data"]["url"] == target_url
        ]
        self.assertGreater(len(target_records), 0)
        data = target_records[0]["data"]
        self.assertEqual(
            data["url"],
            target_url,
        )

        for expected_key in ("url", "type", "access_count"):
            self.assertIn(expected_key, data)

        self.assertTrue(DATE_FIELDS.issubset(data))
        self.assertEqual(data["accessed_date"], "2014-05-12T07:31:06.125292+00:00")
        self.assertNotIn("accessed_time", data)
        self.assertNotIn("response_headers", data)

        response_properties = data["response_properties"]
        self.assertEqual(len(response_properties), 15)
        self.assertEqual(
            {property_data["store_index"] for property_data in response_properties},
            {0, 1},
        )
        self.assertTrue(
            all(
                isinstance(property_data["value"], str)
                for property_data in response_properties
            )
        )
        self.assertTrue(data["response_properties_raw"].startswith("0xe7010000"))
        self.assertIsNone(data["response_properties_parse_error"])

        properties_by_id = {
            property_data["id"]: property_data for property_data in response_properties
        }
        self.assertEqual(
            properties_by_id[16],
            {
                "store_index": 0,
                "storage_index": 0,
                "format_id": "000214a1-0000-0000-c000-000000000046",
                "id": 16,
                "name": "PID_INTSITE_TITLE",
                "value_type": "VT_LPWSTR",
                "value": (
                    "Overview - libyal - Overview of libraries - Yet another "
                    "library library (and tools) - Google Project Hosting"
                ),
            },
        )
        self.assertEqual(properties_by_id[6]["value"], "1")
        self.assertEqual(
            properties_by_id[21]["value"],
            "http://www.gstatic.com/codesite/ph/images/phosting.ico",
        )
        self.assertTrue(
            any(
                record["timestamp"] == record["data"]["accessed_date"]
                and "Accessed Date" in record["timestamp_meaning"]
                for record in target_records
            )
        )
        self.assertTrue(
            any(
                record["timestamp"] == record["data"]["expiry_date"]
                and record["timestamp_meaning"] == "Expiry Date"
                for record in target_records
            )
        )

        urls = {record["data"]["url"] for record in records}
        self.assertIn(
            "Visited: test@http://ct1.addthis.com/static/r07/sh157.html",
            urls,
        )
