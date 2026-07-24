import json
import os
import struct
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

from dfir_ogre_plugin_windows import RegExplorerSearchHistory
from dfir_ogre_plugin_windows.registry.explorer_search_history import (
    decode_word_wheel_value,
    parse_mru_list_ex,
)

from . import CONF_FOLDER, DATA_FOLDER, TEMP_FOLDER


def word_wheel_key(values: dict[str, object]):
    key = Mock()
    key.path = (
        r"HKCU\Software\Microsoft\Windows\CurrentVersion"
        r"\Explorer\WordWheelQuery"
    )
    key.mtime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    key.value_data.side_effect = values.get

    security = Record()
    security.add("owner_sid", Value.String("S-1-5-21-test"))
    key.security_descriptor.to_record.return_value = security
    return key


class ExplorerSearchHistoryTest(TestCase):
    def test_decoders_reject_non_binary_and_odd_length_values(self):
        with self.assertRaisesRegex(ValueError, "MRUListEx is not binary"):
            parse_mru_list_ex("not bytes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "value is not binary"):
            decode_word_wheel_value("not bytes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "value length 1 is odd"):
            decode_word_wheel_value(b"\x00")

    def test_decoder_strips_nuls_without_stripping_whitespace(self):
        encoded = "query  \x00".encode("utf-16-le")

        self.assertEqual(decode_word_wheel_value(encoded), "query  ")

    def test_public_hive_is_emitted_in_mru_list_order(self):
        plugin_file = os.path.join(CONF_FOLDER, "explorer_search_history.xml")
        input_file = os.path.join(
            DATA_FOLDER,
            "hive",
            "NTUSER_WORD_WHEEL_QUERY.dat",
        )
        output_file = os.path.join(
            TEMP_FOLDER,
            "word_wheel_public.explorer_search_history.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            "word_wheel_public",
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )
        report = RegExplorerSearchHistory().parse(
            input_file,
            plugin_file,
            RunConfiguration([output_config]),
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(
            report.output_reports[0].file_reports[0].num_lines,
            2,
        )
        with open(output_file, encoding="utf-8") as output:
            records = [json.loads(line) for line in output]

        self.assertEqual(
            [record["search_request"] for record in records],
            ["rar.exe", "hyth"],
        )
        self.assertEqual(
            [record["order_index"] for record in records],
            [0, 1],
        )
        self.assertEqual(
            [record["value_index"] for record in records],
            [1, 0],
        )
        self.assertEqual(
            records[0]["key_modif_time"],
            "2012-04-06T18:44:16.075674+00:00",
        )
        self.assertIsNone(records[1]["key_modif_time"])

    def test_missing_mru_list_is_artifact_absence(self):
        key = word_wheel_key({})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIsNone(report.last_error)

    def test_malformed_mru_list_is_reported_without_output(self):
        key = word_wheel_key({"MRUListEx": b"\x01\x00"})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIsNotNone(report.last_error)
        self.assertIn("MRUListEx length", report.last_error)

    def test_unterminated_mru_list_is_reported_without_output(self):
        key = word_wheel_key({"MRUListEx": struct.pack("<I", 1)})
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIsNotNone(report.last_error)
        self.assertIn("MRUListEx has no terminator", report.last_error)

    def test_missing_reference_is_reported_and_later_value_is_kept(self):
        key = word_wheel_key(
            {
                "MRUListEx": struct.pack("<III", 2, 1, 0xFFFFFFFF),
                "1": "valid".encode("utf-16-le") + b"\x00\x00",
            }
        )
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertEqual(
            [record["search_request"] for record in records],
            ["valid"],
        )
        self.assertEqual(records[0]["order_index"], 1)
        self.assertNotIn("key_modif_time", records[0])
        self.assertIn("missing WordWheelQuery value 2", report.last_error)

    def test_invalid_utf16_value_is_reported(self):
        key = word_wheel_key(
            {
                "MRUListEx": struct.pack("<II", 0, 0xFFFFFFFF),
                "0": b"\x00\xd8",
            }
        )
        output = Mock()
        report = RunReport()

        RegExplorerSearchHistory().parse_key(key, output, report)

        output.write.assert_not_called()
        self.assertIsNotNone(report.last_error)
        self.assertIn("invalid UTF-16LE value 0", report.last_error)
