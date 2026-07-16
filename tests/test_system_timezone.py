import os
from datetime import timezone
from unittest import TestCase

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OutputConfiguration,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows import system_timezone

from . import BASE_TEMP_FOLDER


DATA_FOLDER = os.path.join("tests", "data")


class TestSystemTimezoneFallback(TestCase):
    def resolver(self):
        self.assertTrue(
            hasattr(system_timezone, "resolve_system_timezone_or_utc"),
            "shared timezone fallback policy is not implemented",
        )
        return getattr(system_timezone, "resolve_system_timezone_or_utc")

    def test_missing_system_reports_warns_and_returns_utc(self):
        report = RunReport()

        with self.assertLogs(system_timezone.__name__, level="WARNING") as logs:
            timezone_info = self.resolver()([], "vss-1", report)

        self.assertIs(timezone_info, timezone.utc)
        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'vss-1'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertIn("interpreting local timestamps as UTC", logs.output[0])

    def test_valid_system_returns_source_timezone_without_warning(self):
        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    "unused",
                    BASE_TEMP_FOLDER,
                    with_timeline=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "vss-1"
        metadata.original_filename = r"C:\Windows\System32\config\SYSTEM"
        entry = BatchEntry(
            os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat"),
            run_config,
            metadata,
        )
        report = RunReport()

        with self.assertNoLogs(system_timezone.__name__, level="WARNING"):
            timezone_info = self.resolver()([entry], "vss-1", report)

        self.assertEqual(str(timezone_info), "Europe/Paris")
        self.assertEqual(report.num_errors, 0)
        self.assertIsNone(report.last_error)
