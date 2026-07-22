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
    package: bytes = b"",
) -> bytes:
    encoded_path = path.encode("utf-16-le")
    body = (
        struct.pack("<H", len(encoded_path))
        + encoded_path
        + struct.pack("<H", len(package))
        + package
        + flag1
        + flag2
        + struct.pack("<QI", filetime, len(data))
        + data
    )
    marker = b"00ts" if version == "8.0" else b"10ts"
    return variable_entry(marker, body)


def windows_8_cache(entries: list[bytes], first_dword: int = 128) -> bytes:
    header = bytearray(128)
    struct.pack_into("<I", header, 0, first_dword)
    return bytes(header) + b"".join(entries)


def windows_xp_entry(path: str) -> bytes:
    encoded_path = path.encode("utf-16-le") + b"\x00\x00"
    path_field = encoded_path + bytes(528 - len(encoded_path))
    return path_field + struct.pack("<QQQ", FILETIME, 1234, FILETIME)


def windows_xp_cache(
    paths: list[str],
    *,
    slot_count: int | None = None,
    lru_indexes: list[int] | None = None,
) -> bytes:
    if slot_count is None:
        slot_count = len(paths)
    if lru_indexes is None:
        lru_indexes = list(range(len(paths)))
    if len(paths) != len(lru_indexes):
        raise ValueError("each XP path requires one LRU index")

    header = bytearray(400)
    struct.pack_into(
        "<IIII",
        header,
        0,
        0xDEADBEEF,
        slot_count,
        len(lru_indexes),
        0,
    )
    entries = [bytes(552) for _ in range(slot_count)]
    for lru_position, (slot_index, path) in enumerate(zip(lru_indexes, paths)):
        struct.pack_into("<I", header, 16 + lru_position * 4, slot_index)
        entries[slot_index] = windows_xp_entry(path)
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


def set_windows_7_data_extent(
    cache: bytearray,
    is_64bit: bool,
    data_size: int,
    data_offset: int,
) -> None:
    field_offset = 128 + (32 if is_64bit else 24)
    field_format = "<QQ" if is_64bit else "<II"
    struct.pack_into(field_format, cache, field_offset, data_size, data_offset)


