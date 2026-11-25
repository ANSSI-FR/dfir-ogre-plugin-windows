"""Raw-MFT integration and shared NTFSInfo output contract."""

import csv
import gzip
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import xml.etree.ElementTree as ET

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import MFT, NTFSInfo


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configuration" / "mft.xml"
FIXTURE = ROOT / "tests" / "data" / "mft" / "tiny.mft.gz"


def output_fields(path):
    fields = {}
    for field in ET.parse(path).findall(".//fields//field"):
        if field.get("parser") not in ("Extension", "Python"):
            name = field.get("output", field.get("input"))
            fields[name] = field
    # file_path is a multi-input join in NTFSInfo.
    for field in ET.parse(path).findall(".//multi_input"):
        fields[field.get("output")] = field
    return fields


class MftTest(TestCase):
    def parse_fixture(
        self, folder, *, format="jsonl", timeline=False, raw=None, config=CONFIG
    ):
        folder = Path(folder)
        source = folder / "$MFT"
        source.write_bytes(
            gzip.decompress(FIXTURE.read_bytes()) if raw is None else raw
        )
        output = OutputConfiguration(
            "test",
            str(folder),
            format=format,
            with_timeline=timeline,
            include_empty=False,
        )
        report = MFT().parse(
            str(source), str(config), RunConfiguration([output]), Metadata("test")
        )
        return report

    def test_registered_and_shared_schema_matches_ntfs_info(self):
        # Other test modules also import the library under src.*, registering
        # duplicate subclasses. Check public discovery in a fresh interpreter.
        count = subprocess.check_output(
            [
                sys.executable,
                "-c",
                "from dfir_ogre_plugin_windows import list_parsers; "
                "print(sum(p.command == 'MFT' for p in list_parsers()))",
            ],
            text=True,
        )
        self.assertEqual(count.strip(), "1")
        mft = output_fields(CONFIG)
        ntfs = output_fields(ROOT / "configuration" / "ntfs_info.xml")
        common = mft.keys() & ntfs.keys()
        self.assertGreaterEqual(len(common), 36)
        for name in common:
            with self.subTest(field=name):
                self.assertEqual(
                    mft[name].get("qualifier"), ntfs[name].get("qualifier")
                )
                expected = ntfs[name].get("parser")
                expected = (
                    "String"
                    if expected == "Join"
                    else "Int"
                    if expected == "IntRadix"
                    else expected
                )
                self.assertEqual(mft[name].get("parser"), expected)
        for name in ("parent_sequence_number", "parent_record_number"):
            self.assertEqual(mft[name].get("parser"), "Int")
            self.assertIsNone(mft[name].get("qualifier"))

    def test_raw_mft_outputs_known_file_and_native_value_types(self):
        with TemporaryDirectory() as folder:
            report = self.parse_fixture(folder)
            self.assertEqual(report.last_error, None)
            self.assertEqual(report.num_errors, 0)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            file8 = next(row for row in rows if row.get("record_number") == 32)
            self.assertEqual(file8["file_name"], "file8.txt")
            self.assertTrue(file8["file_path"].endswith(r"\file8.txt"))
            for name in (
                "record_number",
                "sequence_number",
                "parent_record_number",
                "file_size",
                "usn_number",
            ):
                self.assertIs(type(file8[name]), int)
            for name, value in file8.items():
                if name.startswith("file_attributes_") or name == "file_in_use":
                    self.assertIs(type(value), bool)
            self.assertIn("si_lastchange_date", file8)
            self.assertNotIn("md5", file8)
            self.assertNotIn("volume_id", file8)

    def test_csv_and_timeline_and_normalized_output(self):
        for format, timeline in (
            ("csv", False),
            ("jsonl", True),
            ("normalized_jsonl", False),
        ):
            with (
                self.subTest(format=format, timeline=timeline),
                TemporaryDirectory() as folder,
            ):
                report = self.parse_fixture(folder, format=format, timeline=timeline)
                self.assertIsNone(report.last_error)
                files = report.output_reports[0].file_reports
                self.assertTrue(files)
                for file in files:
                    self.assertGreater(file.num_lines, 0)
                    self.assertGreater(Path(file.file_name).stat().st_size, 0)
                if format == "csv":
                    with Path(files[0].file_name).open(newline="") as stream:
                        rows = list(csv.DictReader(stream, delimiter=";"))
                    row = next(row for row in rows if row["record_number"] == "32")
                    self.assertEqual(row["file_name"], "file8.txt")
                    self.assertIn("file_attributes_recall_on_open", row)
                elif timeline:
                    rows = [
                        json.loads(line)
                        for line in Path(files[0].file_name).read_text().splitlines()
                    ]
                    self.assertTrue(
                        any(
                            row.get("data", {}).get("record_number") == 32
                            for row in rows
                        )
                    )

    def test_corruption_is_reported_once_and_later_records_survive(self):
        data = bytearray(gzip.decompress(FIXTURE.read_bytes()))
        data[31 * 1024 + 510] ^= 0xFF
        with TemporaryDirectory() as folder:
            with self.assertLogs(level="ERROR") as logs:
                report = self.parse_fixture(folder, raw=data)
            self.assertEqual(len(logs.output), 1)
            self.assertEqual(report.num_errors, 1)
            self.assertIn("record 31", report.last_error)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertTrue(any(row.get("record_number") == 32 for row in rows))

    def test_invalid_file_is_a_reported_error(self):
        with TemporaryDirectory() as folder:
            report = self.parse_fixture(folder, raw=b"not a raw MFT")
            self.assertEqual(report.num_errors, 1)
            self.assertFalse(report.output_reports)

    def test_record_aligned_truncation_is_reported_with_partial_output(self):
        data = gzip.decompress(FIXTURE.read_bytes())[: 32 * 1024]
        with TemporaryDirectory() as folder:
            report = self.parse_fixture(folder, raw=data)
            self.assertGreater(report.num_errors, 0)
            self.assertIn("truncated", report.last_error.lower())
            self.assertGreater(report.output_reports[0].file_reports[0].num_lines, 0)

    def test_bad_first_record_and_missing_root_preserve_later_records(self):
        for damage in ("first", "geometry", "root"):
            with self.subTest(damage=damage), TemporaryDirectory() as folder:
                data = bytearray(gzip.decompress(FIXTURE.read_bytes()))
                if damage == "first":
                    data[:4] = b"BAAD"
                elif damage == "geometry":
                    data[0x1C:0x20] = (4096).to_bytes(4, "little")
                else:
                    data[5 * 1024 : 6 * 1024] = bytes(1024)
                report = self.parse_fixture(folder, raw=data)
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(report.output_reports)
                path = Path(report.output_reports[0].file_reports[0].file_name)
                row = next(
                    json.loads(line)
                    for line in path.read_text().splitlines()
                    if json.loads(line).get("record_number") == 32
                )
                self.assertEqual(row["file_name"], "file8.txt")
                if damage == "root":
                    self.assertTrue(row["file_path"].startswith("\\$OrphanFiles\\"))

    def test_typed_fields_honor_mapping_renames_and_ignores(self):
        with TemporaryDirectory() as folder:
            config = ET.parse(CONFIG)
            config.find(".//field[@input='file_name']").set("output", "name")
            config.find(".//field[@input='owner_id']").set("parser", "Ignore")
            path = Path(folder) / "custom.xml"
            config.write(path)
            report = self.parse_fixture(folder, config=path)
            self.assertIsNone(report.last_error)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            row = next(
                json.loads(line)
                for line in path.read_text().splitlines()
                if json.loads(line).get("record_number") == 32
            )
            self.assertEqual(row["name"], "file8.txt")
            self.assertNotIn("file_name", row)
            self.assertNotIn("owner_id", row)

    def test_shared_values_match_an_ntfs_info_csv_export(self):
        with TemporaryDirectory() as folder:
            report = self.parse_fixture(folder)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            mft = next(
                json.loads(line)
                for line in path.read_text().splitlines()
                if json.loads(line).get("record_number") == 32
            )
            # Independently specified metadata of the upstream sample's file8.
            values = dict(
                ParentName="\\",
                File="file8.txt",
                Extension=".txt",
                SizeInBytes=357,
                RecordInUse="True",
                FRN="0x0003000000000020",
                Attributes="A",
                USN="0",
                FilenameFlags=3,
            )
            source = Path(folder) / "NTFSInfo.csv"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values))
                writer.writeheader()
                writer.writerow(values)
            conf = RunConfiguration([OutputConfiguration("csv-export", folder)])
            report = NTFSInfo().parse(
                str(source),
                str(ROOT / "configuration" / "ntfs_info.xml"),
                conf,
                Metadata("test"),
            )
            self.assertIsNone(report.last_error)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            ntfs = json.loads(path.read_text())
            names = [
                "file_path",
                "parent",
                "file_name",
                "extension",
                "file_size",
                "file_in_use",
                "sequence_number",
                "record_number",
                "usn_number",
                "file_name_flags",
            ]
            names += [name for name in ntfs if name.startswith("file_attributes_")]
            self.assertEqual(
                len([name for name in names if name.startswith("file_attributes_")]), 22
            )
            for name in names:
                with self.subTest(field=name):
                    self.assertEqual(mft[name], ntfs[name])
                    self.assertIs(type(mft[name]), type(ntfs[name]))
