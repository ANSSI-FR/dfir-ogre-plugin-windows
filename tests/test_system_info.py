import codecs
import csv
import io
import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import SystemInfo

from . import CONF_FOLDER


HEADERS = [
    "Host Name", "OS Name", "OS Version", "OS Manufacturer", "OS Configuration",
    "OS Build Type", "Registered Owner", "Registered Organization", "Product ID",
    "Original Install Date", "System Boot Time", "System Manufacturer", "System Model",
    "System Type", "Processor(s)", "BIOS Version", "Windows Directory",
    "System Directory", "Boot Device", "System Locale", "Input Locale", "Time Zone",
    "Total Physical Memory", "Available Physical Memory", "Virtual Memory: Max Size",
    "Virtual Memory: Available", "Virtual Memory: In Use", "Page File Location(s)",
    "Domain", "Logon Server", "Hotfix(s)", "Network Card(s)", "Hyper-V Requirements",
]


class TestSystemInfo(TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.folder = Path(self.temp_directory.name)
        self.input_file = self.folder / "Systeminfo.csv"
        self.plugin_file = os.path.join(CONF_FOLDER, "system_info.xml")

    def write_csv(self, headers, rows, quoting=csv.QUOTE_ALL):
        with self.input_file.open("w", encoding="cp866", newline="") as stream:
            writer = csv.writer(stream, quoting=quoting)
            writer.writerow(headers)
            writer.writerows(rows)

    def parse(self, input_file=None):
        output_config = OutputConfiguration(
            "systeminfo", str(self.folder), with_timeline=False, include_empty=True,
        )
        (self.folder / "systeminfo.systeminfo.jsonl").unlink(missing_ok=True)
        parser = SystemInfo()
        report = parser.parse(
            str(input_file or self.input_file), self.plugin_file,
            RunConfiguration([output_config]), Metadata("test"),
        )
        records = []
        for output_report in report.output_reports:
            for file_report in output_report.file_reports:
                with open(file_report.file_name, encoding="utf-8") as stream:
                    records.extend(json.loads(line) for line in stream)
                self.assertEqual(file_report.num_lines, len(records))
        return report, records

    def fixture_row(self):
        with open("tests/data/csv/Systeminfo.csv", encoding="cp866", newline="") as stream:
            reader = csv.reader(stream)
            next(reader)
            return next(reader)

    def test_systeminfo(self):
        report, records = self.parse("tests/data/csv/Systeminfo.csv")
        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["host_name"], "W2022")
        self.assertEqual(record["os_name"], "Microsoft Windows Server 2022 Standard")
        self.assertEqual(record["system_type"], "x64-based PC")
        self.assertEqual(record["total_physical_memory"], "2\xa0187 MB")
        self.assertEqual(record["original_install_date"], "08/09/2021, 08:52:45")
        self.assertEqual(record["system_boot_time"], "23/03/2025, 19:13:36")
        self.assertEqual(
            report.output_reports[0].file_reports[0].file_name,
            str(self.folder / "systeminfo.systeminfo.jsonl"),
        )

    def test_windows_2003_uptime_and_page_file_headers(self):
        headers = HEADERS[:-1]
        headers[10] = "System Up Time"
        headers[24:27] = ["Page File: Max Size", "Page File: Available", "Page File: In Use"]
        row = self.fixture_row()[:-1]
        row[10] = "12 Days, 3 Hours, 4 Minutes, 5 Seconds"
        self.write_csv(headers, [row])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["system_up_time"], "12 Days, 3 Hours, 4 Minutes, 5 Seconds")
        self.assertFalse(records[0].get("system_boot_time"))
        self.assertEqual(records[0]["virtual_memory_max_size"], "3\xa0211 MB")
        self.assertEqual(records[0]["virtual_memory_available"], "1\xa0742 MB")
        self.assertEqual(records[0]["virtual_memory_in_use"], "1\xa0469 MB")
        self.assertEqual(records[0]["network_cards"], row[31])
        self.assertFalse(records[0].get("hyper_v_requirements"))

    def test_escaped_quotes_and_multiline_fields_remain_raw_strings(self):
        row = self.fixture_row()
        row[6] = 'A "quoted", owner'
        row[31] = 'Adapter "one"\r\nAddress: 192.0.2.1\nAdapter two'
        row[9] = "11/12/2024, 1:02:03 PM"
        self.write_csv(HEADERS, [row])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["registered_owner"], 'A "quoted", owner')
        self.assertEqual(records[0]["network_cards"], 'Adapter "one"\r\nAddress: 192.0.2.1\nAdapter two')
        self.assertEqual(records[0]["original_install_date"], "11/12/2024, 1:02:03 PM")

    def test_headers_control_reordered_columns(self):
        row = self.fixture_row()
        headers = HEADERS.copy()
        headers[0], headers[28] = headers[28], headers[0]
        row[0], row[28] = row[28], row[0]
        self.write_csv(headers, [row])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(records[0]["host_name"], "W2022")
        self.assertEqual(records[0]["domain"], "WORKGROUP")

    def test_modern_32_columns_keep_boot_time(self):
        self.write_csv(HEADERS[:-1], [self.fixture_row()[:-1]])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["system_boot_time"], "23/03/2025, 19:13:36")
        self.assertFalse(records[0].get("system_up_time"))

    def test_optional_empty_columns_do_not_shift_values(self):
        row = self.fixture_row()
        row[7] = row[10] = row[32] = ""
        self.write_csv(HEADERS, [row])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(records[0]["registered_organization"], "")
        self.assertEqual(records[0]["system_boot_time"], "")
        self.assertEqual(records[0]["system_manufacturer"], "Microsoft Corporation")
        self.assertEqual(records[0]["network_cards"], row[31])
        self.assertEqual(records[0]["hyper_v_requirements"], "")

    def test_standard_csv_with_unquoted_columns(self):
        self.write_csv(HEADERS, [self.fixture_row()], quoting=csv.QUOTE_MINIMAL)

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["host_name"], "W2022")

    def test_localized_canonical_33_column_headers_preserve_ibm866(self):
        row = self.fixture_row()
        row[0] = "СЕРВЕР"
        self.write_csv([f"Поле {index}" for index in range(33)], [row])

        report, records = self.parse()

        self.assertIsNone(report.last_error)
        self.assertEqual(records[0]["host_name"], "СЕРВЕР")
        self.assertEqual(records[0]["system_boot_time"], "23/03/2025, 19:13:36")
        self.assertEqual(records[0]["network_cards"], row[31])

    def test_unicode_boms_override_descriptor_encoding(self):
        row = self.fixture_row()
        row[6] = "使用者"
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerow(row)
        for encoding, bom in [
            ("utf-8", codecs.BOM_UTF8),
            ("utf-16-le", codecs.BOM_UTF16_LE),
            ("utf-16-be", codecs.BOM_UTF16_BE),
        ]:
            with self.subTest(encoding=encoding):
                self.input_file.write_bytes(bom + stream.getvalue().encode(encoding))

                report, records = self.parse()

                self.assertIsNone(report.last_error)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["host_name"], "W2022")
                self.assertEqual(records[0]["registered_owner"], "使用者")

    def test_unknown_32_column_headers_are_not_assumed_to_be_uptime(self):
        self.write_csv([f"Поле {index}" for index in range(32)], [self.fixture_row()[:-1]])

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("header", report.last_error.lower())

    def test_malformed_column_counts_report_line_and_skip_row(self):
        for malformed_row in [self.fixture_row()[:-1], self.fixture_row() + ["extra"]]:
            with self.subTest(column_count=len(malformed_row)):
                self.write_csv(HEADERS, [malformed_row, self.fixture_row()])

                report, records = self.parse()

                self.assertEqual(report.num_errors, 1)
                self.assertIn("line 2", report.last_error.lower())
                self.assertIn("33", report.last_error)
                self.assertIn(str(len(malformed_row)), report.last_error)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["host_name"], "W2022")

    def test_unterminated_quoted_field_is_a_csv_diagnostic(self):
        self.write_csv(HEADERS, [])
        with self.input_file.open("a", encoding="cp866", newline="") as stream:
            stream.write('"unterminated\nfield')

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("csv", report.last_error.lower())
        self.assertIn("line 2", report.last_error.lower())

    def test_duplicate_header_reports_ambiguous_mapping(self):
        headers = HEADERS.copy()
        headers[1] = "Host Name"
        self.write_csv(headers, [self.fixture_row()])

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("header", report.last_error.lower())

    def test_mixed_unknown_header_does_not_trigger_positional_fallback(self):
        headers = HEADERS.copy()
        headers[1] = "Unknown OS Label"
        self.write_csv(headers, [self.fixture_row()])

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("header", report.last_error.lower())

    def test_unknown_noncanonical_header_is_reported(self):
        self.write_csv(["First", "Second"], [["server", "OS"]])

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("header", report.last_error.lower())

    def test_empty_file_reports_missing_header(self):
        self.input_file.write_bytes(b"")

        report, records = self.parse()

        self.assertEqual(records, [])
        self.assertEqual(report.num_errors, 1)
        self.assertIn("header", report.last_error.lower())
