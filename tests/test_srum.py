import glob
import hashlib
import json
import os
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from zipfile import ZipFile

import pyesedb
from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    PluginConfiguration,
    Record,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import Srum
from dfir_ogre_plugin_windows.srum import _read_value, _sid, parse_srum

from . import BASE_TEMP_FOLDER, CONF_FOLDER
from .srum_reference import output_cases, run_reference

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "srum")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class SrumTest(TestCase):
    @staticmethod
    def _parse(input_file, run_config, plugin_config, metadata):
        return Srum().parse(
            input_file, os.path.join(CONF_FOLDER, "srum.xml"), run_config, metadata
        )

    def test_all_outputs_match_rust_reference(self):
        self._assert_outputs_match(
            Path(DATA_FOLDER, "srum", "rust-baseline.json"),
            Path(DATA_FOLDER, "srum", "SRUDB.dat"),
        )

    def test_windows_11_2022_outputs_match_rust_reference(self):
        with TemporaryDirectory() as folder:
            database = Path(folder, "SRUDB.dat")
            with ZipFile(Path(DATA_FOLDER, "srum", "win11-2022.zip")) as archive:
                database.write_bytes(archive.read("SRUDB.dat"))
            self._assert_outputs_match(
                Path(DATA_FOLDER, "srum", "rust-baseline-win11-2022.json"), database
            )

    def _assert_outputs_match(self, reference_path, database):
        reference = json.loads(reference_path.read_text())
        self.assertEqual(
            hashlib.sha256(database.read_bytes()).hexdigest(),
            reference["database_sha256"],
        )
        with TemporaryDirectory() as folder:
            for name, options in output_cases():
                with self.subTest(output=name):
                    self.assertEqual(
                        run_reference(
                            self._parse, Path(folder, name), options, database=database
                        ),
                        reference["cases"][name],
                    )

    def test_uses_python_esedb_backend(self):
        with TemporaryDirectory() as folder:
            with patch("pyesedb.file", wraps=pyesedb.file) as open_database:
                run_reference(self._parse, folder, {})
            open_database.assert_called_once_with()

    def test_import_and_parse_without_common_srum_api(self):
        # A fresh interpreter catches imports as well as calls to the retired API.
        code = """
import sys
import dfir_ogre_common as common
if hasattr(common, 'parse_srum'):
    del common.parse_srum
from dfir_ogre_plugin_windows import Srum
report = Srum().parse(
    'tests/data/srum/SRUDB.dat', 'configuration/srum.xml',
    common.RunConfiguration([common.OutputConfiguration('srum', sys.argv[1])]),
    common.Metadata('test'),
)
assert report.num_errors == 0, report.last_error
assert sum(f.num_lines for o in report.output_reports for f in o.file_reports) == 2355
"""
        with TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-c", code, folder], capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_keyword_arguments_are_supported(self):
        with TemporaryDirectory() as folder:
            report = parse_srum(
                input_file=os.path.join(DATA_FOLDER, "srum", "SRUDB.dat"),
                configuration=RunConfiguration([OutputConfiguration("srum", folder)]),
                plugin_config=PluginConfiguration.load(
                    os.path.join(CONF_FOLDER, "srum.xml")
                ),
                metadata=Metadata("test"),
            )
            self.assertEqual(report.num_errors, 0, report.last_error)

    def test_missing_database_reports_error(self):
        with TemporaryDirectory() as folder:
            report = parse_srum(
                os.path.join(folder, "missing.dat"),
                RunConfiguration([OutputConfiguration("srum", folder)]),
                PluginConfiguration.load(os.path.join(CONF_FOLDER, "srum.xml")),
                Metadata("test"),
            )
            self.assertEqual(report.num_errors, 1)
            self.assertEqual(report.output_reports, [])

    def test_opens_windows_11_24h2_ese_before_srum_validation(self):
        # This is a real modern ESE database, but it contains BITS, not SRUM.
        # Reaching the ID-map check proves the plugin can open the page format.
        with TemporaryDirectory() as folder:
            database = Path(folder, "qmgr.db")
            with ZipFile(Path(DATA_FOLDER, "esedb", "qmgr-win11-24h2.zip")) as archive:
                database.write_bytes(archive.read("qmgr.db"))
            report = parse_srum(
                str(database),
                RunConfiguration([OutputConfiguration("srum", folder)]),
                PluginConfiguration.load(os.path.join(CONF_FOLDER, "srum.xml")),
                Metadata("test"),
            )
            self.assertEqual(report.num_errors, 1)
            self.assertIn("Missing SRUM SruDbIdMapTable", report.last_error)
            self.assertEqual(report.output_reports, [])

    def test_finalization_errors_are_reported(self):
        from dfir_ogre_plugin_windows import srum

        original = srum.Output

        class FailingOutput:
            def __init__(self, *args):
                self.output = original(*args)

            def __enter__(self):
                return self.output.__enter__()

            def __exit__(self, *args):
                self.output.__exit__(*args)
                raise OSError("forced finalization failure")

        with TemporaryDirectory() as folder:
            with patch.object(srum, "Output", FailingOutput):
                report = Srum().parse(
                    os.path.join(DATA_FOLDER, "srum", "SRUDB.dat"),
                    os.path.join(CONF_FOLDER, "srum.xml"),
                    RunConfiguration([OutputConfiguration("srum", folder)]),
                    Metadata("test"),
                )
            self.assertEqual(report.num_errors, 14)
            self.assertIn("forced finalization failure", report.last_error)
            self.assertEqual(len(report.output_reports), 14)
            self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 1660)

    def test_aliases_and_unmapped_columns_keep_typed_values(self):
        with TemporaryDirectory() as folder:
            xml = ET.parse(os.path.join(CONF_FOLDER, "srum.xml"))
            fields = xml.find("mapping/fields")
            app = fields.find("field[@input='AppId']")
            app.set("output", "application_alias")
            ET.SubElement(
                fields,
                "field",
                {"input": "AppId", "output": "application_copy", "parser": "String"},
            )
            fields.remove(fields.find("field[@input='InFocusS']"))
            config_file = Path(folder, "srum.xml")
            xml.write(config_file)
            report = Srum().parse(
                os.path.join(DATA_FOLDER, "srum", "SRUDB.dat"),
                str(config_file),
                RunConfiguration([OutputConfiguration("srum", folder)]),
                Metadata("test"),
            )
            self.assertEqual(report.num_errors, 0, report.last_error)
            path = Path(report.output_reports[0].file_reports[0].file_name)
            row = json.loads(path.read_text().splitlines()[0])
            self.assertEqual(row["application_alias"], row["application_copy"])
            self.assertNotIn("app_id", row)
            self.assertIsInstance(row["in_focus_s"], int)

    def test_record_error_retains_finalized_partial_output_and_other_tables(self):
        from dfir_ogre_plugin_windows import srum

        original = srum._read_value
        calls = 0

        def fail_second_record(row, position, name, index):
            nonlocal calls
            if position == 0:
                calls += 1
            if calls == 2:
                raise ValueError("unreadable record")
            return original(row, position, name, index)

        with TemporaryDirectory() as folder:
            with patch.object(srum, "_read_value", side_effect=fail_second_record):
                report = Srum().parse(
                    os.path.join(DATA_FOLDER, "srum", "SRUDB.dat"),
                    os.path.join(CONF_FOLDER, "srum.xml"),
                    RunConfiguration([OutputConfiguration("srum", folder)]),
                    Metadata("test"),
                )
            self.assertEqual(report.num_errors, 1)
            self.assertIn("unreadable record", report.last_error)
            self.assertEqual(len(report.output_reports), 14)
            first = report.output_reports[0].file_reports[0]
            self.assertEqual(first.num_lines, 1)
            self.assertEqual(len(Path(first.file_name).read_text().splitlines()), 1)
            self.assertEqual(report.output_reports[1].file_reports[0].num_lines, 562)

    # python -m unittest tests.test_srum.SrumTest.test_srum -v
    def test_srum(self):
        plugin_file = os.path.join(CONF_FOLDER, "srum.xml")
        input_file = os.path.join(DATA_FOLDER, "srum", "SRUDB.dat")
        base_output_name = "srum_test"

        output_file = os.path.join(TEMP_FOLDER, base_output_name)

        for f in glob.glob(output_file + "*"):
            os.remove(f)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=True,
        )

        run_config = RunConfiguration(
            [output_config],
            True,
        )
        metadata = Metadata("test")
        parser = Srum()
        self.assertEqual("Srum", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)

        expected_lines = 1660
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        with open(filename) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 3:
                    self.assertEqual(
                        jsoned["app_id"],
                        "!!svchost.exe!1972/12/14:16:22:50!1c364![LocalSystemNetworkRestricted] [WdiSystemHost]",
                    )
                i += 1
            self.assertEqual(i, expected_lines)


