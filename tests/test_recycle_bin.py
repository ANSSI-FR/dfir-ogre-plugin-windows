import io
import json
import os
import struct
import tempfile
from unittest import TestCase
from unittest.mock import patch

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RecycleBin

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "recycle_bin")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestRecycleBin(TestCase):
    # python -m unittest tests.test_recycle_bin.TestRecycleBin.test_windows7 -v
    def test_windows7(self):
        plugin_file = os.path.join(CONF_FOLDER, "recycle_bin.xml")
        input_file = os.path.join(DATA_FOLDER, "recycle_bin", "W7_$ILX8009")

        base_output_name = "recycle_bin_w7"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".recycle_bin.jsonl"
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
        parser = RecycleBin()
        self.assertEqual("RecycleBin", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)
        self.assertEqual(report.num_errors, 0)

        expected_lines = 1
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
                        js["description"],
                        "path: C:\\Users\\Admin\\Downloads\\prd-testzip-W7.zip",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "size: 572",
                    )
                    self.assertEqual(js["data"], {
                        "path": r"C:\Users\Admin\Downloads\prd-testzip-W7.zip",
                        "size": 572,
                        "header": 1,
                        "uninstall_date": "2024-05-06T15:56:56.626000+00:00",
                    })
                    self.assertEqual(
                        js["timestamp"], "2024-05-06T15:56:56.626000+00:00",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_recycle_bin.TestRecycleBin.test_windows10 -v
    def test_windows10(self):
        plugin_file = os.path.join(CONF_FOLDER, "recycle_bin.xml")
        input_file = os.path.join(DATA_FOLDER, "recycle_bin", "W10_$IC7V7S1")

        base_output_name = "recycle_bin_w10"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".recycle_bin.jsonl"
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
        parser = RecycleBin()
        self.assertEqual("RecycleBin", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)
        self.assertEqual(report.num_errors, 0)

        expected_lines = 1
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
                        js["description"],
                        "path: C:\\Users\\Administrator\\Downloads\\prd-testzip-W10.zip",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "size: 572",
                    )
                    self.assertEqual(js["data"], {
                        "path": r"C:\Users\Administrator\Downloads\prd-testzip-W10.zip",
                        "size": 572,
                        "header": 2,
                        "uninstall_date": "2024-05-06T16:26:04.094000+00:00",
                    })
                    self.assertEqual(
                        js["timestamp"], "2024-05-06T16:26:04.094000+00:00",
                    )

                i += 1
            self.assertEqual(i, expected_lines)


