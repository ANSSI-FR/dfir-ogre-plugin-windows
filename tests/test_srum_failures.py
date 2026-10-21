"""Malformed inputs and resource failures outside the successful SRUM fixtures."""

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


class SrumFailureTest(TestCase):
    def parse(self, database, folder, outputs=True):
        return srum.parse_srum(
            str(database),
            RunConfiguration([OutputConfiguration("srum", folder)] if outputs else []),
            PluginConfiguration.load("configuration/srum.xml"),
            Metadata("test"),
        )

    def test_corrupt_and_truncated_databases_report_errors_without_outputs(self):
        header = Path("tests/data/srum/SRUDB.dat").read_bytes()[:8192]
        for label, data in (
            ("empty", b""),
            ("signature", b"invalid" * 100),
            ("truncated", header),
        ):
            with self.subTest(label=label), TemporaryDirectory() as folder:
                database = Path(folder, "broken.dat")
                database.write_bytes(data)
                report = self.parse(database, folder)
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(report.last_error)
                self.assertEqual(report.output_reports, [])
                self.assertEqual(list(Path(folder).glob("*.jsonl")), [])

    def test_no_outputs_is_reported_before_opening_database(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(srum.pyesedb, "file") as factory,
        ):
            report = self.parse("unused.dat", folder, outputs=False)
        self.assertEqual(report.num_errors, 1)
        self.assertIn("at least one output", report.last_error)
        self.assertEqual(report.output_reports, [])
        factory.assert_not_called()

    def test_database_close_failure_retains_successful_outputs(self):
        native = pyesedb.file()
        database = Mock(spec=pyesedb.file, wraps=native)

        def fail_close():
            native.close()
            raise OSError("forced database close failure")

        database.close.side_effect = fail_close
        with (
            TemporaryDirectory() as folder,
            patch.object(srum.pyesedb, "file", return_value=database),
        ):
            report = self.parse("tests/data/srum/SRUDB.dat", folder)
        self.assertEqual(report.num_errors, 1)
        self.assertIn("forced database close failure", report.last_error)
        self.assertEqual(len(report.output_reports), 14)
        self.assertEqual(
            sum(f.num_lines for o in report.output_reports for f in o.file_reports),
            2355,
        )
        database.close.assert_called_once_with()

    def test_index_and_close_failures_are_both_reported(self):
        native = pyesedb.file()
        database = Mock(spec=pyesedb.file, wraps=native)
        database.get_table_by_name.side_effect = ValueError("unreadable ID map")

        def fail_close():
            native.close()
            raise OSError("forced database close failure")

        database.close.side_effect = fail_close
        with (
            TemporaryDirectory() as folder,
            patch.object(srum.pyesedb, "file", return_value=database),
        ):
            report = self.parse("tests/data/srum/SRUDB.dat", folder)
        self.assertEqual(report.num_errors, 2)
        self.assertIn("forced database close failure", report.last_error)
        self.assertEqual(report.output_reports, [])
        database.close.assert_called_once_with()


def index_row(id_type=0, index=7, blob=b"app\0", column_types=None, compressed=False):
    row = Mock(spec=pyesedb.record)
    row.is_long_value.return_value = False
    row.is_multi_value.return_value = False
    types = pyesedb.column_types
    columns = column_types or (
        types.INTEGER_32BIT_SIGNED,
        types.INTEGER_32BIT_SIGNED,
        types.BINARY_DATA,
    )
    row.get_column_type.side_effect = columns.__getitem__
    row.get_value_data_as_integer.side_effect = [id_type, index]
    row.get_value_data.return_value = blob
    row.get_value_data_flags.return_value = 2 if compressed else 0
    return row


def index_database(rows):
    table = Mock(spec=pyesedb.table)
    table.get_number_of_records.return_value = len(rows)
    table.get_record.side_effect = rows
    database = Mock(spec=pyesedb.file)
    database.get_table_by_name.return_value = table
    return database


class SrumIndexFailureTest(TestCase):
    def test_invalid_index_records_do_not_hide_later_valid_record(self):
        types = pyesedb.column_types
        cases = [
            {"id_type": None},
            {"index": None},
            {"blob": None},
            {"id_type": -1},
            {"id_type": 1 << 32},
            {"index": -(1 << 31) - 1},
            {"index": 1 << 31},
            {
                "column_types": (
                    types.TEXT,
                    types.INTEGER_32BIT_SIGNED,
                    types.BINARY_DATA,
                )
            },
            {
                "column_types": (
                    types.INTEGER_32BIT_SIGNED,
                    types.TEXT,
                    types.BINARY_DATA,
                )
            },
            {
                "column_types": (
                    types.INTEGER_32BIT_SIGNED,
                    types.INTEGER_32BIT_SIGNED,
                    types.TEXT,
                )
            },
        ]
        # Distinct IDs prevent the valid row from overwriting an accepted bad row.
        invalid = [
            index_row(**{"index": 100 + number, **case})
            for number, case in enumerate(cases)
        ]
        self.assertEqual(
            srum._load_index(index_database(invalid + [index_row()])), {7: "app"}
        )

    def test_id_map_decodes_compressed_blobs_and_sids_and_keeps_last_duplicate(self):
        rows = [
            index_row(blob=b"replaced"),
            index_row(blob=bytes.fromhex("18030000000000616263"), compressed=True),
            index_row(
                id_type=3, index=8, blob=bytes.fromhex("010100000000000512000000")
            ),
            index_row(index=9, blob=b"a\0\xff\0"),
        ]
        self.assertEqual(
            srum._load_index(index_database(rows)),
            {7: "abc", 8: "S-1-5-18", 9: "a\ufffd"},
        )

    def test_malformed_compressed_id_map_closes_database_and_reports_error(self):
        database = index_database([index_row(blob=b"\x18", compressed=True)])
        with (
            TemporaryDirectory() as folder,
            patch.object(srum.pyesedb, "file", return_value=database),
        ):
            report = srum.parse_srum(
                "synthetic.dat",
                RunConfiguration([OutputConfiguration("srum", folder)]),
                PluginConfiguration.load("configuration/srum.xml"),
                Metadata("test"),
            )
        self.assertEqual(report.num_errors, 1)
        self.assertIn("Truncated compressed ESE LZXPRESS", report.last_error)
        self.assertEqual(report.output_reports, [])
        database.close.assert_called_once_with()
