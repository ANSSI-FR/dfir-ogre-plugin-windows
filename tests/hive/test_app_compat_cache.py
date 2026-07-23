import hashlib
import json
import os
import struct
from unittest import TestCase
from unittest.mock import Mock, call

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows import RegAppCompatCache

from . import CONF_FOLDER, TEMP_FOLDER
from .test_app_compat_cache_formats import (
    variable_entry,
    windows_10_cache,
    windows_10_entry,
    windows_8_cache,
    windows_8_entry,
    windows_xp_cache,
)

DATA_FOLDER = os.path.join("tests", "data")


def canonical_cache_sequence_snapshot(output_file: str) -> tuple[int, str]:
    sequence = []
    seen = set()
    with open(output_file, encoding="utf-8") as stream:
        for line in stream:
            data = json.loads(line)["data"]
            item = (
                data["key_path"],
                data["index"],
                data["path"],
                data["modification_date"],
            )
            if item in seen:
                continue
            seen.add(item)
            sequence.append(item)

    payload = json.dumps(
        sequence,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(sequence), hashlib.sha256(payload).hexdigest()


class AppCompatCache(TestCase):
    def test_cache_key_discovery_includes_xp_and_later_paths(self):
        parser = RegAppCompatCache()
        registry = Mock()
        xp_key = Mock()
        later_key = Mock()
        registry.glob_keys.side_effect = ([xp_key], [later_key])
        report = RunReport()

        keys = list(parser.cache_keys(registry, report))

        self.assertEqual(keys, [xp_key, later_key])
        self.assertEqual(
            registry.glob_keys.call_args_list,
            [
                call(
                    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager"
                    "\\AppCompatibility"
                ),
                call(
                    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager"
                    "\\AppCompatCache"
                ),
            ],
        )
        self.assertEqual(report.num_errors, 0)

    def test_unsupported_format_warns_and_updates_run_report(self):
        parser = RegAppCompatCache()
        key = Mock()
        cache_value = Mock()
        cache_value.data.return_value = struct.pack("<I", 0x12345678) + bytes(60)
        key.value.return_value = cache_value
        key.path = r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        output = Mock()
        report = RunReport()

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ) as logs:
            parser.parse_key(key, output, report)

        self.assertEqual(output.write.call_count, 0)
        self.assertEqual(report.num_errors, 1)
        self.assertIn("0x12345678", report.last_error)
        self.assertIn("0x12345678", logs.output[0])

    def test_cache_key_discovery_continues_after_one_pattern_fails(self):
        parser = RegAppCompatCache()
        registry = Mock()
        later_key = Mock()
        registry.glob_keys.side_effect = (RuntimeError("XP traversal failed"), [later_key])
        report = RunReport()

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ):
            keys = list(parser.cache_keys(registry, report))

        self.assertEqual(keys, [later_key])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("XP traversal failed", report.last_error)

    def test_missing_value_is_artifact_absent(self):
        parser = RegAppCompatCache()
        key = Mock()
        key.value.return_value = None
        key.path = r"HKLM\SYSTEM\ControlSet001\missing"
        output = Mock()
        report = RunReport()

        with self.assertNoLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ):
            parser.parse_key(key, output, report)

        self.assertEqual(output.write.call_count, 0)
        self.assertEqual(report.num_errors, 0)
        self.assertIsNone(report.last_error)

    def test_non_byte_value_is_diagnostic(self):
        parser = RegAppCompatCache()
        key = Mock()
        cache_value = Mock()
        cache_value.data.return_value = "not bytes"
        key.value.return_value = cache_value
        key.path = r"HKLM\SYSTEM\ControlSet001\non-byte"
        output = Mock()
        report = RunReport()

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ) as logs:
            parser.parse_key(key, output, report)

        self.assertEqual(output.write.call_count, 0)
        self.assertEqual(report.num_errors, 1)
        self.assertIn("AppCompatCache value is not bytes", report.last_error)
        self.assertIn("AppCompatCache value is not bytes", logs.output[0])

    def test_windows_8_record_keeps_existing_schema(self):
        parser = RegAppCompatCache()
        flag1 = bytes.fromhex("11223344")
        flag2 = bytes.fromhex("aabbccdd")
        cache = windows_8_cache(
            [windows_8_entry(r"C:\Evidence\schema.exe", "8.1", flag1, flag2)]
        )
        key = Mock()
        cache_value = Mock()
        cache_value.data.return_value = cache
        key.value.return_value = cache_value
        key.path = r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        key.mtime = None
        key.security_descriptor.to_record.return_value = Record()
        output = Mock()
        report = RunReport()

        parser.parse_key(key, output, report)

        self.assertEqual(report.num_errors, 0)
        self.assertEqual(output.write.call_count, 1)
        record = json.loads(output.write.call_args.args[0].to_string())
        self.assertEqual(
            set(record),
            {
                "index",
                "path",
                "modification_date",
                "flag1",
                "flag2",
                "key_path",
                "key_modif_time",
                "key_security",
            },
        )
        self.assertEqual(record["flag1"], "0x11223344")
        self.assertEqual(record["flag2"], "0xaabbccdd")

    def test_windows_10_stale_header_count_is_not_an_error(self):
        parser = RegAppCompatCache()
        key_path = (
            r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        )
        for header_size in (48, 52):
            with self.subTest(header_size=header_size):
                key = Mock()
                cache_value = Mock()
                cache_value.data.return_value = windows_10_cache(
                    [windows_10_entry(r"C:\Evidence\stale-count.exe")],
                    header_size=header_size,
                    declared_count=0,
                )
                key.value.return_value = cache_value
                key.path = key_path
                key.mtime = None
                key.security_descriptor.to_record.return_value = Record()
                output = Mock()
                report = RunReport()

                parser.parse_key(key, output, report)

                self.assertEqual(report.num_errors, 0)
                self.assertIsNone(report.last_error)
                self.assertEqual(output.write.call_count, 1)

    def test_windows_xp_trailing_bytes_report_exact_diagnostic(self):
        parser = RegAppCompatCache()
        key_path = (
            r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatibility"
        )
        undeclared = bytearray(windows_xp_cache([r"C:\undeclared.exe"]))
        struct.pack_into("<II", undeclared, 4, 0, 0)
        cases = (
            (
                "undeclared-entry",
                bytes(undeclared),
                "Windows XP entry array ends at 400, cache has 552 trailing bytes",
                0,
            ),
            (
                "trailing-byte",
                windows_xp_cache([r"C:\declared.exe"]) + b"\xa5",
                "Windows XP entry array ends at 952, cache has 1 trailing byte",
                1,
            ),
        )
        for label, cache, diagnostic, expected_writes in cases:
            with self.subTest(label=label):
                key = Mock()
                cache_value = Mock()
                cache_value.data.return_value = cache
                key.value.return_value = cache_value
                key.path = key_path
                key.mtime = None
                key.security_descriptor.to_record.return_value = Record()
                output = Mock()
                report = RunReport()
                expected_message = f"AppCompatCache {key_path}: {diagnostic}"

                with self.assertLogs(
                    "dfir_ogre_plugin_windows.registry.app_compat_cache",
                    level="WARNING",
                ) as logs:
                    parser.parse_key(key, output, report)

                self.assertEqual(
                    [record.getMessage() for record in logs.records],
                    [expected_message],
                )
                self.assertEqual(report.num_errors, 1)
                self.assertEqual(report.last_error, expected_message)
                self.assertEqual(output.write.call_count, expected_writes)

    def test_fixed_layout_ambiguity_reports_key_format_and_reason(self):
        parser = RegAppCompatCache()
        cases = (
            (
                0xBADC0FFE,
                8,
                "Windows 2003/Vista",
                r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache",
            ),
            (
                0xBADC0FEE,
                128,
                "Windows 7",
                r"HKLM\SYSTEM\ControlSet002\Control\Session Manager\AppCompatCache",
            ),
        )
        for signature, header_size, format_name, key_path in cases:
            with self.subTest(format_name=format_name):
                key = Mock()
                cache_value = Mock()
                cache_value.data.return_value = (
                    struct.pack("<II", signature, 1)
                    + bytes(header_size - 8)
                )
                key.value.return_value = cache_value
                key.path = key_path
                output = Mock()
                report = RunReport()
                expected_message = (
                    f"AppCompatCache {key_path}: {format_name}: unable to determine "
                    "fixed-entry architecture (x86=-1, x64=-1)"
                )

                with self.assertLogs(
                    "dfir_ogre_plugin_windows.registry.app_compat_cache",
                    level="WARNING",
                ) as logs:
                    parser.parse_key(key, output, report)

                self.assertEqual(
                    [record.getMessage() for record in logs.records],
                    [expected_message],
                )
                self.assertEqual(report.num_errors, 1)
                self.assertEqual(report.last_error, expected_message)
                self.assertEqual(output.write.call_count, 0)

    def test_recoverable_entry_and_later_key_continue(self):
        parser = RegAppCompatCache()
        first_key_path = (
            r"HKLM\SYSTEM\ControlSet001\Control\Session Manager\AppCompatCache"
        )
        later_key_path = (
            r"HKLM\SYSTEM\ControlSet002\Control\Session Manager\AppCompatCache"
        )
        first_cache = windows_8_cache(
            [
                windows_8_entry(
                    r"C:\Evidence\before.exe",
                    "8.1",
                    bytes(4),
                    bytes(4),
                ),
                variable_entry(b"10ts", b"\x03\x00abc"),
                windows_8_entry(
                    r"C:\Evidence\recovered.exe",
                    "8.1",
                    bytes(4),
                    bytes(4),
                ),
            ]
        )
        later_cache = windows_8_cache(
            [
                windows_8_entry(
                    r"C:\Evidence\later-key.exe",
                    "8.1",
                    bytes(4),
                    bytes(4),
                )
            ]
        )
        first_key = Mock()
        first_value = Mock()
        first_value.data.return_value = first_cache
        first_key.value.return_value = first_value
        first_key.path = first_key_path
        first_key.mtime = None
        first_key.security_descriptor.to_record.return_value = Record()
        later_key = Mock()
        later_value = Mock()
        later_value.data.return_value = later_cache
        later_key.value.return_value = later_value
        later_key.path = later_key_path
        later_key.mtime = None
        later_key.security_descriptor.to_record.return_value = Record()
        output = Mock()
        report = RunReport()
        expected_message = (
            f"AppCompatCache {first_key_path}: Windows 8.1 entry 1: "
            "path has invalid byte size 3"
        )

        with self.assertLogs(
            "dfir_ogre_plugin_windows.registry.app_compat_cache",
            level="WARNING",
        ) as logs:
            parser.parse_key(first_key, output, report)
            parser.parse_key(later_key, output, report)

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [expected_message],
        )
        self.assertEqual(report.num_errors, 1)
        self.assertEqual(report.last_error, expected_message)
        records = [
            json.loads(write.args[0].to_string())
            for write in output.write.call_args_list
        ]
        self.assertEqual(
            [
                (record["key_path"], record["index"], record["path"])
                for record in records
            ],
            [
                (first_key_path, 0, r"C:\Evidence\before.exe"),
                (first_key_path, 1, r"C:\Evidence\recovered.exe"),
                (later_key_path, 0, r"C:\Evidence\later-key.exe"),
            ],
        )

    # python -m unittest tests.hive.test_app_compat_cache.AppCompatCache.test_compat_cache -v
    def test_compat_cache(self):
        plugin_file = os.path.join(CONF_FOLDER, "app_compat_cache.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat")
        base_output_name = "app_compat_cache"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".app_compat_cache.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegAppCompatCache()
        self.assertEqual("RegAppCompatCache", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 108
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",
                    )

                    self.assertEqual(
                        js["description"],
                        "path: C:\\WINDOWS\\system32\\ie4ushowIE.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

        entry_count, sequence_digest = canonical_cache_sequence_snapshot(output_file)
        self.assertEqual(entry_count, 54)
        self.assertEqual(
            sequence_digest,
            "fc7b0fd772a90954b308e30ffb9c7cbe73ea33ce35a105f6358541e637f25fb4",
        )

    # python -m unittest tests.hive.test_app_compat_cache.AppCompatCache.test_compat_cache_2 -v
    def test_compat_cache_2(self):
        plugin_file = os.path.join(CONF_FOLDER, "app_compat_cache.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM_2.dat")

        base_output_name = "app_compat_cache_2"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".app_compat_cache.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )
        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = RegAppCompatCache()
        self.assertEqual("RegAppCompatCache", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 474
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        js["related_user"],
                        "S-1-5-18",
                    )

                    self.assertEqual(
                        js["description"],
                        "path: C:\\Windows\\SysWOW64\\cmd.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

        entry_count, sequence_digest = canonical_cache_sequence_snapshot(output_file)
        self.assertEqual(entry_count, 237)
        self.assertEqual(
            sequence_digest,
            "190f6d64ba5326b2af8b6f1cc683532c0fde5cf9e5e129995b634be5a726a0b2",
        )
