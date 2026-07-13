import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import XML

# Re‑use the temporary folder helpers used throughout the test suite.
from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "amcache")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class AmcacheProgramXmlTest(TestCase):


    #   python -m unittest tests.amcache_files.test_amcache_program_xml.AmcacheProgramXmlTest.test_aeinv_previous -v
    def test_aeinv_previous(self):

        plugin_file = os.path.join(CONF_FOLDER, "amcache_program_previous.xml")

        input_file = os.path.join(
            DATA_FOLDER, "aeinv", "AEINV_PREVIOUS.xml"
        )

        base_output_name = "amcache_program_aeinv_previous"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.amcache_program_xml.jsonl"
        )
        # Ensure a clean run.
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=True,
        )

        metadata = Metadata("test")
        parser = XML()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)

        file_report = report.output_reports[0].file_reports[0]
        self.assertEqual(file_report.num_lines,6)

        self.assertEqual(file_report.file_name, output_file)

        with open(output_file) as fp:
            first_line = fp.readline().strip()
            jsoned = json.loads(first_line)

            self.assertIn("id", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("version", jsoned)
            self.assertIn("publisher", jsoned)

            self.assertEqual(
                jsoned["source"],
                "AddRemoveProgram",
                "Source should reflect the @Source attribute of the first Program node",
            )

            second_line = fp.readline().strip()
            jsoned = json.loads(second_line)

            self.assertIn("id", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("version", jsoned)
            self.assertIn("publisher", jsoned)

            self.assertEqual(
                jsoned["name"],
                "Mozilla Maintenance Service",
                "Source should reflect the @Source attribute of the first Program node",
            )

    #   python -m unittest tests.amcache_files.test_amcache_program_xml.AmcacheProgramXmlTest.test_aeinv_wer -v
    def test_aeinv_wer(self):

        plugin_file = os.path.join(CONF_FOLDER, "amcache_program_wer.xml")

        input_file = os.path.join(
            DATA_FOLDER, "aeinv", "AEINV_AMI_WER_{32781662-3DBD-4055-A94B-4CE805656B08}_20190102_131746.xml"
        )

        base_output_name = "amcache_program_wer"
        output_file = os.path.join(
            TEMP_FOLDER, f"{base_output_name}.amcache_program_xml.jsonl"
        )
        # Ensure a clean run.
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=True,
        )

        metadata = Metadata("test")
        parser = XML()

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)

        self.assertIsNone(report.last_error)

        file_report = report.output_reports[0].file_reports[0]
        self.assertEqual(file_report.num_lines,3)

        self.assertEqual(file_report.file_name, output_file)

        with open(output_file) as fp:
            first_line = fp.readline().strip()
            jsoned = json.loads(first_line)

            self.assertIn("id", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("version", jsoned)
            self.assertIn("publisher", jsoned)

            self.assertEqual(
                jsoned["source"],
                "File",
                "Source should reflect the @Source attribute of the first Program node",
            )

            second_line = fp.readline().strip()
            jsoned = json.loads(second_line)

            self.assertIn("id", jsoned)
            self.assertIn("name", jsoned)
            self.assertIn("version", jsoned)
            self.assertIn("publisher", jsoned)
            self.assertEqual(len(jsoned["files"]),26)
            self.assertEqual(
                jsoned["source"],
                "AddRemoveProgram",
                "Source should reflect the @Source attribute of the first Program node",
            )

    # python -m unittest tests.amcache_files.test_amcache_program_xml.AmcacheProgramXmlTest.test_compatibility_report -v
    def test_compatibility_report(self):

      plugin_file = os.path.join(CONF_FOLDER, "amcache_program_report.xml")

      input_file = os.path.join(
          DATA_FOLDER, "aeinv", "FullCompatReport.xml"
      )

      base_output_name = "amcache_program_compat"
      output_file = os.path.join(
          TEMP_FOLDER, f"{base_output_name}.amcache_program_xml.jsonl"
      )
      # Ensure a clean run.
      if os.path.exists(output_file):
          os.remove(output_file)

      output_config = OutputConfiguration(
        base_output_name,
        TEMP_FOLDER,
        with_timeline=False,
        include_empty=True,
      )

      metadata = Metadata("test")
      parser = XML()

      run_config = RunConfiguration([output_config])
      report = parser.parse(input_file, plugin_file, run_config, metadata)

      self.assertIsNone(report.last_error)

      file_report = report.output_reports[0].file_reports[0]
      self.assertEqual(file_report.num_lines,4)

      self.assertEqual(file_report.file_name, output_file)

      with open(output_file) as fp:
          first_line = fp.readline().strip()
          jsoned = json.loads(first_line)

          self.assertIn("id", jsoned)
          self.assertIn("name", jsoned)
          self.assertIn("version", jsoned)
          self.assertIn("publisher", jsoned)

          self.assertEqual(
              jsoned["source"],
              "AddRemoveProgram",
              "Source should reflect the @Source attribute of the first Program node",
          )

          second_line = fp.readline().strip()
          jsoned = json.loads(second_line)

          self.assertIn("id", jsoned)
          self.assertIn("name", jsoned)
          self.assertIn("version", jsoned)
          self.assertIn("publisher", jsoned)

          self.assertEqual(
              jsoned["name"],
              "Oracle VM VirtualBox Guest Additions 5.0.40"

          )
