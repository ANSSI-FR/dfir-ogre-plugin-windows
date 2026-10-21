import json
import os
from tempfile import TemporaryDirectory
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import Prefetch

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "prefetch")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestPrefetch(TestCase):
    def test_real_fixtures_preserve_execution_and_volume_timestamps(self):
        # Constants checked against the uncompressed SCCA fields: version at
        # 0x00, hash at 0x4c, file count at 0x58, run FILETIMEs at 0x80,
        # run count at 0x98 (v23) / 0xc8 (v30), and volume FILETIME at +0x08.
        # W10/W11 MAM payloads were decompressed before checking these fields.
        fixtures = [
            (
                "W7", "AUTORUNSC.EXE-B8F1A907.pf", "23", 0xB8F1A907, 1, 81,
                ["2023-05-15T08:43:21.984500+00:00"],
                "2019-07-19T19:40:51.203125+00:00",
            ),
            (
                "W10-22H2", "CMD.EXE-6D6290C5.pf", "30", 0x6D6290C5, 5, 35,
                [
                    "2023-05-15T08:40:54.446173+00:00",
                    "2023-05-15T08:40:53.112308+00:00",
                    "2023-05-15T08:40:54.108794+00:00",
                    "2023-05-15T04:09:35.376210+00:00",
                    "2022-11-22T17:10:02.412455+00:00",
                ],
                "2022-11-23T01:16:52.550359+00:00",
            ),
            (
                "W11", "SVCHOST.EXE-5D15888E.pf", "30", 0x5D15888E, 15, 36,
                [
                    "2025-03-25T13:12:34.243100+00:00",
                    "2025-03-25T03:03:43.701998+00:00",
                    "2025-03-25T02:57:30.096721+00:00",
                    "2025-03-25T01:12:29.407418+00:00",
                    "2025-03-24T21:12:27.575237+00:00",
                    "2025-03-24T17:12:26.170562+00:00",
                    "2025-03-24T09:12:22.658276+00:00",
                    "2025-03-24T05:11:21.638772+00:00",
                ],
                "2021-06-30T18:49:56.891371+00:00",
            ),
        ]
        for fixture in fixtures:
            folder, filename, version, hash_value, runs, files, dates, volume_date = fixture
            with self.subTest(fixture=filename), TemporaryDirectory() as output_folder:
                metadata = Metadata("fixture-host")
                metadata.original_filename = rf"C:\Windows\Prefetch\{filename}"
                report = Prefetch().parse(
                    os.path.join(DATA_FOLDER, "prefetch", folder, filename),
                    os.path.join(CONF_FOLDER, "prefetch.xml"),
                    RunConfiguration([
                        OutputConfiguration("semantic", output_folder, with_timeline=True)
                    ]),
                    metadata,
                )
                self.assertIsNone(report.last_error)
                with open(
                    os.path.join(output_folder, "semantic.prefetch.jsonl"),
                    encoding="utf-8",
                ) as fp:
                    rows = [json.loads(line) for line in fp]

                run_rows = [
                    row for row in rows if row["timestamp_meaning"] == "run date"
                ]
                volume_rows = [
                    row for row in rows
                    if row["timestamp_meaning"] == "volume creation date"
                ]
                self.assertCountEqual([row["timestamp"] for row in run_rows], dates)
                self.assertEqual(len(rows), 2 * len(dates))
                self.assertEqual(len(volume_rows), len(dates))
                self.assertTrue(
                    all(row["timestamp"] == volume_date for row in volume_rows)
                )
                for row in rows:
                    data = row["data"]
                    self.assertEqual(row["data_type"], "prefetch")
                    self.assertEqual(row["metadata"]["computer"], "fixture-host")
                    self.assertEqual(
                        row["metadata"]["original_filename"], metadata.original_filename
                    )
                    self.assertEqual(data["version"], version)
                    self.assertEqual(data["prefetch_hash"], hash_value)
                    self.assertIs(type(data["prefetch_hash"]), int)
                    self.assertEqual(data["run_count"], runs)
                    self.assertIs(type(data["run_count"]), int)
                    self.assertEqual(data["file_count"], files)
                    self.assertEqual(len(data["files"]), files)
                    self.assertEqual(data["volume_count"], 1)
                    self.assertEqual(data["volumes"][0]["creation_time"], volume_date)
                for row in run_rows:
                    self.assertEqual(row["timestamp"], row["data"]["run_date"])

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w7 -v
    def test_prefetch_w7(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W7", "AUTORUNSC.EXE-B8F1A907.pf"
        )

        base_output_name = "prefetch_w7"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
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
                        "executable: AUTORUNSC.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\TEMP\\WORKINGTEMP\\AUTORUNSC.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w8_autoruns -v
    def test_prefetch_w8_autoruns(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W81", "AUTORUNSC.EXE-74270A5A.pf"
        )

        base_output_name = "prefetch_w8_autoruns"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
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
                        "executable: AUTORUNSC.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\TEMP\\AUTORUNSC.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w8_cmd -v
    def test_prefetch_w8_cmd(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(DATA_FOLDER, "prefetch", "W81", "CMD.EXE-CD245F9E.pf")

        base_output_name = "prefetch_w8_cmd"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
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
                        "executable: CMD.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\SYSTEM32\\CMD.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w10_autoruns -v
    def test_prefetch_w10_autoruns(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W10-22H2", "AUTORUNSC.EXE-C047C10D.pf"
        )

        base_output_name = "prefetch_w10_autoruns"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
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
                        "executable: AUTORUNSC.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\TEMP\\AUTORUNSC.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w10_cmd -v
    def test_prefetch_w10_cmd(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W10-22H2", "CMD.EXE-6D6290C5.pf"
        )

        base_output_name = "prefetch_w10_cmd"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 10
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
                        "executable: CMD.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\SYSWOW64\\CMD.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w10_orc -v
    def test_prefetch_w10_orc(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W10-22H2", "ORC_PTF2REF_10.1.7.EXE-BA772821.pf"
        )

        base_output_name = "prefetch_w10_orc"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
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
                        "executable: ORC_PTF2REF_10.1.7.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: []",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w10_dll -v
    def test_prefetch_w10_dll(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W10-22H2", "RUNDLL32.EXE-20A3C999.pf"
        )

        base_output_name = "prefetch_w10_dll"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
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
        parser = Prefetch()
        self.assertEqual("Prefetch", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 4
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
                        "executable: RUNDLL32.EXE",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "path_hints: [\\WINDOWS\\SYSTEM32\\RUNDLL32.EXE]",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_prefetch.TestPrefetch.test_prefetch_w11_more_runs_than_timestamps -v
    def test_prefetch_w11_more_runs_than_timestamps(self):
        plugin_file = os.path.join(CONF_FOLDER, "prefetch.xml")
        input_file = os.path.join(
            DATA_FOLDER, "prefetch", "W11", "SVCHOST.EXE-5D15888E.pf"
        )

        base_output_name = "prefetch_w11_more_runs_than_timestamps"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".prefetch.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )
        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = Prefetch()

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 8
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        with open(output_file) as fp:
            parsed_lines = [json.loads(line) for line in fp]

        self.assertEqual(len(parsed_lines), expected_lines)
        self.assertEqual(parsed_lines[0]["executable"], "SVCHOST.EXE")
        self.assertEqual(parsed_lines[0]["run_count"], 15)
