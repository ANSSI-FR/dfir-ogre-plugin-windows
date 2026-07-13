from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_plugin_windows.common import (
    FRNParser,
    FileAttributesParser,
    fat_datetime_to_utc,
)


class CommonTest(TestCase):
    def test_abstract_parsers_return_empty_records_for_empty_input(self):
        self.assertTrue(FileAttributesParser().parse("", "attributes").is_empty())
        self.assertTrue(FRNParser.build("parent_").parse("", "frn").is_empty())

    def test_fat_datetime_uses_high_word_for_date_and_low_word_for_time(self):
        date_word = ((2024 - 1980) << 9) | (6 << 5) | 29
        time_word = (17 << 11) | (42 << 5) | (58 // 2)
        fat_datetime = (date_word << 16) | time_word

        self.assertEqual(
            fat_datetime_to_utc(fat_datetime),
            datetime(2024, 6, 29, 17, 42, 58, tzinfo=timezone.utc),
        )
