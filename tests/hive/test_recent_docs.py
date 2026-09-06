import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegRecentDocs

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class RecentDocs(TestCase):
    # python -m unittest tests.hive.test_recent_docs.RecentDocs.test_recent_docs -v
    def test_recent_docs(self):
        plugin_file = os.path.join(CONF_FOLDER, "recent_docs.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "NTUSER.dat")

        base_output_name = "recent_docs"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".recent_docs.jsonl"
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
        parser = RegRecentDocs()
        self.assertEqual("RegRecentDocs", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 10
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        rows = [rec["data"] for rec in records]

        # the root key lists recent items of every type; Folder lists folders
        self.assertEqual(sum(1 for r in rows if r["extension"] == ""), 8)
        self.assertEqual(sum(1 for r in rows if r["extension"] == "Folder"), 2)

        # the most recently opened root item is MRUListEx position 0
        newest = [
            rec
            for rec in records
            if rec["data"]["extension"] == "" and rec["data"]["mru_position"] == 0
        ]
        self.assertEqual(len(newest), 1)
        self.assertEqual(newest[0]["data"]["target"], "ms-gamingoverlay:///")
        self.assertEqual(newest[0]["data"]["index"], "7")
        self.assertEqual(newest[0]["description"], "target: ms-gamingoverlay:///")
