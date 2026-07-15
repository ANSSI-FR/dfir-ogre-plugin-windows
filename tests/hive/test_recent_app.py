import json
import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows import RegRecentApp

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


def registry_key(name: str, path: str, values: dict, children=None):
    key = Mock()
    key.name = name
    key.path = path
    key.mtime = datetime(2025, 1, 1, tzinfo=timezone.utc)
    key.value_data.side_effect = values.get
    key.sub_keys.return_value = children or []

    security = Record()
    security.add("owner_sid", Value.String("S-1-5-21-test"))
    key.security_descriptor.to_record.return_value = security
    return key


class RecentApp(TestCase):
    def test_one_record_is_emitted_per_recent_item(self):
        first_item = registry_key(
            "{22222222-2222-2222-2222-222222222222}",
            r"\HKCU\RecentApps\app\RecentItems\first",
            {
                "DisplayName": "First item",
                "Path": r"C:\evidence\first.txt",
                "Arguments": "--first",
            },
        )
        second_item = registry_key(
            "{33333333-3333-3333-3333-333333333333}",
            r"\HKCU\RecentApps\app\RecentItems\second",
            {
                "DisplayName": "Second item",
                "Path": r"C:\evidence\second.txt",
                "Arguments": "--second",
            },
        )
        recent_items = registry_key(
            "RecentItems",
            r"\HKCU\RecentApps\app\RecentItems",
            {},
            [first_item, second_item],
        )
        app_key = registry_key(
            "{11111111-1111-1111-1111-111111111111}",
            r"\HKCU\RecentApps\app",
            {"AppId": "forensic-app", "LaunchCount": 7},
        )
        app_key.sub_key.return_value = recent_items

        output = Mock()
        report = RunReport()
        RegRecentApp().parse_key(app_key, output, report)

        records = [
            json.loads(call.args[0].to_string()) for call in output.write.call_args_list
        ]
        self.assertEqual(report.last_error, None)
        self.assertEqual(len(records), 2)
        self.assertEqual(
            [record["guid_file"] for record in records],
            [
                "22222222-2222-2222-2222-222222222222",
                "33333333-3333-3333-3333-333333333333",
            ],
        )
        self.assertEqual(
            [record["display_name"] for record in records],
            ["First item", "Second item"],
        )
        self.assertEqual(
            [record["key_path"] for record in records],
            [first_item.path, second_item.path],
        )
        self.assertTrue(all(record["app_id"] == "forensic-app" for record in records))
        self.assertTrue(all(record["launch_count"] == 7 for record in records))

    # python -m unittest tests.hive.test_recent_app.RecentApp.test_recent_app -v
    def test_recent_app(self):
        plugin_file = os.path.join(CONF_FOLDER, "recent_app.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "NTUSER.dat")

        base_output_name = "recent_app"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".recent_app.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )

        metadata = Metadata("test")
        parser = RegRecentApp()
        self.assertEqual("RegRecentApp", parser.description().command)  # type: ignore

        configuration = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, configuration, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 0
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        # with open(output_file) as fp:
        #     i = 0
        #     num_field = 0
        #     line_number = 0
        #     for line in fp:
        #         js = json.loads(line)
        #         if len(js) > num_field:
        #             num_field = len(js)
        #             line_number = i
        #         i += 1
        #     self.assertEqual(i, expected_lines)
        #     print(f"largest line:{line_number + 1} num_field:{num_field}")