class AppCompatCacheFormats(TestCase):
    def test_independent_reference_vectors(self):
        filetime = bytes.fromhex("8000c44a19c1d501")
        xp_x86 = (
            bytes.fromhex(
                "efbeadde"
                "01000000"
                "01000000"
                "00000000"
                "00000000"
            )
            + bytes(380)
            + bytes.fromhex("43003a005c0078002e00650078006500")
            + b"\x00\x00"
            + bytes(510)
            + filetime
            + bytes(16)
        )
        nt5_x86 = bytes.fromhex(
            "fe0fdcba01000000"
            "1000120020000000"
            "8000c44a19c1d5010000000000000000"
            "43003a005c0061002e006500780065000000"
        )
        nt5_x64 = bytes.fromhex(
            "fe0fdcba01000000"
            "10001200000000002800000000000000"
            "8000c44a19c1d5010000000000000000"
            "43003a005c0062002e006500780065000000"
        )
        windows_7_x86 = (
            bytes.fromhex("ee0fdcba0100000078000000")
            + bytes(116)
            + bytes.fromhex(
                "10001200a0000000"
                "8000c44a19c1d5010200000000000000"
                "0000000000000000"
                "43003a005c0063002e006500780065000000"
            )
        )
        windows_7_x64 = (
            bytes.fromhex("ee0fdcba0100000078000000")
            + bytes(116)
            + bytes.fromhex(
                "1000120000000000b000000000000000"
                "8000c44a19c1d5010200000000000000"
                "00000000000000000000000000000000"
                "43003a005c0064002e006500780065000000"
            )
        )
        windows_8_0 = bytes(128) + bytes.fromhex(
            "303074730000000028000000"
            "100043003a005c0065002e00650078006500"
            "000011223344aabbccdd8000c44a19c1d50100000000"
        )
        windows_8_1 = bytes(128) + bytes.fromhex(
            "313074730000000028000000"
            "100043003a005c0066002e00650078006500"
            "000011223344aabbccdd8000c44a19c1d50100000000"
        )
        windows_10_48 = (
            bytes.fromhex("30000000")
            + bytes(32)
            + bytes.fromhex("01000000")
            + bytes(8)
            + bytes.fromhex(
                "31307473000000001e000000"
                "100043003a005c0067002e00650078006500"
                "8000c44a19c1d50100000000"
            )
        )
        windows_10_52 = (
            bytes.fromhex("34000000")
            + bytes(36)
            + bytes.fromhex("01000000")
            + bytes(8)
            + bytes.fromhex(
                "31307473000000001e000000"
                "100043003a005c0068002e00650078006500"
                "8000c44a19c1d50100000000"
            )
        )
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        vectors = (
            ("Windows XP x86", xp_x86, r"C:\x.exe", None, None),
            ("0xbadc0ffe x86", nt5_x86, r"C:\a.exe", None, None),
            ("0xbadc0ffe x64", nt5_x64, r"C:\b.exe", None, None),
            ("Windows 7 x86", windows_7_x86, r"C:\c.exe", None, None),
            ("Windows 7 x64", windows_7_x64, r"C:\d.exe", None, None),
            ("Windows 8.0", windows_8_0, r"C:\e.exe", flag1, flag2),
            ("Windows 8.1", windows_8_1, r"C:\f.exe", flag1, flag2),
            ("Windows 10/48", windows_10_48, r"C:\g.exe", None, None),
            ("Windows 10/52", windows_10_52, r"C:\h.exe", None, None),
        )

        for label, cache, path, expected_flag1, expected_flag2 in vectors:
            with self.subTest(label=label):
                result = parse_appcompat_cache(cache)
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].path, path)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertEqual(result.entries[0].flag1, expected_flag1)
                self.assertEqual(result.entries[0].flag2, expected_flag2)

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

    def test_windows_xp_ignores_unused_allocated_slots(self):
        result = parse_appcompat_cache(
            windows_xp_cache(
                [r"C:\active-one.exe", r"C:\active-two.exe"],
                slot_count=96,
            )
        )

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\active-one.exe", r"C:\active-two.exe"],
        )
        self.assertEqual(result.diagnostics, ())

    def test_windows_xp_uses_lru_indexes_in_physical_slot_order(self):
        cache = bytearray(
            windows_xp_cache(
                [r"C:\slot-five.exe", r"C:\slot-two.exe"],
                slot_count=6,
                lru_indexes=[5, 2],
            )
        )
        stale_offset = 400 + 4 * 552
        cache[stale_offset : stale_offset + 552] = windows_xp_entry(
            r"C:\unreferenced-stale.exe"
        )

        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\slot-two.exe", r"C:\slot-five.exe"],
        )
        self.assertEqual(result.diagnostics, ())

    def test_windows_xp_rejects_lru_count_beyond_allocated_slots(self):
        cache = bytearray(windows_xp_cache([r"C:\active.exe"], slot_count=2))
        struct.pack_into("<I", cache, 8, 3)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU entry count 3 exceeds 2 allocated slots",
        ):
            parse_appcompat_cache(bytes(cache))

    def test_windows_xp_rejects_out_of_range_lru_index(self):
        cache = bytearray(windows_xp_cache([r"C:\active.exe"], slot_count=2))
        struct.pack_into("<I", cache, 16, 2)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU index 2 is outside 2 allocated slots",
        ):
            parse_appcompat_cache(bytes(cache))

    def test_windows_xp_rejects_duplicate_lru_index(self):
        cache = bytearray(
            windows_xp_cache(
                [r"C:\first.exe", r"C:\second.exe"],
                slot_count=2,
            )
        )
        struct.pack_into("<I", cache, 20, 0)

        with self.assertRaisesRegex(
            AppCompatCacheParseError,
            "LRU index 0 is duplicated",
        ):
            parse_appcompat_cache(bytes(cache))

    def test_windows_xp_skips_bad_fixed_entry_and_continues(self):
        cache = bytearray(windows_xp_cache([r"C:\bad.exe", r"C:\good.exe"]))
        cache[400:928] = b"A" * 528
        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual([entry.path for entry in result.entries], [r"C:\good.exe"])
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("missing UTF-16 terminator", result.diagnostics[0])

    def test_windows_xp_reports_undeclared_entry_bytes(self):
        cache = bytearray(windows_xp_cache([r"C:\undeclared.exe"]))
        struct.pack_into("<II", cache, 4, 0, 0)

        result = parse_appcompat_cache(bytes(cache))

        self.assertEqual(result.entries, ())
        self.assertEqual(
            result.diagnostics,
            ("Windows XP entry array ends at 400, cache has 552 trailing bytes",),
        )

    def test_windows_xp_keeps_declared_entry_before_trailing_byte(self):
        cache = windows_xp_cache([r"C:\declared.exe"]) + b"\xa5"

        result = parse_appcompat_cache(cache)

        self.assertEqual([entry.path for entry in result.entries], [r"C:\declared.exe"])
        self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
        self.assertEqual(
            result.diagnostics,
            ("Windows XP entry array ends at 952, cache has 1 trailing byte",),
        )

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

    def test_windows_7_zero_size_data_extent_is_valid(self):
        for is_64bit in (False, True):
            with self.subTest(is_64bit=is_64bit):
                result = parse_appcompat_cache(
                    fixed_cache(
                        0xBADC0FEE,
                        [r"C:\Evidence\zero-data.exe"],
                        is_64bit,
                    )
                )

                self.assertEqual(result.diagnostics, ())
                self.assertEqual(
                    [entry.path for entry in result.entries],
                    [r"C:\Evidence\zero-data.exe"],
                )

    def test_windows_7_in_bounds_data_extent_is_valid(self):
        for is_64bit in (False, True):
            with self.subTest(is_64bit=is_64bit):
                cache = bytearray(
                    fixed_cache(
                        0xBADC0FEE,
                        [r"C:\Evidence\bounded-data.exe"],
                        is_64bit,
                    )
                )
                data_offset = len(cache)
                cache.extend(b"DATA")
                set_windows_7_data_extent(cache, is_64bit, 4, data_offset)

                result = parse_appcompat_cache(bytes(cache))

                self.assertEqual(result.diagnostics, ())
                self.assertEqual(
                    [entry.path for entry in result.entries],
                    [r"C:\Evidence\bounded-data.exe"],
                )

    def test_windows_7_out_of_bounds_data_extent_keeps_entry(self):
        for is_64bit, architecture in ((False, "x86"), (True, "x64")):
            with self.subTest(architecture=architecture):
                cache = bytearray(
                    fixed_cache(
                        0xBADC0FEE,
                        [r"C:\Evidence\bad-data.exe"],
                        is_64bit,
                    )
                )
                data_offset = len(cache) - 2
                set_windows_7_data_extent(cache, is_64bit, 4, data_offset)

                result = parse_appcompat_cache(bytes(cache))

                self.assertEqual(
                    [entry.path for entry in result.entries],
                    [r"C:\Evidence\bad-data.exe"],
                )
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)
                self.assertEqual(
                    result.diagnostics,
                    (
                        f"Windows 7 {architecture} entry 0: data range "
                        f"{data_offset}:{data_offset + 4} extends outside "
                        f"{len(cache)} bytes",
                    ),
                )

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

    def test_fixed_layout_ambiguity_identifies_format(self):
        cases = (
            (0xBADC0FFE, 8, "Windows 2003/Vista"),
            (0xBADC0FEE, 128, "Windows 7"),
        )
        for signature, header_size, format_name in cases:
            with self.subTest(format_name=format_name):
                cache = (
                    struct.pack("<II", signature, 1)
                    + bytes(header_size - 8)
                )
                expected_message = (
                    f"{format_name}: unable to determine fixed-entry architecture "
                    "(x86=-1, x64=-1)"
                )

                with self.assertRaises(AppCompatCacheParseError) as raised:
                    parse_appcompat_cache(cache)

                self.assertEqual(str(raised.exception), expected_message)

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

    def test_windows_8_server_2012_reference_entry(self):
        entry = bytes.fromhex(
            "30307473868ab2fd5e000000"
            "460053005900530056004f004c005c00570069006e0064006f00770073005c00"
            "530079007300740065006d00330032005c004c006f0067006f006e0055004900"
            "2e00650078006500"
            "00004300000000000001c0e30af0db6acd0100000000"
        )

        result = parse_appcompat_cache(bytes(128) + entry)

        self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(
            result.entries[0].path,
            r"SYSVOL\Windows\System32\LogonUI.exe",
        )
        self.assertEqual(result.entries[0].flag1, bytes.fromhex("43000000"))
        self.assertEqual(result.entries[0].flag2, bytes.fromhex("00000001"))
        self.assertEqual(
            result.entries[0].modification_date,
            datetime(2012, 7, 26, 3, 8, 32, 124000, tzinfo=timezone.utc),
        )

    def test_windows_8_skips_package_data_before_flags(self):
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        for version in ("8.0", "8.1"):
            with self.subTest(version=version):
                result = parse_appcompat_cache(
                    windows_8_cache(
                        [
                            windows_8_entry(
                                rf"C:\Evidence\package-{version}.exe",
                                version,
                                flag1,
                                flag2,
                                package=b"\x5a\xa5\x7f",
                            )
                        ]
                    )
                )

                self.assertEqual(result.diagnostics, ())
                self.assertEqual(len(result.entries), 1)
                self.assertEqual(result.entries[0].flag1, flag1)
                self.assertEqual(result.entries[0].flag2, flag2)
                self.assertEqual(result.entries[0].modification_date, EXPECTED_DATE)

    def test_windows_8_skips_package_extent_outside_bounded_body(self):
        encoded_path = r"C:\Evidence\bad-package.exe".encode("utf-16-le")
        malformed_body = (
            struct.pack("<H", len(encoded_path))
            + encoded_path
            + struct.pack("<H", 100)
        )
        valid = windows_8_entry(
            r"C:\Evidence\valid.exe",
            "8.0",
            bytes(4),
            bytes(4),
        )

        result = parse_appcompat_cache(
            windows_8_cache([variable_entry(b"00ts", malformed_body), valid])
        )

        self.assertEqual(
            [entry.path for entry in result.entries],
            [r"C:\Evidence\valid.exe"],
        )
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("flags extend outside the entry body", result.diagnostics[0])

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
        self.assertEqual(len(result.diagnostics), 1)
        self.assertIn("outside the cache", result.diagnostics[0])

    def test_windows_10_exact_headers_ignore_stale_count(self):
        for header_size in (48, 52):
            with self.subTest(header_size=header_size):
                empty = parse_appcompat_cache(
                    windows_10_cache(
                        [],
                        header_size=header_size,
                        declared_count=3,
                    )
                )
                self.assertEqual(empty.entries, ())
                self.assertEqual(empty.diagnostics, ())

                result = parse_appcompat_cache(
                    windows_10_cache(
                        [windows_10_entry(r"C:\Evidence\stale-count.exe")],
                        header_size=header_size,
                        declared_count=0,
                    )
                )

                self.assertEqual(
                    [entry.path for entry in result.entries],
                    [r"C:\Evidence\stale-count.exe"],
                )
                self.assertEqual(result.diagnostics, ())

    def test_windows_8_header_only_cache_is_empty(self):
        header = bytearray(128)
        struct.pack_into("<I", header, 0, 128)

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