class TestRecycleBinStructure(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def parse_payload(self, payload):
        input_file = os.path.join(self.temp_dir.name, "input")
        with open(input_file, "wb") as fp:
            fp.write(payload)
        output_file = os.path.join(self.temp_dir.name, "entry.recycle_bin.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)
        report = RecycleBin().parse(
            input_file,
            os.path.join(CONF_FOLDER, "recycle_bin.xml"),
            RunConfiguration([
                OutputConfiguration(
                    "entry", self.temp_dir.name,
                    with_timeline=False, include_empty=True,
                ),
            ]),
            Metadata("test"),
        )
        rows = []
        if os.path.exists(output_file):
            with open(output_file, encoding="utf-8") as fp:
                rows = [json.loads(line) for line in fp]
        return report, rows

    def assert_invalid_payload(self, payload):
        report, rows = self.parse_payload(payload)
        self.assertEqual(report.num_errors, 1, report.last_error)
        self.assertIsNotNone(report.last_error)
        self.assertEqual(rows, [])
        self.assertEqual(
            sum(
                file_report.num_lines
                for output_report in report.output_reports
                for file_report in output_report.file_reports
            ),
            0,
        )

    def test_rejects_truncation_at_required_field_boundaries(self):
        path = "C:\\evidence.txt\0".encode("utf-16-le")
        for version in (1, 2):
            header = struct.pack("<QQQ", version, 572, 133486382450000000)
            if version == 1:
                payload = header + path.ljust(520, b"\0")
                cutoffs = (0, 1, 7, 8, 9, 15, 16, 17, 23, 24, 26, 542, 543)
            else:
                payload = header + struct.pack("<I", len(path) // 2) + path
                cutoffs = (
                    0, 1, 7, 8, 9, 15, 16, 17, 23, 24, 25, 27, 28,
                    len(payload) - 2, len(payload) - 1,
                )
            for cutoff in cutoffs:
                with self.subTest(version=version, cutoff=cutoff):
                    self.assert_invalid_payload(payload[:cutoff])

    def test_rejects_declared_path_longer_than_available_data(self):
        path = "C:\\evidence.txt\0".encode("utf-16-le")
        payload = (
            struct.pack("<QQQI", 2, 572, 133486382450000000, len(path) // 2 + 1)
            + path
        )
        self.assert_invalid_payload(payload)

    def test_rejects_huge_declared_path_before_attempting_large_read(self):
        payload = struct.pack("<QQQI", 2, 0, 0, 0xFFFFFFFF) + b"\0\0"

        class BoundedInput(io.BytesIO):
            oversized_read = False

            def read(self, size=-1):
                if size > len(payload):
                    self.oversized_read = True
                    raise ValueError("Requested read exceeds available input")
                return super().read(size)

        native_input = BoundedInput(payload)
        with patch(
            "dfir_ogre_plugin_windows.recycle_bin.open",
            return_value=native_input,
            create=True,
        ):
            self.assert_invalid_payload(payload)
        self.assertFalse(native_input.oversized_read)

    def test_rejects_paths_without_utf16_terminator(self):
        for version in (1, 2):
            with self.subTest(version=version):
                header = struct.pack("<QQQ", version, 572, 133486382450000000)
                if version == 1:
                    path = b"A\0" * 260
                else:
                    path = "C:\\evidence.txt".encode("utf-16-le")
                    header += struct.pack("<I", len(path) // 2)
                self.assert_invalid_payload(header + path)

    def test_rejects_zero_length_v2_path_without_terminator(self):
        self.assert_invalid_payload(struct.pack("<QQQI", 2, 0, 0, 0))

    def test_rejects_v2_path_with_only_embedded_nul(self):
        path = "C:\\evidence\0x".encode("utf-16-le")
        self.assert_invalid_payload(
            struct.pack("<QQQI", 2, 572, 133486382450000000, len(path) // 2)
            + path
        )

    def test_rejects_invalid_utf16_paths(self):
        for version in (1, 2):
            header = struct.pack("<QQQ", version, 572, 133486382450000000)
            invalid_path = b"\x00\xd8\x00\x00"  # Unpaired high surrogate + NUL.
            if version == 1:
                payload = header + invalid_path.ljust(520, b"\0")
            else:
                payload = header + struct.pack("<I", 2) + invalid_path
            with self.subTest(version=version):
                self.assert_invalid_payload(payload)

    def test_rejects_unknown_versions(self):
        for version in (0, 3, 0xFFFFFFFFFFFFFFFF):
            with self.subTest(version=version):
                self.assert_invalid_payload(
                    struct.pack("<QQQ", version, 572, 133486382450000000)
                    + b"\0" * 520
                )

    def test_accepts_complete_empty_path_and_zero_values(self):
        for version in (1, 2):
            header = struct.pack("<QQQ", version, 0, 0)
            if version == 1:
                payload = header + b"\0" * 520
            else:
                payload = header + struct.pack("<I", 1) + b"\0\0"
            with self.subTest(version=version):
                report, rows = self.parse_payload(payload)
                self.assertEqual(report.num_errors, 0, report.last_error)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["path"], "")
                self.assertEqual(rows[0]["size"], 0)
                self.assertEqual(
                    rows[0]["uninstall_date"], "1601-01-01T00:00:00.000000+00:00",
                )
