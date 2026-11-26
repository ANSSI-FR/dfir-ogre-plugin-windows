import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration


from src.dfir_ogre_plugin_windows import XML,FastFind

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "fastfind")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestFastfind(TestCase):
    def _parse_xml(self, text, configuration, parser):
        with tempfile.TemporaryDirectory(prefix="ogre-fastfind-test-") as temporary:
            root = Path(temporary)
            source = root / "FastFind.xml"
            source.write_text(text, encoding="utf-8")
            output = OutputConfiguration("record", str(root), with_timeline=False)
            report = parser.parse(
                str(source),
                os.path.join(CONF_FOLDER, configuration),
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

    def test_fastfind_filesystem_preserves_fractional_precision(self):
        report, records = self._parse_xml(
            """<fast_find><filesystem><filefind_match><record>
              <standardinformation creation="2026-07-20 12:00:00.548" />
              <filename creation="2026-07-20 12:00:00.123456" />
              <i30 creation="2026-07-20 12:00:00.987654" />
            </record></filefind_match></filesystem></fast_find>""",
            "fastfind_file.xml",
            FastFind(),
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["si_creation_date"], "2026-07-20T12:00:00.548000+00:00")
        self.assertEqual(records[0]["fn_creation_date"], "2026-07-20T12:00:00.123456+00:00")
        self.assertEqual(records[0]["i30_creation"], "2026-07-20T12:00:00.987654+00:00")

    def test_fastfind_registry_preserves_fractional_precision(self):
        report, records = self._parse_xml(
            """<fast_find><registry><hive><regfind_match>
              <key lastmodified_key="2026-07-20 12:00:00.548" />
              <value lastmodified_key="2026-07-20 12:00:00.123456" />
            </regfind_match></hive></registry></fast_find>""",
            "fastfind_registry.xml",
            XML(),
        )

        self.assertIsNone(report.last_error)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["key"][0]["lastmodified_key"], "2026-07-20T12:00:00.548000+00:00"
        )
        self.assertEqual(
            records[0]["value"][0]["lastmodified_key"], "2026-07-20T12:00:00.123456+00:00"
        )

    # python -m unittest tests.test_fastfind.TestFastfind.test_fastfind_object -v
    def test_fastfind_object(self):
        plugin_file = os.path.join(CONF_FOLDER, "fastfind_object.xml")
        input_file = os.path.join(
            DATA_FOLDER, "xml", "FastFind_result.xml"
        )

        base_output_name = "ffobj"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".fastfind_obj.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        metadata = Metadata("test")
        parser = XML()
        self.assertEqual("XML", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        # Some builtin data don't not have dates
        self.assertEqual(
            None, report.last_error
        )

        expected_lines = 8
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)



        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 6:
                    self.assertEqual(
                        js["description"],
                        "Device'name is Ntfs",
                    )
                    self.assertEqual(
                        js["object"][0]["name"],
                        "Ntfs",
                    )
                i += 1
            self.assertEqual(i, expected_lines)


    # python -m unittest tests.test_fastfind.TestFastfind.test_fastfind_registry -v
    def test_fastfind_registry(self):
        plugin_file = os.path.join(CONF_FOLDER, "fastfind_registry.xml")
        input_file = os.path.join(
            DATA_FOLDER, "xml", "FastFind_result.xml"
        )

        base_output_name = "ffobj"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".fastfind_reg.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        metadata = Metadata("test")
        parser = XML()
        self.assertEqual("XML", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        # Some builtin data don't not have dates
        self.assertEqual(
            None, report.last_error
        )

        expected_lines = 7
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)

                if i == 2:
                    self.assertEqual(
                        js["description"],
                        "KeyPath matches regex \\\\Software(\\\\Wow6432Node)?\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run, Name matches regex .*",
                    )

                i += 1
            self.assertEqual(i, expected_lines)


    # python -m unittest tests.test_fastfind.TestFastfind.test_fastfind_filesystem -v
    def test_fastfind_filesystem(self):
        plugin_file = os.path.join(CONF_FOLDER, "fastfind_file.xml")
        input_file = os.path.join(
            DATA_FOLDER, "xml", "FastFind_result.xml"
        )

        base_output_name = "fffile_system"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".fastfind_file.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=False,
        )

        metadata = Metadata("test")
        parser = FastFind()
        self.assertEqual("FastFind", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        # Some builtin data don't not have dates
        self.assertEqual(
            None, report.last_error
        )

        expected_lines = 196
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
                      js["timestamp_meaning"],
                      "$SI:MACB - $FN:MACB",
                  )
                  self.assertEqual(
                      js["description"],
                      "\\$Volume",
                  )
                  self.assertEqual(
                      js["additional_description"],
                      "Size=0, SHA1=DA39A3EE5E6B4B0D3255BFEF95601890AFD80709",
                  )

                i += 1
            self.assertEqual(i, expected_lines)
