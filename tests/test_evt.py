import json
import os
import unittest
from unittest.mock import Mock

import pyevt

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import WinEvt
from dfir_ogre_plugin_windows.evt import _get_event_data

# The test suite defines a couple of handy constants that point to temporary
# directories and the location of the configuration files.
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "evt")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestWinEvt(unittest.TestCase):
    """Integration test for the ``WinEvt`` plugin (EVT‑format)."""

    # python -m unittest tests.test_evt.TestWinEvt.test_evt_file -v
    def test_evt_file(self):
        plugin_file = os.path.join(CONF_FOLDER, "evt.xml")
        input_file = os.path.join(DATA_FOLDER, "evt", "SysEvent.Evt")

        base_output_name = "sys_event"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.evt.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_cfg = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=False,           # no extra options
        )
        run_cfg = RunConfiguration([output_cfg])

        metadata = Metadata("test")
        parser = WinEvt()
        self.assertEqual("WinEvt", parser.description().command) # type: ignore

        report = parser.parse(input_file, plugin_file, run_cfg, metadata)

        self.assertIsNone(report.last_error)
        self.assertEqual(report.num_errors, 0)


        expected_lines = 6611
        output_report = report.output_reports[0]
        file_report = output_report.file_reports[0]

        self.assertEqual(file_report.num_lines, expected_lines)
        self.assertEqual(file_report.file_name, output_file)

        with open(output_file, "r", encoding="utf-8") as fp:
            i =0
            for line in fp:
                js = json.loads(line)
                if i == 2420:
                    self.assertEqual(
                        js["description"],
                        "Service Control Manager:7036",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "[Google Update Service (gupdate), running]",
                    )
                    self.assertEqual(js["data"]["record_number"], 3795)
                    self.assertEqual(
                        js["data"]["creation_time"],
                        "2011-09-13T08:43:00.000000+00:00",
                    )
                    self.assertEqual(
                        js["data"]["written_time"],
                        "2011-09-13T08:43:00.000000+00:00",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
        # If we reach this point, the EVT parser behaved as expected.


class TestWinEvtTimestamps(unittest.TestCase):
    def test_creation_and_written_timestamps_are_independent(self):
        creation_time = "2024-01-02T03:04:05.000000+00:00"
        written_time = "2024-01-02T03:05:05.000000+00:00"
        cases = (
            ("both_valid", 1704164645, 1704164705, creation_time, written_time),
            ("written_missing", 1704164645, AttributeError(), creation_time, None),
            ("written_overflow", 1704164645, OverflowError(), creation_time, None),
            ("creation_missing", AttributeError(), 1704164705, None, written_time),
            ("creation_overflow", OverflowError(), 1704164705, None, written_time),
            ("both_missing", AttributeError(), AttributeError(), None, None),
            ("both_overflow", OverflowError(), OverflowError(), None, None),
        )

        for label, creation, written, expected_creation, expected_written in cases:
            with self.subTest(label=label):
                # Only the native reader is replaced; field extraction, Record,
                # Value and JSON serialization use the production implementations.
                native_record = Mock(spec=pyevt.record)
                native_record.identifier = 42
                native_record.event_identifier = 7036
                native_record.offset = 48
                native_record.event_type = 4
                native_record.event_category = 0
                native_record.source_name = "Service Control Manager"
                native_record.computer_name = "HOST"
                native_record.user_security_identifier = None
                native_record.strings = ["service", "running"]
                for accessor, result in (
                    (native_record.get_creation_time_as_integer, creation),
                    (native_record.get_written_time_as_integer, written),
                ):
                    if isinstance(result, Exception):
                        accessor.side_effect = result
                    else:
                        accessor.return_value = result

                record = json.loads(_get_event_data(native_record).to_string())

                self.assertEqual(record["creation_time"], expected_creation)
                self.assertIn("written_time", record)
                self.assertEqual(record["written_time"], expected_written)
