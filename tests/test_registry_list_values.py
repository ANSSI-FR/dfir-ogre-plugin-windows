import json
from unittest import TestCase

from dfir_ogre_common import Record

from dfir_ogre_plugin_windows.common import add_list, value


class RegistryListValuesTest(TestCase):
    def test_value_preserves_list_items_and_nested_types(self):
        record = Record()
        record.add("data", value([r"C:\Windows\file", True, 7, 1.5, None, ["RPCSS"]]))

        self.assertEqual(
            json.loads(record.to_string()),
            {"data": [r"C:\Windows\file", True, 7, 1.5, None, ["RPCSS"]]},
        )

    def test_add_list_normalizes_missing_empty_single_and_multiple_values(self):
        cases = (
            (None, {}),
            ([], {"data": []}),
            ("RPCSS", {"data": ["RPCSS"]}),
            ("", {"data": [""]}),
            (["RPCSS", "HTTP"], {"data": ["RPCSS", "HTTP"]}),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                record = Record()
                add_list(record, "data", raw)
                self.assertEqual(json.loads(record.to_string()), expected)
