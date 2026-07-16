import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegClsIdIUser, RegClsIdSoftware

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class CLSID(TestCase):
    # python -m unittest tests.hive.test_clsid.CLSID.test_clsid_user -v
    def test_clsid_user(self):
        plugin_file = os.path.join(CONF_FOLDER, "clsid_users.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "UsrClass.dat")
        base_output_name = "clsid_user"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".clsid.jsonl"
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
        parser = RegClsIdIUser()
        self.assertEqual("RegClsIdIUser", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 32
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 0:
                    self.assertEqual(js["description"], "description: Bitmap Image")
                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.hive.test_clsid.CLSID.test_clsid_software -v
    def test_clsid_software(self):
        plugin_file = os.path.join(CONF_FOLDER, "clsid_software.xml")

        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")
        base_output_name = "clsid_software"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".clsid.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=False,
        )
        run_config = RunConfiguration([output_config])
        metadata = Metadata("test")
        parser = RegClsIdSoftware()
        self.assertEqual("RegClsIdSoftware", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 6764
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                js = json.loads(line)
                if i == 1:
                    self.assertEqual(
                        js["additional_description"],
                        "executable: C:\\Windows\\System32\\oleaut32.dll",
                    )
                if i == 53:
                    self.assertEqual(
                        js["data"]["treat_as"],
                        "{f20da720-c02f-11ce-927b-0800095ae340}",
                    )
                    self.assertEqual(
                        js["additional_description"],
                        "treat_as: {f20da720-c02f-11ce-927b-0800095ae340}",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
