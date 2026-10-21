"""Synthetic logical tagged-energy rows, not a real on-disk ESE fixture.

Native read accessors are substituted because no redistributable tagged-energy
sample is available. ID resolution, typed conversion, XML mapping, output and
timeline creation all run through the production code.
"""

import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import pyesedb
from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    PluginConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import srum


def logical_table(names, types, values):
    table = Mock(spec=pyesedb.table)
    table.get_number_of_columns.return_value = len(names)
    table.get_column.side_effect = lambda position: Mock(
        get_name=lambda: names[position]
    )
    records = []
    for data in values:
        row = Mock(spec=pyesedb.record)
        row.get_column_type.side_effect = types.__getitem__
        row.is_long_value.return_value = False
        row.is_multi_value.return_value = False
        row.get_value_data_flags.return_value = 0
        row.get_value_data.side_effect = data.__getitem__
        row.get_value_data_as_integer.side_effect = (
            lambda position, data=data: int.from_bytes(
                data[position], "little", signed=True
            )
        )
        records.append(row)
    table.get_number_of_records.return_value = len(records)
    table.get_record.side_effect = records.__getitem__
    return table


class SyntheticTaggedEnergyTest(TestCase):
    def test_tagged_energy_mapping_ids_payload_and_timeline(self):
        types = pyesedb.column_types
        integer = types.INTEGER_32BIT_SIGNED
        binary = types.BINARY_DATA
        index = logical_table(
            ["IdType", "IdIndex", "IdBlob"],
            [integer, integer, binary],
            [
                [struct.pack("<i", 0), struct.pack("<i", 7), b"app.exe\0"],
                [
                    struct.pack("<i", 3),
                    struct.pack("<i", 8),
                    bytes.fromhex("010100000000000512000000"),
                ],
            ],
        )
        tagged = logical_table(
            ["AutoIncId", "TimeStamp", "AppId", "UserId", "OpaquePayload"],
            [integer, types.DATE_TIME, integer, integer, binary],
            [
                [
                    struct.pack("<i", 1),
                    struct.pack("<d", 25569),
                    struct.pack("<i", 7),
                    struct.pack("<i", 8),
                    b"\xfb\xff",
                ]
            ],
        )
        database = Mock(spec=pyesedb.file)
        database.get_table_by_name.side_effect = {
            "SruDbIdMapTable": index,
            "{B6D82AF1-F780-4E17-8077-6CB9AD8A6FC4}": tagged,
        }.get
        for timeline in (False, True):
            with self.subTest(timeline=timeline), TemporaryDirectory() as folder:
                with patch.object(srum.pyesedb, "file", return_value=database):
                    report = srum.parse_srum(
                        "synthetic.dat",
                        RunConfiguration(
                            [
                                OutputConfiguration(
                                    "srum", folder, with_timeline=timeline
                                )
                            ]
                        ),
                        PluginConfiguration.load("configuration/srum.xml"),
                        Metadata("synthetic"),
                    )
                self.assertEqual(report.num_errors, 0, report.last_error)
                (record,) = (
                    Path(folder, "srum.srum_tagged_energy.jsonl")
                    .read_text()
                    .splitlines()
                )
                data = {
                    "incremental_id": 1,
                    "timestamp": "1970-01-01T00:00:00.000000+00:00",
                    "app_id": "app.exe",
                    "user_id": "S-1-5-18",
                    "opaque_payload": "-_8",
                }
                metadata = {"computer": "synthetic", "data_type": "srum_tagged_energy"}
                expected = (
                    {
                        "timestamp": data["timestamp"],
                        "timestamp_meaning": "timestamp",
                        "description": "app_id: app.exe",
                        "additional_description": "",
                        "related_user": "S-1-5-18",
                        "data_type": "srum_tagged_energy",
                        "metadata": metadata,
                        "data": data,
                    }
                    if timeline
                    else {**data, "ogre_md": metadata}
                )
                self.assertEqual(json.loads(record), expected)
        self.assertEqual(database.close.call_count, 2)
