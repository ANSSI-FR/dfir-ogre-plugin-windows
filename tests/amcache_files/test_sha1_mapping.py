import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from xml.etree import ElementTree as ET

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import XML

from . import CONF_FOLDER


class AmcacheSha1MappingTest(TestCase):
    # The program identifier deliberately resembles a file identifier: only
    # the nested file IDs should be normalized by the shared @Id callback.
    PROGRAM_ID = "0000D14DF5EA9601CA2981074516BDA8F5226A5C735B"
    CASES = (
        ("0000D14DF5EA9601CA2981074516BDA8F5226A5C735B", "d14df5ea9601ca2981074516bda8f5226a5c735b"),
        ("D14DF5EA9601CA2981074516BDA8F5226A5C735B", "d14df5ea9601ca2981074516bda8f5226a5c735b"),
        ("0000not-a-sha1", "0000not-a-sha1"),
        ("FFFFD14DF5EA9601CA2981074516BDA8F5226A5C735B", "FFFFD14DF5EA9601CA2981074516BDA8F5226A5C735B"),
        ("", None),
        (None, None),
    )

    def parse_xml(self, descriptor, data_type, root):
        with TemporaryDirectory() as folder:
            input_path = Path(folder, "input.xml")
            ET.ElementTree(root).write(input_path, encoding="utf-8")
            report = XML().parse(
                str(input_path),
                str(Path(CONF_FOLDER, descriptor)),
                RunConfiguration([OutputConfiguration("hashes", folder)]),
                Metadata("test"),
            )
            self.assertIsNone(report.last_error)
            return [
                json.loads(line)
                for line in Path(folder, f"hashes.{data_type}.jsonl").read_text().splitlines()
            ]

    def test_driver_and_installer_hashes_preserve_malformed_and_missing_values(self):
        for kind, descriptor in (
            ("Driver", "amcache_driver_xml.xml"),
            ("Installer", "amcache_installer_xml.xml"),
        ):
            with self.subTest(kind=kind):
                root = ET.Element("Report")
                for index, (raw, _) in enumerate(self.CASES):
                    node = ET.SubElement(root, kind, Name=f"item-{index}")
                    if kind == "Installer":
                        node = ET.SubElement(node, "InstallInfo")
                    if raw is not None:
                        node.set("DriverId" if kind == "Driver" else "Id", raw)
                rows = self.parse_xml(descriptor, f"amcache_{kind.lower()}_xml", root)
                self.assertEqual(len(rows), len(self.CASES))
                self.assertCountEqual(
                    [row["sha1"] for row in rows],
                    [expected for _, expected in self.CASES],
                )

    def test_all_program_mappings_normalize_nested_hashes_and_preserve_program_id(self):
        for descriptor, parent_path in (
            ("amcache_program_previous.xml", ("ProgramList",)),
            ("amcache_program_report.xml", ("Programs",)),
            ("amcache_program_wer.xml", ("ProgramList", "Installed")),
        ):
            with self.subTest(descriptor=descriptor):
                root = ET.Element("Report")
                parent = root
                for tag in parent_path:
                    parent = ET.SubElement(parent, tag)
                program = ET.SubElement(parent, "Program", Id=self.PROGRAM_ID)
                files = ET.SubElement(ET.SubElement(program, "StaticProperties"), "Files")
                for index, (raw, _) in enumerate(self.CASES):
                    file = ET.SubElement(files, "File", Name=f"item-{index}")
                    if raw is not None:
                        file.set("Id", raw)
                rows = self.parse_xml(descriptor, "amcache_program_xml", root)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["id"], self.PROGRAM_ID)
                self.assertEqual(
                    {file["name"]: file["sha1"] for file in rows[0]["files"]},
                    {f"item-{index}": expected for index, (_, expected) in enumerate(self.CASES)},
                )
