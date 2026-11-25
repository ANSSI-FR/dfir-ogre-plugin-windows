import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegServicesControlSet, RegSnapExclude

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


def run(parser, descriptor: str, base_output_name: str, data_type: str) -> list[dict]:
    output_file = os.path.join(TEMP_FOLDER, f"{base_output_name}.{data_type}.jsonl")
    if os.path.exists(output_file):
        os.remove(output_file)
    run_config = RunConfiguration([OutputConfiguration(base_output_name, TEMP_FOLDER)])
    report = parser.parse(
        os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat"),
        os.path.join(CONF_FOLDER, descriptor),
        run_config,
        Metadata("test"),
    )
    assert report.last_error is None
    with open(output_file) as fp:
        return [json.loads(line) for line in fp]


class MultiString(TestCase):
    """REG_MULTI_SZ values are emitted as JSON arrays, not as Python list text."""

    # python -m unittest tests.hive.test_multi_string.MultiString.test_services -v
    def test_services(self):
        rows = run(
            RegServicesControlSet(),
            "services_control_set.xml",
            "multi_string_services",
            "services_control_set",
        )
        for field in ("depend_on_service", "depend_on_group", "required_privileges"):
            values = [row[field] for row in rows if row.get(field)]
            self.assertTrue(values, field)
            for value in values:
                self.assertIsInstance(value, list, field)
                for item in value:
                    self.assertIsInstance(item, str, field)
                    self.assertFalse(item.startswith("["), field)

        dependencies = {row["name"]: row.get("depend_on_service") for row in rows}
        self.assertIn(["RPCSS", "HTTP"], dependencies.values())

    # python -m unittest tests.hive.test_multi_string.MultiString.test_snapshot_exclude -v
    def test_snapshot_exclude(self):
        rows = run(
            RegSnapExclude(), "snapshot_exclude.xml", "multi_string_exclude", "backup_exclude"
        )
        self.assertTrue(rows)
        for row in rows:
            self.assertIsInstance(row["file_path"], list)
            for item in row["file_path"]:
                self.assertFalse(item.startswith("["))
                self.assertNotIn("\\\\", item.replace("\\\\?\\", ""))
