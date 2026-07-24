import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import Record, RunReport, Value

from dfir_ogre_plugin_windows import RegAcMru


def registry_value(name: str, data: str):
    reg_value = Mock()
    reg_value.name.return_value = name
    reg_value.data.return_value = data
    return reg_value


def acmru_key(values):
    key = Mock()
    key.name = "5603"
    key.path = r"HKCU\Software\Microsoft\Search Assistant\ACMru\5603"
    key.mtime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    key.values.return_value = values

    security = Record()
    security.add("owner_sid", Value.String("S-1-5-21-test"))
    key.security_descriptor.to_record.return_value = security
    return key


class TestAcmru(TestCase):
    def test_only_ascii_decimal_value_names_are_accepted(self):
        for value_name in ("+0", "-0", " 0", "0_0", "\u0660"):
            with self.subTest(value_name=value_name):
                key = acmru_key([registry_value(value_name, "skip me")])
                output = Mock()
                report = RunReport()

                RegAcMru().parse_key(key, output, report)

                output.write.assert_not_called()
                self.assertIsNotNone(report.last_error)
                self.assertIn("invalid ACMru value name", report.last_error)
                self.assertIn(repr(value_name), report.last_error)

    def test_values_are_sorted_and_only_newest_has_timestamp(self):
        key = acmru_key(
            [
                registry_value("002", "third"),
                registry_value("000", "newest"),
                registry_value("001", "second"),
            ]
        )
        output = Mock()
        report = RunReport()

        RegAcMru().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertIsNone(report.last_error)
        self.assertEqual(
            [record["search_request"] for record in records],
            ["newest", "second", "third"],
        )
        self.assertEqual(
            [record["order_index"] for record in records],
            [0, 1, 2],
        )
        self.assertTrue(all(record["category"] == "5603" for record in records))
        self.assertEqual(
            records[0]["key_modif_time"],
            "2025-01-02T03:04:05.000000+00:00",
        )
        self.assertNotIn("key_modif_time", records[1])
        self.assertNotIn("key_modif_time", records[2])

    def test_invalid_value_name_is_reported_without_losing_valid_values(self):
        key = acmru_key(
            [
                registry_value("invalid", "skip me"),
                registry_value("000", "keep me"),
            ]
        )
        output = Mock()
        report = RunReport()

        RegAcMru().parse_key(key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertEqual(
            [record["search_request"] for record in records],
            ["keep me"],
        )
        self.assertIn("invalid ACMru value name", report.last_error)
        self.assertIn("invalid", report.last_error)

    def test_unexpected_category_error_does_not_suppress_later_category(self):
        failing_key = acmru_key([])
        failing_key.path = (
            r"HKCU\Software\Microsoft\Search Assistant\ACMru\corrupt"
        )
        failing_key.values.side_effect = RuntimeError("corrupt category")
        valid_key = acmru_key([registry_value("000", "keep me")])
        output = Mock()
        report = RunReport()
        parser = RegAcMru()

        try:
            parser.parse_key(failing_key, output, report)
        except RuntimeError as error:
            self.fail(f"category error escaped parse_key: {error}")
        parser.parse_key(valid_key, output, report)

        records = [
            json.loads(call.args[0].to_string())
            for call in output.write.call_args_list
        ]
        self.assertEqual(
            [record["search_request"] for record in records],
            ["keep me"],
        )
        self.assertIsNotNone(report.last_error)
        self.assertIn("corrupt category", report.last_error)
        self.assertIn(failing_key.path, report.last_error)
