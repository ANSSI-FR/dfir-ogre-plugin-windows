import struct
from datetime import datetime, timezone
from unittest import TestCase

from dfir_ogre_plugin_windows.registry.app_compat_cache_formats import (
    AppCompatCacheParseError,
    UnsupportedAppCompatCacheFormat,
    parse_appcompat_cache,
)


FILETIME = 132224078450000000
EXPECTED_DATE = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def variable_entry(marker: bytes, body: bytes) -> bytes:
    return marker + bytes(4) + struct.pack("<I", len(body)) + body


def windows_10_entry(
    path: str,
    filetime: int = FILETIME,
    data: bytes = b"",
) -> bytes:
    encoded_path = path.encode("utf-16-le")
    body = (
        struct.pack("<H", len(encoded_path))
        + encoded_path
        + struct.pack("<QI", filetime, len(data))
        + data
    )
    return variable_entry(b"10ts", body)


def windows_10_cache(
    entries: list[bytes],
    header_size: int = 52,
    declared_count: int | None = None,
) -> bytes:
    header = bytearray(header_size)
    struct.pack_into("<I", header, 0, header_size)
    count_offset = 36 if header_size == 48 else 40
    struct.pack_into(
        "<I",
        header,
        count_offset,
        len(entries) if declared_count is None else declared_count,
    )
    return bytes(header) + b"".join(entries)


class AppCompatCacheFormats(TestCase):
    def test_windows_10_headers(self):
        for header_size in (48, 52):
            with self.subTest(header_size=header_size):
                result = parse_appcompat_cache(
                    windows_10_cache(
                        [windows_10_entry(r"C:\Windows\System32\cmd.exe")],
                        header_size=header_size,
                    )
                )

                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(
                    result.entries[0].path,
                    r"C:\Windows\System32\cmd.exe",
                )
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertIsNone(result.entries[0].flag1)
                self.assertIsNone(result.entries[0].flag2)

    def test_windows_10_invalid_filetime_preserves_path(self):
        result = parse_appcompat_cache(
            windows_10_cache(
                [windows_10_entry(r"C:\Evidence\invalid-time.exe", 0xFFFFFFFFFFFFFFFF)]
            )
        )

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].path, r"C:\Evidence\invalid-time.exe")
        self.assertIsNone(result.entries[0].modification_date)
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid FILETIME", result.diagnostics[0])

    def test_windows_10_stops_at_unbounded_truncation(self):
        valid = windows_10_entry(r"C:\Evidence\valid.exe")
        truncated = b"10ts" + bytes(4) + struct.pack("<I", 4096)
        result = parse_appcompat_cache(windows_10_cache([valid, truncated]))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\Evidence\valid.exe"])
        self.assertEqual(len(result.diagnostics), 2)
        self.assertIn("outside the cache", result.diagnostics[0])
        self.assertIn("declares 2 entries but contains 1", result.diagnostics[1])

    def test_header_only_caches_are_empty(self):
        for header_size in (48, 52, 128):
            with self.subTest(header_size=header_size):
                header = bytearray(header_size)
                struct.pack_into("<I", header, 0, header_size)
                result = parse_appcompat_cache(bytes(header))
                self.assertEqual(result.entries, ())
                self.assertEqual(result.diagnostics, ())

    def test_unsupported_signature_is_explicit(self):
        with self.assertRaisesRegex(
            UnsupportedAppCompatCacheFormat,
            "0x12345678",
        ):
            parse_appcompat_cache(struct.pack("<I", 0x12345678) + bytes(60))

    def test_short_value_is_malformed(self):
        with self.assertRaisesRegex(AppCompatCacheParseError, "too short: 3 bytes"):
            parse_appcompat_cache(b"\x01\x02\x03")

    def test_invalid_utf16_body_is_reported(self):
        body = (
            struct.pack("<H", 2)
            + b"\x00\xd8"
            + struct.pack("<QI", FILETIME, 0)
        )
        result = parse_appcompat_cache(
            windows_10_cache([variable_entry(b"10ts", body)])
        )

        self.assertEqual(result.entries, ())
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("not valid UTF-16LE", result.diagnostics[0])
