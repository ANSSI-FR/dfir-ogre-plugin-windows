"""SRUM providers read with the same ESE engine as the other Windows plugins."""

import base64
import math
import struct
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pyesedb
from dfir_ogre_common import (
    DateInputCodec,
    Field,
    FieldMapping,
    FieldName,
    Metadata,
    OgrePlugin,
    Output,
    Parser,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
)


# Keep provider order and names compatible with the original Rust parser.
SRUM_TABLES = (
    ("srum_app_timeline", "{5C8CF1C7-7257-4F13-B223-970EF5939312}"),
    ("srum_application_resources", "{D10CA2FE-6FCF-4F6D-848E-B2E99266FA89}"),
    ("srum_energy_estimation", "{DA73FB89-2BEA-4DDC-86B8-6E048C6DA477}"),
    ("srum_energy_usage", "{FEE4E14F-02A9-4550-B5CE-5FA2DA202E37}"),
    ("srum_energy_usage_long_term", "{FEE4E14F-02A9-4550-B5CE-5FA2DA202E37}LT"),
    ("srum_network_connectivity_usage", "{DD6636C4-8929-4683-974E-22C046A43763}"),
    ("srum_network_data_usage", "{973F5D5C-1D90-4944-BE8E-24B94231A174}"),
    ("srum_sdp_volume", "{17F4D97B-F26A-5E79-3A82-90040A47D13D}"),
    ("srum_sdp_physical_disk", "{841A7317-3805-518B-C2EA-AD224CB4AF84}"),
    ("srum_sdp_cpu", "{DC3D3B50-BB90-5066-FA4E-A5F90DD8B677}"),
    ("srum_sdp_network", "{EEE2F477-0659-5C47-EF03-6D6BEFD441B3}"),
    ("srum_tagged_energy", "{B6D82AF1-F780-4E17-8077-6CB9AD8A6FC4}"),
    ("srum_vfuprov", "{7ACBBAA3-D029-4BE4-9A7A-0885927F1D8F}"),
    ("srum_wpn_provider", "{D10CA2FE-6FCF-4F6D-848E-B2E99266FA86}"),
)

_TYPES = pyesedb.column_types
_INTEGERS = {
    _TYPES.INTEGER_8BIT_UNSIGNED: "<B",
    _TYPES.INTEGER_16BIT_SIGNED: "<h",
    _TYPES.INTEGER_32BIT_SIGNED: "<i",
    _TYPES.INTEGER_64BIT_SIGNED: "<q",
    _TYPES.INTEGER_16BIT_UNSIGNED: "<H",
    _TYPES.INTEGER_32BIT_UNSIGNED: "<I",
    _TYPES.CURRENCY: "<q",
}
_BINARY = {
    _TYPES.BINARY_DATA,
    _TYPES.LARGE_BINARY_DATA,
    _TYPES.SUPER_LARGE_VALUE,
    _TYPES.GUID,
}
# Python datetime truncates nanoseconds, changing normalized record IDs. Use
# common's existing timestamp parser to retain the original typed Rust Date.
_DATE_PARSER = FieldMapping(
    [
        Field.Single(
            FieldName("date"), Parser.DateTime(DateInputCodec.TimestampNs()), None
        )
    ]
).get_parser("date")
_ISO_DATE_PARSER = FieldMapping(
    [Field.Single(FieldName("date"), Parser.DateTime(DateInputCodec.Iso()), None)]
).get_parser("date")


@lru_cache(maxsize=4096)
def _timestamp_value(data: bytes, column_type: int) -> Value:
    if column_type in (_TYPES.DOUBLE_64BIT, _TYPES.DATE_TIME):
        days = struct.unpack("<d", data)[0]
        # Match libesedb-rs/time's float multiplication and i64 saturation.
        total = days * 86_400_000_000_000
        elapsed = (
            0 if math.isnan(total) else int(max(-(1 << 63), min((1 << 63) - 1, total)))
        )
        nanoseconds = elapsed - 2_209_161_600_000_000_000
    elif column_type == _TYPES.INTEGER_64BIT_SIGNED:
        ticks = struct.unpack("<Q", data)[0]
        # Preserve the old Rust binding's subsecond scaling for output parity.
        # A correction to FILETIME rounding must be a separate behavior change.
        seconds, remainder = divmod(ticks, 10_000_000)
        nanoseconds = (seconds - 11_644_473_600) * 1_000_000_000 + remainder
    else:
        return Value.Null()
    if -(1 << 63) <= nanoseconds < (1 << 63):
        return _DATE_PARSER.parse_into_value(str(nanoseconds))
    # FILETIME zero (1601) predates the i64 Unix-nanosecond range. Parse ISO
    # with an explicit nanosecond suffix instead, retaining the same precision.
    nanoseconds = min(nanoseconds, 253_402_300_799_999_999_999)
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    date = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    text = date.strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction:09d}+00:00"
    return _ISO_DATE_PARSER.parse_into_value(text)


