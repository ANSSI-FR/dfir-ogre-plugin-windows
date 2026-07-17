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


def windows_8_entry(
    path: str,
    version: str,
    flag1: bytes,
    flag2: bytes,
    filetime: int = FILETIME,
    data: bytes = b"",
) -> bytes:
    encoded_path = path.encode("utf-16-le")
    unknown = b"\x5a\xa5" if version == "8.1" else b""
    body = (
        struct.pack("<H", len(encoded_path))
        + encoded_path
        + flag1
        + flag2
        + unknown
        + struct.pack("<QI", filetime, len(data))
        + data
    )
    marker = b"00ts" if version == "8.0" else b"10ts"
    return variable_entry(marker, body)


def windows_8_cache(entries: list[bytes], first_dword: int = 128) -> bytes:
    header = bytearray(128)
    struct.pack_into("<I", header, 0, first_dword)
    return bytes(header) + b"".join(entries)


def windows_xp_cache(paths: list[str]) -> bytes:
    header = bytearray(400)
    struct.pack_into("<IIII", header, 0, 0xDEADBEEF, len(paths), len(paths), 0)
    for index in range(len(paths)):
        struct.pack_into("<I", header, 16 + index * 4, index)

    entries = []
    for path in paths:
        encoded_path = path.encode("utf-16-le") + b"\x00\x00"
        path_field = encoded_path + bytes(528 - len(encoded_path))
        entries.append(path_field + struct.pack("<QQQ", FILETIME, 1234, FILETIME))
    return bytes(header) + b"".join(entries)


def fixed_cache(signature: int, paths: list[str], is_64bit: bool) -> bytes:
    if signature == 0xBADC0FFE:
        header_size = 8
        entry_size = 32 if is_64bit else 24
    else:
        header_size = 128
        entry_size = 48 if is_64bit else 32
    encoded_paths = [path.encode("utf-16-le") for path in paths]
    next_path_offset = header_size + entry_size * len(paths)
    entries = []
    path_data = []

    for encoded_path in encoded_paths:
        if signature == 0xBADC0FFE and is_64bit:
            entry = struct.pack(
                "<HHIQQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                0,
                next_path_offset,
                FILETIME,
                0,
            )
        elif signature == 0xBADC0FFE:
            entry = struct.pack(
                "<HHIQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                next_path_offset,
                FILETIME,
                0,
            )
        elif is_64bit:
            entry = struct.pack(
                "<HHIQQIIQQ",
                len(encoded_path),
                len(encoded_path) + 2,
                0,
                next_path_offset,
                FILETIME,
                2,
                0,
                0,
                0,
            )
        else:
            entry = struct.pack(
                "<HHIQIIII",
                len(encoded_path),
                len(encoded_path) + 2,
                next_path_offset,
                FILETIME,
                2,
                0,
                0,
                0,
            )
        entries.append(entry)
        path_data.append(encoded_path + b"\x00\x00")
        next_path_offset += len(encoded_path) + 2

    header = struct.pack("<II", signature, len(paths)) + bytes(header_size - 8)
    return header + b"".join(entries) + b"".join(path_data)


class AppCompatCacheFormats(TestCase):
    def test_windows_xp(self):
        result = parse_appcompat_cache(
            windows_xp_cache([r"\??\C:\Windows\System32\calc.exe"])
        )

        self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(
            result.entries[0].path,
            r"\??\C:\Windows\System32\calc.exe",
        )
        self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)

    def test_windows_xp_skips_bad_fixed_entry_and_continues(self):
        cache = bytearray(windows_xp_cache([r"C:\bad.exe", r"C:\good.exe"]))
        cache[400:928] = b"A" * 528
        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\good.exe"])
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("missing UTF-16 terminator", result.diagnostics[0])

    def test_fixed_layouts(self):
        cases = (
            (0xBADC0FFE, False, "Windows 2003/Vista x86"),
            (0xBADC0FFE, True, "Windows 2003/Vista x64"),
            (0xBADC0FEE, False, "Windows 7 x86"),
            (0xBADC0FEE, True, "Windows 7 x64"),
        )
        for signature, is_64bit, label in cases:
            with self.subTest(label=label):
                path = rf"C:\Evidence\case-{signature:x}-{int(is_64bit)}.exe"
                result = parse_appcompat_cache(
                    fixed_cache(signature, [path], is_64bit)
                )
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].path, path)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertIsNone(result.entries[0].flag1)
                self.assertIsNone(result.entries[0].flag2)

    def test_fixed_layout_skips_bad_path_and_continues(self):
        cache = bytearray(
            fixed_cache(
                0xBADC0FEE,
                [r"C:\Evidence\bad.exe", r"C:\Evidence\good.exe"],
                False,
            )
        )
        struct.pack_into("<I", cache, 128 + 4, len(cache) + 100)
        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\Evidence\good.exe"])
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid path range", result.diagnostics[0])

    def test_windows_8_layouts_and_flag_alignment(self):
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        for version in ("8.0", "8.1"):
            with self.subTest(version=version):
                result = parse_appcompat_cache(
                    windows_8_cache(
                        [
                            windows_8_entry(
                                rf"C:\Evidence\windows-{version}.exe",
                                version,
                                flag1,
                                flag2,
                                data=b"forensic-data",
                            )
                        ],
                        first_dword=0,
                    )
                )
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].flag1, flag1)
                self.assertEqual(result.entries[0].flag2, flag2)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)

    def test_windows_8_skips_malformed_bounded_body(self):
        valid_1 = windows_8_entry(
            r"C:\Evidence\first.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )
        malformed = variable_entry(b"10ts", b"\x03\x00abc")
        valid_2 = windows_8_entry(
            r"C:\Evidence\second.exe",
            "8.1",
            bytes(4),
            bytes(4),
        )
        result = parse_appcompat_cache(windows_8_cache([valid_1, malformed, valid_2]))

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\Evidence\first.exe", r"C:\Evidence\second.exe"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("invalid byte size 3", result.diagnostics[0])

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
