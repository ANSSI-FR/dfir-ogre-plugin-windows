import json
import os
import dateutil.parser
from datetime import timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from unittest import TestCase

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OutputConfiguration,
    RunConfiguration,
)


from dfir_ogre_plugin_windows import Lnk, LnkBatched
from dfir_ogre_plugin_windows.lnk import (
    group_lnk_inputs,
    normalize_lnk_fat_timestamps,
)

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "lnk")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestLnkFatTimestamps(TestCase):
    def test_groups_lnk_and_system_hives_by_vss(self):
        run_config = RunConfiguration(
            [OutputConfiguration("unused", TEMP_FOLDER, with_timeline=False)]
        )

        def entry(file: str, original_filename: str, vss: str) -> BatchEntry:
            metadata = Metadata("test")
            metadata.original_filename = original_filename
            metadata.vss = vss
            return BatchEntry(file, run_config, metadata)

        grouped = group_lnk_inputs(
            [
                entry("system-2", "C:\\Windows\\System32\\config\\SYSTEM", "vss-2"),
                entry("one", "C:\\Users\\one\\one.lnk", "vss-1"),
                entry("system-1", "C:\\Windows\\System32\\config\\SYSTEM", "vss-1"),
                entry("system-link", "C:\\Users\\one\\SYSTEM.lnk", "vss-1"),
                entry("two", "C:\\Users\\two\\two.lnk", "vss-2"),
            ]
        )

        self.assertEqual(
            [entry.file for entry in grouped["vss-1"].lnk_entries],
            ["one", "system-link"],
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-1"].system_entries],
            ["system-1"],
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-2"].lnk_entries], ["two"]
        )
        self.assertEqual(
            [entry.file for entry in grouped["vss-2"].system_entries],
            ["system-2"],
        )

    def test_normalizes_only_target_item_fat_timestamps(self):
        jumplist = {
            "lnk": [
                {
                    "header": {"modification_time": "2024-06-29T17:42:58+00:00"},
                    "target": {
                        "items": [{"modification_time": "2024-06-29T17:42:58+00:00"}]
                    },
                }
            ]
        }

        count = normalize_lnk_fat_timestamps(jumplist, ZoneInfo("Europe/Paris"))

        self.assertEqual(count, 1)
        self.assertEqual(
            jumplist["lnk"][0]["target"]["items"][0]["modification_time"],
            "2024-06-29T15:42:58+00:00",
        )
        self.assertEqual(
            jumplist["lnk"][0]["header"]["modification_time"],
            "2024-06-29T17:42:58+00:00",
        )

        without_timezone = {
            "lnk": [
                {
                    "target": {
                        "items": [{"modification_time": "2024-06-29T17:42:58+00:00"}]
                    }
                }
            ]
        }
        normalize_lnk_fat_timestamps(without_timezone, None)
        self.assertIsNone(
            without_timezone["lnk"][0]["target"]["items"][0]["modification_time"]
        )

    def test_batched_lnk_uses_matching_system_timezone(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        lnk_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        system_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat")
        base_output_name = "lnk_fat_timestamp"
        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        lnk_metadata = Metadata("test")
        lnk_metadata.vss = "test_vss"
        lnk_metadata.original_filename = "C:\\Users\\test\\desktop.lnk"
        system_metadata = Metadata("test")
        system_metadata.vss = "test_vss"
        system_metadata.original_filename = "C:\\Windows\\System32\\config\\SYSTEM"
        entries = [
            BatchEntry(system_file, run_config, system_metadata),
            BatchEntry(lnk_file, run_config, lnk_metadata),
        ]
        parsed_lnk = {
            "status": "success",
            "lnk": [
                {
                    "status": "success",
                    "header": {"modification_time": "2024-06-29T17:42:58+00:00"},
                    "target": {
                        "items": [
                            {
                                "primary_name": "target.txt",
                                "modification_time": "2024-06-29T17:42:58+00:00",
                            }
                        ]
                    },
                }
            ],
        }

        with patch(
            "dfir_ogre_plugin_windows.lnk.parse_jumplist",
            return_value=parsed_lnk,
        ) as parse_mock:
            report = LnkBatched().parse(entries, plugin_file)

        self.assertEqual(report.last_error, None)
        parse_mock.assert_called_once()
        self.assertEqual(
            parsed_lnk["lnk"][0]["target"]["items"][0]["modification_time"],
            "2024-06-29T15:42:58+00:00",
        )
        with open(output_file) as fp:
            record = json.loads(fp.readline())

        self.assertEqual(
            record["header"]["modification_time"],
            "2024-06-29T17:42:58.000000+00:00",
        )

    def test_batched_lnk_without_system_reports_and_uses_utc_fallback(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        lnk_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_without_system"
        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "missing-system"
        metadata.original_filename = r"C:\Users\test\desktop.lnk"
        parsed_lnk = {
            "status": "success",
            "lnk": [
                {
                    "status": "success",
                    "header": {
                        "modification_time": "2024-06-29T17:42:58+00:00"
                    },
                    "target": {
                        "items": [
                            {
                                "primary_name": "target.txt",
                                "modification_time": "2024-06-29T17:42:58+00:00",
                            }
                        ]
                    },
                }
            ],
        }

        with self.assertLogs(
            "dfir_ogre_plugin_windows.system_timezone",
            level="WARNING",
        ) as logs, patch(
            "dfir_ogre_plugin_windows.lnk.parse_jumplist",
            return_value=parsed_lnk,
        ):
            report = LnkBatched().parse(
                [BatchEntry(lnk_file, run_config, metadata)],
                plugin_file,
            )

        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'missing-system'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 1)
        self.assertEqual(
            parsed_lnk["lnk"][0]["target"]["items"][0]["modification_time"],
            "2024-06-29T17:42:58+00:00",
        )


class TestLnk(TestCase):
    # python -m unittest tests.test_lnk.TestLnk.test_lnk -v
    def test_lnk(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        input_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_desktop"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=False,
        )

        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = Lnk()
        self.assertEqual("Lnk", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_tuples = 4
        self.assertEqual(lines, expected_tuples)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        js["description"], "local_base_path: C:\\Users\\heznik\\Desktop"
                    )
                    # test lower case conversion
                    self.assertEqual(
                        js["data"]["header"]["guid"],
                        "00021401-0000-0000-c000-000000000046",
                    )

                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_volume_identifier"
                        ],
                        "cb368e46-431e-4e6d-b3a9-7cbb6dd6a31f",
                    )

                    # test FRNHex python mapping
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_file_frn"
                        ],
                        "0x000000000000F5B0",
                    )

                    # test FRNSplit extension mapping
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "birth_droid_file_record_number"
                        ],
                        62896,
                    )

                    # test FRNSplit extension mapping
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_file_record_number"
                        ],
                        62896,
                    )
                i += 1
            self.assertEqual(i, expected_tuples)

    # python -m unittest tests.test_lnk.TestLnk.test_lnk_metadata -v
    def test_lnk_metadata(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        input_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_desktop_with_date_metadata"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=False,
        )

        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        metadata.creation_date = dateutil.parser.isoparse(
            "2023-04-15T12:34:56Z"
        ).astimezone(timezone.utc)
        metadata.modif_date = dateutil.parser.isoparse(
            "2024-02-15T14:01:32Z"
        ).astimezone(timezone.utc)
        parser = Lnk()
        self.assertEqual("Lnk", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_tuples = 6
        self.assertEqual(lines, expected_tuples)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        js["description"], "local_base_path: C:\\Users\\heznik\\Desktop"
                    )
                    # test lower case conversion
                    self.assertEqual(
                        js["data"]["header"]["guid"],
                        "00021401-0000-0000-c000-000000000046",
                    )

                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_volume_identifier"
                        ],
                        "cb368e46-431e-4e6d-b3a9-7cbb6dd6a31f",
                    )

                    # test FRNHex
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_file_frn"
                        ],
                        "0x000000000000F5B0",
                    )

                    # test FRNSplit extension mapping
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "birth_droid_file_record_number"
                        ],
                        62896,
                    )

                    # test FRNSplit extension mapping
                    self.assertEqual(
                        js["data"]["extra"]["distributed_link_tracker"][
                            "droid_file_record_number"
                        ],
                        62896,
                    )
                i += 1
            self.assertEqual(i, expected_tuples)

    # python -m unittest tests.test_lnk.TestLnk.test_lnk_include_empty -v
    def test_lnk_include_empty(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        input_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_include_empty"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )

        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        metadata.creation_date = dateutil.parser.isoparse(
            "2023-04-15T12:34:56Z"
        ).astimezone(timezone.utc)
        metadata.modif_date = dateutil.parser.isoparse(
            "2024-02-15T14:01:32Z"
        ).astimezone(timezone.utc)

        parser = Lnk()
        self.assertEqual("Lnk", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_tuples = 1
        self.assertEqual(lines, expected_tuples)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)

                self.assertEqual(
                    "common_path_suffix" in js["link_info"],
                    True,
                )

                self.assertEqual(
                    js["link_info"]["location"],
                    "Local",
                )

                i += 1
            self.assertEqual(i, expected_tuples)

    # python -m unittest tests.test_lnk.TestLnk.test_lnk_remove_empty -v
    def test_lnk_remove_empty(self):
        plugin_file = os.path.join(CONF_FOLDER, "lnk_batched.xml")
        input_file = os.path.join(DATA_FOLDER, "lnk", "desktop.lnk.data")
        base_output_name = "lnk_remove_empty"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".lnk.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=False,
        )

        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        metadata.creation_date = dateutil.parser.isoparse(
            "2023-04-15T12:34:56Z"
        ).astimezone(timezone.utc)
        metadata.modif_date = dateutil.parser.isoparse(
            "2024-02-15T14:01:32Z"
        ).astimezone(timezone.utc)

        parser = Lnk()
        self.assertEqual("Lnk", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        expected_tuples = 1
        self.assertEqual(lines, expected_tuples)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)

                self.assertEqual(
                    "common_path_suffix" in js["link_info"],
                    False,
                )

                self.assertEqual(
                    js["link_info"]["location"],
                    "Local",
                )

                i += 1
            self.assertEqual(i, expected_tuples)
