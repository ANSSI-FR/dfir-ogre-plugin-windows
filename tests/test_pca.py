import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegExp

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "pca")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestPca(TestCase):
    def _parse_app_launch_lines(self, lines):
        with tempfile.TemporaryDirectory(prefix="ogre-pca-test-") as temporary:
            root = Path(temporary)
            source = root / "PcaAppLaunchDic.txt"
            source.write_text(lines, encoding="utf-8")
            output = OutputConfiguration("record", str(root), with_timeline=False)
            report = RegExp().parse(
                str(source),
                os.path.join(CONF_FOLDER, "pca_app_launch.xml"),
                RunConfiguration([output]),
                Metadata("test"),
            )
            records = [
                json.loads(row)
                for group in report.output_reports
                for file in group.file_reports
                for row in Path(file.file_name).read_text().splitlines()
            ]
            return report, records

    def _parse_general_line(self, line):
        with tempfile.TemporaryDirectory(prefix="ogre-pca-test-") as temporary:
            root = Path(temporary)
            source = root / "PcaGeneralDb.txt"
            source.write_text(line, encoding="utf-16-le")
            output = OutputConfiguration("record", str(root), with_timeline=False)
            report = RegExp().parse(
                str(source),
                os.path.join(CONF_FOLDER, "pca_general_record.xml"),
                RunConfiguration([output]),
                Metadata("test"),
            )
            records = [
                json.loads(row)
                for group in report.output_reports
                for file in group.file_reports
                for row in Path(file.file_name).read_text().splitlines()
            ]
            return report, records

    def test_app_launch_preserves_full_paths(self):
        for path in (
            r"c:\Tools\app.exe",
            r"C:\Program Files\Tool\app.exe",
            r"\\server\share\app.exe",
            r"%programfiles%\Tool\app.exe",
        ):
            for ending in ("\n", "\r\n", ""):
                with self.subTest(path=path, ending=ending):
                    report, records = self._parse_app_launch_lines(
                        path + "|2026-07-20 12:00:00.548" + ending
                    )

                    self.assertIsNone(report.last_error)
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]["executable_path"], path)

    def test_app_launch_preserves_millisecond_precision(self):
        report, records = self._parse_app_launch_lines(
            "C:\\Tools\\app.exe|2026-07-20 12:00:00.548\n"
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["timestamp"], "2026-07-20T12:00:00.548000+00:00")

    def test_app_launch_skips_malformed_rows(self):
        valid = "C:\\Tools\\valid.exe|2026-07-20 12:00:00.548"
        for malformed in (
            "|2026-07-20 12:00:00.548",
            "C:\\Tools\\app.exe",
            "C:\\Tools\\app.exe|2026-07-20 12:00:00x548",
            "C:\\Tools\\app.exe|2026-07-20 12:00:00.548|extra",
            "prefix|C:\\Tools\\app.exe|2026-07-20 12:00:00.548",
        ):
            with self.subTest(malformed=malformed):
                report, records = self._parse_app_launch_lines(
                    malformed + "\r\n" + valid + "\n"
                )

                self.assertIsNone(report.last_error)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["executable_path"], r"C:\Tools\valid.exe")

    def test_general_records_preserve_millisecond_precision(self):
        report, records = self._parse_general_line(
            "2026-07-20 12:00:00.548|2|C:\\Tools\\app.exe|||||\n"
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["run_time"], "2026-07-20T12:00:00.548000+00:00")

    def test_general_records_allow_empty_optional_fields(self):
        fields = [
            "2026-07-20 12:00:00.123", "2", r"C:\Tools\app.exe",
            "Tool", "Vendor", "1.0", "a" * 44, "Process exited with code 0x0",
        ]
        names = ["file_description", "software_vendor", "file_version", "program_id", "exitcode_value"]
        for empty_fields in [(index,) for index in range(3, 8)] + [tuple(range(3, 8))]:
            for ending in ("\n", "\r\n", ""):
                with self.subTest(empty_fields=empty_fields, ending=ending):
                    expected = fields.copy()
                    for index in empty_fields:
                        expected[index] = ""
                    report, records = self._parse_general_line("|".join(expected) + ending)

                    self.assertIsNone(report.last_error)
                    self.assertEqual(len(records), 1)
                    record = records[0]
                    self.assertEqual(record["executable_path"], r"C:\Tools\app.exe")
                    self.assertEqual(record["run_status"], 2)
                    self.assertTrue(record["run_time"].startswith("2026-07-20T12:00:00"))
                    for name, expected_value in zip(names, expected[3:]):
                        self.assertEqual(record[name], expected_value)

    def test_general_records_allow_description_punctuation(self):
        report, records = self._parse_general_line(
            "2026-07-20 12:00:00.123|2|C:\\Tools\\app.exe|Tool - x64 (v1.0)|Vendor|1.0|"
            + "a" * 44 + "|Process exited with code 0x0\r\n"
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["file_description"], "Tool - x64 (v1.0)")
        self.assertEqual(records[0]["exitcode_value"], "Process exited with code 0x0")

    def test_general_records_reject_malformed_structure(self):
        for line in (
            "2026-07-20 12:00:00.123|2|C:\\Tools\\app.exe",
            "2026-07-20 12:00:00.123|2||||||",
            "2026-07-20 12:00:00.123|bad|C:\\Tools\\app.exe|||||",
        ):
            with self.subTest(line=line):
                report, records = self._parse_general_line(line + "\n")

                self.assertIsNotNone(report.last_error)
                self.assertEqual(records, [])

    # python -m unittest tests.test_pca.TestPca.test_general_db0 -v
    def test_general_db0(self):
        plugin_file = os.path.join(CONF_FOLDER, "pca_general_record.xml")
        input_file = os.path.join(DATA_FOLDER, "pca", "PcaGeneralDb0.txt")

        base_output_name = "pca_general_0"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".pca_general_record.jsonl"
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
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 51
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
                        "executable_path: %programfiles%\\freefilesync\\freefilesync.exe",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "file_description: freefilesync",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_pca.TestPca.test_general_db1 -v
    def test_general_db1(self):
        plugin_file = os.path.join(CONF_FOLDER, "pca_general_record.xml")
        input_file = os.path.join(DATA_FOLDER, "pca", "PcaGeneralDb1.txt")

        base_output_name = "pca_general_1"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".pca_general_record.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        configuration = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, configuration, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 125
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
                        "executable_path: %programfiles%\\freefilesync\\freefilesync.exe",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "file_description: freefilesync",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_pca.TestPca.test_general_db2 -v
    def test_general_db2(self):
        plugin_file = os.path.join(CONF_FOLDER, "pca_general_record.xml")
        input_file = os.path.join(DATA_FOLDER, "pca", "PcaGeneralDb2.txt")

        base_output_name = "pca_general_2"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".pca_general_record.jsonl"
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
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 3
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
                        "executable_path: %programfiles%\\windowsapps\\microsoft.windowsterminal_1.12.10983.0_x64__8wekyb3d8bbwe\\wt.exe",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "file_description: windows terminal",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_pca.TestPca.test_app_launch0 -v
    def test_app_launch0(self):
        plugin_file = os.path.join(CONF_FOLDER, "pca_app_launch.xml")
        input_file = os.path.join(DATA_FOLDER, "pca", "PcaAppLaunchDic0.txt")

        base_output_name = "pca_app_launch_0"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".pca_app_launch.jsonl"
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
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        print(report.last_error)
        self.assertEqual(None, report.last_error)

        expected_lines = 6
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
                        "executable_path: C:\\Program Files\\WindowsApps\\MicrosoftTeams_22248.701.1548.6610_x64__8wekyb3d8bbwe\\msteams.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_pca.TestPca.test_app_launch1 -v
    def test_app_launch1(self):
        plugin_file = os.path.join(CONF_FOLDER, "pca_app_launch.xml")
        input_file = os.path.join(DATA_FOLDER, "pca", "PcaAppLaunchDic1.txt")

        base_output_name = "pca_app_launch_1"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".pca_app_launch.jsonl"
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
        parser = RegExp()
        self.assertEqual("Regexp", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        print(report.last_error)
        self.assertEqual(None, report.last_error)

        expected_lines = 55
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
                        "executable_path: C:\\ProgramData\\Sophos\\AutoUpdate\\Cache\\sophos_autoupdate1.dir\\su-setup32.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