def _sid(data: bytes) -> str:
    # Match common.windows_utils.convert_sid, including partial/truncated SIDs.
    result = "S-1-"
    if len(data) < 8:
        return result
    result += str(int.from_bytes(data[2:8], "big"))
    for offset in range(8, 8 + data[1] * 4, 4):
        if len(data) < offset + 4:
            break
        result += "-" + str(int.from_bytes(data[offset : offset + 4], "little"))
    return result


def _load_index(database) -> dict[int, str]:
    table = database.get_table_by_name("SruDbIdMapTable")
    if table is None:
        raise ValueError("Missing SRUM SruDbIdMapTable")
    index = {}
    for position in range(table.get_number_of_records()):
        row = table.get_record(position)
        id_type = row.get_value_data_as_integer(0)
        id_index = row.get_value_data_as_integer(1)
        blob = row.get_value_data(2)
        if id_type is None or id_index is None or blob is None:
            continue
        # Keep the legacy decoding for this compatibility migration. Switching
        # IdBlob strings to UTF-16LE would change existing non-ASCII output.
        index[id_index] = (
            _sid(blob)
            if id_type == 3
            else blob.decode("utf-8", "replace").replace("\0", "")
        )
    return index


def _read_value(row, position: int, name: str, index: dict[int, str]) -> Value:
    # The Rust parser represents long and multi values as null.
    if row.is_long_value(position) or row.is_multi_value(position):
        return Value.Null()
    data = row.get_value_data(position)
    if data is None:
        return Value.Null()
    column_type = row.get_column_type(position)
    if name in ("AppId", "UserId"):
        format = _INTEGERS.get(column_type)
        number = struct.unpack(format, data)[0] if format else None
        text = index.get(number)
        return Value.String(text) if text is not None else Value.Null()
    if name in ("TimeStamp", "ConnectStartTime"):
        return _timestamp_value(data, column_type)
    if column_type in _INTEGERS:
        return Value.Int(struct.unpack(_INTEGERS[column_type], data)[0])
    if column_type == _TYPES.DATE_TIME:
        return Value.Int(struct.unpack("<q", data)[0])
    if column_type == _TYPES.BOOLEAN:
        return Value.Bool(bool(struct.unpack("<B", data)[0]))
    if column_type in (_TYPES.FLOAT_32BIT, _TYPES.DOUBLE_64BIT):
        return Value.Float(
            struct.unpack("<f" if column_type == _TYPES.FLOAT_32BIT else "<d", data)[0]
        )
    if column_type in (_TYPES.TEXT, _TYPES.LARGE_TEXT):
        return Value.String(row.get_value_data_as_string(position))
    if column_type in _BINARY:
        return Value.String(base64.urlsafe_b64encode(data).decode("ascii").rstrip("="))
    return Value.Null()


def _parse_table(table, output, field_mapping, index):
    columns = []
    for position in range(table.get_number_of_columns()):
        name = table.get_column(position).get_name()
        columns.append((name, field_mapping.get_parser(name)))
    for position in range(table.get_number_of_records()):
        row = table.get_record(position)
        record = Record()
        for column, (name, parser) in enumerate(columns):
            value = _read_value(row, column, name, index)
            if parser is None:
                record.add(name, value)
            else:
                parser.set_value(value, record)
        output.write(record)


def parse_srum(
    input_file: str,
    run_config: RunConfiguration,
    plugin_config: PluginConfiguration,
    metadata: Metadata,
) -> RunReport:
    """Parse SRUM using pyesedb and common's configuration/output runtime."""
    report = RunReport()
    database = None
    opened = False
    try:
        if not run_config.output:
            raise ValueError("SRUM requires at least one output configuration")
        plugin_config.get_data_type_mapping()
        database = pyesedb.file()
        database.open(input_file)
        opened = True
        index = _load_index(database)
        for name, guid in SRUM_TABLES:
            mapping = plugin_config.get_data_type_mapping(name).field_mapping
            if mapping is None:
                raise ValueError(
                    f"'{name}' configuration does not have a field mapping"
                )
            output = None
            try:
                with Output(run_config, plugin_config, metadata, name) as output:
                    table = database.get_table_by_name(guid)
                    if table is not None:
                        _parse_table(table, output, mapping, index)
            except Exception as error:
                report.add_error(f"SRUM Table:'{name}', Error: {error}")
            finally:
                if output is not None:
                    report.add_output_report(output.get_report())
    except Exception as error:
        report.add_error(str(error))
    finally:
        if opened:
            try:
                database.close()
            except Exception as error:
                report.add_error(str(error))
    return report


class Srum(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "Srum",
            "SRUM (System Resource Usage Monitor) database file parser",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        return parse_srum(input_file, run_config, plugin_config, metadata)