class SrumValueTest(TestCase):
    def read(self, column_type, data, name="Counter", index=None, **flags):
        row = Mock(spec=pyesedb.record)
        row.is_long_value.return_value = flags.get("long", False)
        row.is_multi_value.return_value = flags.get("multi", False)
        row.get_column_type.return_value = column_type
        row.get_value_data.return_value = data
        row.get_value_data_as_string.return_value = "text"
        record = Record()
        record.add("value", _read_value(row, 0, name, index or {}))
        return json.loads(record.to_string())["value"]

    def test_scalar_values_and_unsigned_binary_encoding(self):
        types = pyesedb.column_types
        cases = [
            (types.INTEGER_8BIT_UNSIGNED, b"\xff", 255),
            (types.INTEGER_16BIT_SIGNED, b"\xff\xff", -1),
            (types.INTEGER_32BIT_UNSIGNED, b"\xff" * 4, 4294967295),
            (types.INTEGER_64BIT_SIGNED, struct.pack("<q", -42), -42),
            (types.CURRENCY, struct.pack("<q", 12345), 12345),
            (types.BOOLEAN, b"\x01", True),
            (types.DOUBLE_64BIT, struct.pack("<d", 1.5), 1.5),
            (types.DATE_TIME, struct.pack("<q", 12345), 12345),
            (types.BINARY_DATA, b"\xfb\xff", "-_8"),
            (types.TEXT, b"text", "text"),
        ]
        for column_type, data, expected in cases:
            with self.subTest(column_type=column_type):
                self.assertEqual(self.read(column_type, data), expected)

    def test_null_long_and_multi_values(self):
        types = pyesedb.column_types
        self.assertIsNone(self.read(types.INTEGER_32BIT_SIGNED, None))
        self.assertIsNone(self.read(types.BINARY_DATA, b"abc", long=True))
        self.assertIsNone(self.read(types.BINARY_DATA, b"abc", multi=True))

    def test_id_resolution_and_missing_ids(self):
        column_type = pyesedb.column_types.INTEGER_32BIT_SIGNED
        self.assertEqual(
            self.read(column_type, struct.pack("<i", 7), "AppId", {7: "app"}), "app"
        )
        self.assertIsNone(
            self.read(column_type, struct.pack("<i", 8), "UserId", {7: "app"})
        )

    def test_sid_and_truncated_sid_match_common(self):
        self.assertEqual(_sid(bytes.fromhex("010100000000000512000000")), "S-1-5-18")
        self.assertEqual(_sid(b"\x01"), "S-1-")
        self.assertEqual(_sid(bytes.fromhex("010200000000000512000000")), "S-1-5-18")

    def test_timestamp_rounding_matches_rust(self):
        types = pyesedb.column_types
        self.assertEqual(
            self.read(
                types.DOUBLE_64BIT, struct.pack("<d", 44630.69097222222), "TimeStamp"
            ),
            "2022-03-10T16:34:59.999999+00:00",
        )
        # Retain the historical Rust FILETIME subsecond scaling during migration.
        self.assertEqual(
            self.read(
                types.INTEGER_64BIT_SIGNED,
                struct.pack("<Q", 116444736001234567),
                "ConnectStartTime",
            ),
            "1970-01-01T00:00:00.001234+00:00",
        )
        self.assertIsNone(
            self.read(types.INTEGER_32BIT_SIGNED, struct.pack("<i", 42), "TimeStamp")
        )

    def test_filetime_epoch_and_saturated_dates_match_rust(self):
        column_type = pyesedb.column_types.INTEGER_64BIT_SIGNED
        self.assertEqual(
            self.read(column_type, struct.pack("<q", 0), "ConnectStartTime"),
            "1601-01-01T00:00:00.000000+00:00",
        )
        self.assertEqual(
            self.read(column_type, struct.pack("<q", -1), "ConnectStartTime"),
            "9999-12-31T23:59:59.999999+00:00",
        )

    def test_nan_ole_timestamp_matches_rust_saturating_cast(self):
        self.assertEqual(
            self.read(
                pyesedb.column_types.DOUBLE_64BIT,
                struct.pack("<d", float("nan")),
                "TimeStamp",
            ),
            "1899-12-30T00:00:00.000000+00:00",
        )
