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
from .test_app_compat_cache_formats import windows_8_cache, windows_8_entry

DATA_FOLDER = os.path.join("tests", "data")


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

    def test_missing_and_non_byte_values_are_diagnostic(self):
        parser = RegAppCompatCache()
        cases = (("missing", None), ("non-byte", "not bytes"))
        for label, cache_data in cases:
            with self.subTest(label=label):
                key = Mock()
                key.path = rf"HKLM\SYSTEM\ControlSet001\{label}"
                if cache_data is None:
                    key.value.return_value = None
                else:
                    cache_value = Mock()
                    cache_value.data.return_value = cache_data
                    key.value.return_value = cache_value
                output = Mock()
                report = RunReport()

                with self.assertLogs(
                    "dfir_ogre_plugin_windows.registry.app_compat_cache",
                    level="WARNING",
                ):
                    parser.parse_key(key, output, report)

                self.assertEqual(output.write.call_count, 0)
                self.assertEqual(report.num_errors, 1)

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
