import json
import os
import csv
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import NTFSInfo

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "csv")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class NtfsInfoTest(TestCase):
    #  python -m unittest tests.test_ntfs_info.NtfsInfoTest.test_ntfs_info -v
    def test_ntfs_info(self):
        plugin_file = os.path.join(CONF_FOLDER, "ntfs_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "NTFSInfo.csv")
        base_output_name = "ntfsinfo_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".ntfsinfo.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        plugin_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = NTFSInfo()
        self.assertEqual("NTFSInfo", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, plugin_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 5)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i < 3:
                    self.assertEqual(
                        jsoned["data"]["authenticode_ca_thumbprint"], ["hello", "world"]
                    )
                    self.assertEqual(jsoned["data"]["file_attributes_hidden"], True)
                    self.assertEqual(
                        jsoned["data"]["file_attributes_sparse_file"], False
                    )
                    self.assertEqual(jsoned["data"]["sequence_number"], 5)
                    self.assertEqual(jsoned["data"]["record_number"], 5)
                    self.assertEqual(
                        jsoned["data"]["snapshot_id"],
                        "{00000000-0000-0000-0000-000000000000}",
                    )

                i += 1
            self.assertEqual(i, 5)

    #  python -m unittest tests.test_ntfs_info.NtfsInfoTest.test_ntfs_info_1000 -v
    def test_ntfs_info_1000(self):
        plugin_file = os.path.join(CONF_FOLDER, "ntfs_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "NTFSInfo_1000.csv")
        base_output_name = "ntfsinfo_1000_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".ntfsinfo.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = NTFSInfo()
        self.assertEqual("NTFSInfo", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        print(report.last_error)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 999)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 609:
                    self.assertEqual(
                        jsoned["pe_compilation_date"],
                        "2022-12-14T05:55:43.000000+00:00",
                    )
                    self.assertEqual(jsoned["pe_companyname"], "Microsoft Corporation")

                i += 1
            self.assertEqual(i, 999)


    #  python -m unittest tests.test_ntfs_info.NtfsInfoTest.test_ntfs_info_csv -v
    def test_ntfs_info_csv(self):
        plugin_file = os.path.join(CONF_FOLDER, "ntfs_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "NTFSInfo.csv")
        base_output_name = "ntfsinfo_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".ntfsinfo.csv"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          format="csv",
          with_timeline=False,
                    include_empty=True,
        )

        plugin_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = NTFSInfo()
        self.assertEqual("NTFSInfo", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, plugin_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 3)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            csv_file = csv.reader(fp, delimiter=";", strict=True)
            i = 0
            for line in csv_file:
                if i == 1:
                  self.assertEqual(line[54], "[\"hello\",\"world\"]")
                i += 1
            self.assertEqual(i, 4)


    #  python -m unittest tests.test_ntfs_info.NtfsInfoTest.test_ntfs_info_timeline_csv -v
    def test_ntfs_info_timeline_csv(self):
        plugin_file = os.path.join(CONF_FOLDER, "ntfs_info.xml")
        input_file = os.path.join(DATA_FOLDER, "csv", "NTFSInfo.csv")
        base_output_name = "ntfsinfo_output"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".ntfsinfo.csv"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          format="csv",
          with_timeline=True,
                    include_empty=True,
        )

        plugin_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = NTFSInfo()
        self.assertEqual("NTFSInfo", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, plugin_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 5)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            csv_file = csv.reader(fp, delimiter=";", strict=True)
            i = 0
            for _ in csv_file:
                i += 1
            self.assertEqual(i, 6)
