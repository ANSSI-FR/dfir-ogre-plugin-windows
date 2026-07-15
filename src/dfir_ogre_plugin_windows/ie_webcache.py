import json
import logging
import struct
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pyesedb
from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc, value

logger = logging.getLogger(__name__)
CONTAINER_NAME_IDX = 8
CONTAINER_DIRECTORY_IDX = 10
PROPERTY_STORAGE_VERSION = b"1SPS"
FMTID_INTERNET_SITE = "000214a1-0000-0000-c000-000000000046"
MAX_VECTOR_VALUES = 10_000

VT_VECTOR = 0x1000
VT_ARRAY = 0x2000
VT_BYREF = 0x4000
VT_TYPE_MASK = 0x0FFF

PROPERTY_TYPE_NAMES = {
    0x0000: "VT_EMPTY",
    0x0001: "VT_NULL",
    0x0002: "VT_I2",
    0x0003: "VT_I4",
    0x0004: "VT_R4",
    0x0005: "VT_R8",
    0x0006: "VT_CY",
    0x0007: "VT_DATE",
    0x0008: "VT_BSTR",
    0x000A: "VT_ERROR",
    0x000B: "VT_BOOL",
    0x000E: "VT_DECIMAL",
    0x0010: "VT_I1",
    0x0011: "VT_UI1",
    0x0012: "VT_UI2",
    0x0013: "VT_UI4",
    0x0014: "VT_I8",
    0x0015: "VT_UI8",
    0x0016: "VT_INT",
    0x0017: "VT_UINT",
    0x001E: "VT_LPSTR",
    0x001F: "VT_LPWSTR",
    0x0040: "VT_FILETIME",
    0x0041: "VT_BLOB",
    0x0042: "VT_STREAM",
    0x0043: "VT_STORAGE",
    0x0044: "VT_STREAMED_OBJECT",
    0x0045: "VT_STORED_OBJECT",
    0x0046: "VT_BLOB_OBJECT",
    0x0047: "VT_CF",
    0x0048: "VT_CLSID",
    0x0049: "VT_VERSIONED_STREAM",
}

INTERNET_SITE_PROPERTY_NAMES = {
    2: "PID_INTSITE_WHATSNEW",
    3: "PID_INTSITE_AUTHOR",
    4: "PID_INTSITE_LASTVISIT",
    5: "PID_INTSITE_LASTMOD",
    6: "PID_INTSITE_VISITCOUNT",
    7: "PID_INTSITE_DESCRIPTION",
    8: "PID_INTSITE_COMMENT",
    9: "PID_INTSITE_FLAGS",
    10: "PID_INTSITE_CONTENTLEN",
    11: "PID_INTSITE_CONTENTCODE",
    12: "PID_INTSITE_RECURSE",
    13: "PID_INTSITE_WATCH",
    14: "PID_INTSITE_SUBSCRIPTION",
    15: "PID_INTSITE_URL",
    16: "PID_INTSITE_TITLE",
    18: "PID_INTSITE_CODEPAGE",
    19: "PID_INTSITE_TRACKING",
    20: "PID_INTSITE_ICONINDEX",
    21: "PID_INTSITE_ICONFILE",
    34: "PID_INTSITE_ROAMED",
}


def _align_4(size: int) -> int:
    return (size + 3) & ~3


def _require_size(data: bytes, size: int, description: str):
    if len(data) < size:
        raise ValueError(
            f"truncated {description}: need {size} bytes, have {len(data)}"
        )


def _unpack_scalar(data: bytes, format: str, description: str):
    size = struct.calcsize(format)
    _require_size(data, size, description)
    return struct.unpack_from(format, data)[0], size


def _decode_counted_string(
    data: bytes,
    encoding: str,
    character_size: int,
) -> tuple[str, int]:
    character_count, _ = _unpack_scalar(data, "<I", "string length")
    byte_count = character_count * character_size
    end = 4 + byte_count
    aligned_end = _align_4(end)
    _require_size(data, aligned_end, "string")
    if any(data[end:aligned_end]):
        raise ValueError("string has non-zero alignment padding")

    decoded = data[4:end].decode(encoding)
    if decoded:
        if not decoded.endswith("\x00"):
            raise ValueError("string is not null terminated")
        decoded = decoded[:-1]
    return decoded, aligned_end


def _decode_code_page_string(data: bytes) -> tuple[str, int]:
    byte_count, _ = _unpack_scalar(data, "<I", "code-page string length")
    end = 4 + byte_count
    aligned_end = _align_4(end)
    _require_size(data, aligned_end, "code-page string")
    if any(data[end:aligned_end]):
        raise ValueError("code-page string has non-zero alignment padding")

    encoded = data[4:end]
    if not encoded:
        return "", aligned_end

    # Serialized property stores commonly use CP_WINUNICODE. The code page is
    # not carried in this packet, so the two-byte terminator is the only safe
    # local discriminator; otherwise preserve the usual Windows-1252 text.
    if len(encoded) % 2 == 0 and encoded.endswith(b"\x00\x00"):
        decoded = encoded.decode("utf-16-le")
    else:
        decoded = encoded.decode("windows-1252")

    if not decoded.endswith("\x00"):
        raise ValueError("code-page string is not null terminated")
    return decoded[:-1], aligned_end


def _decode_blob(data: bytes) -> tuple[str, int]:
    byte_count, _ = _unpack_scalar(data, "<I", "blob length")
    end = 4 + byte_count
    aligned_end = _align_4(end)
    _require_size(data, aligned_end, "blob")
    if any(data[end:aligned_end]):
        raise ValueError("blob has non-zero alignment padding")
    return f"0x{data[4:end].hex()}", aligned_end


def _decode_indirect_property_name(data: bytes) -> tuple[str, int]:
    return _decode_code_page_string(data)


def _decode_scalar_property(property_type: int, data: bytes) -> tuple[str, int]:
    if property_type == 0x0000:
        return "", 0
    if property_type == 0x0001:
        return "null", 0
    if property_type == 0x0002:
        result, size = _unpack_scalar(data, "<h", "VT_I2")
        return str(result), size
    if property_type in (0x0003, 0x0016):
        result, size = _unpack_scalar(data, "<i", "signed 32-bit integer")
        return str(result), size
    if property_type == 0x0004:
        result, size = _unpack_scalar(data, "<f", "VT_R4")
        return repr(result), size
    if property_type == 0x0005:
        result, size = _unpack_scalar(data, "<d", "VT_R8")
        return repr(result), size
    if property_type == 0x0006:
        result, size = _unpack_scalar(data, "<q", "VT_CY")
        return format(Decimal(result) / Decimal(10_000), "f"), size
    if property_type == 0x0007:
        result, size = _unpack_scalar(data, "<d", "VT_DATE")
        date = datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=result)
        return date.isoformat(), size
    if property_type == 0x0008:
        return _decode_code_page_string(data)
    if property_type == 0x000A:
        result, size = _unpack_scalar(data, "<I", "VT_ERROR")
        return f"0x{result:08x}", size
    if property_type == 0x000B:
        result, size = _unpack_scalar(data, "<h", "VT_BOOL")
        return str(result != 0).lower(), size
    if property_type == 0x0010:
        result, size = _unpack_scalar(data, "<b", "VT_I1")
        return str(result), size
    if property_type == 0x0011:
        result, size = _unpack_scalar(data, "<B", "VT_UI1")
        return str(result), size
    if property_type == 0x0012:
        result, size = _unpack_scalar(data, "<H", "VT_UI2")
        return str(result), size
    if property_type in (0x0013, 0x0017):
        result, size = _unpack_scalar(data, "<I", "unsigned 32-bit integer")
        return str(result), size
    if property_type == 0x0014:
        result, size = _unpack_scalar(data, "<q", "VT_I8")
        return str(result), size
    if property_type == 0x0015:
        result, size = _unpack_scalar(data, "<Q", "VT_UI8")
        return str(result), size
    if property_type == 0x001E:
        return _decode_code_page_string(data)
    if property_type == 0x001F:
        return _decode_counted_string(data, "utf-16-le", 2)
    if property_type == 0x0040:
        result, size = _unpack_scalar(data, "<Q", "VT_FILETIME")
        return filetime_to_utc(result).isoformat(), size
    if property_type in (0x0041, 0x0046):
        return _decode_blob(data)
    if property_type in (0x0042, 0x0043, 0x0044, 0x0045):
        return _decode_indirect_property_name(data)
    if property_type == 0x0048:
        _require_size(data, 16, "VT_CLSID")
        return str(UUID(bytes_le=data[:16])), 16
    if property_type == 0x0049:
        _require_size(data, 16, "VT_VERSIONED_STREAM GUID")
        version = str(UUID(bytes_le=data[:16]))
        name, consumed = _decode_indirect_property_name(data[16:])
        return f"{version}:{name}", 16 + consumed

    return f"0x{data.hex()}", len(data)


def _decode_vector_property(property_type: int, data: bytes) -> str:
    element_type = property_type & VT_TYPE_MASK
    element_count, _ = _unpack_scalar(data, "<I", "vector element count")
    if element_count > MAX_VECTOR_VALUES:
        raise ValueError(
            f"vector contains {element_count} values; maximum is {MAX_VECTOR_VALUES}"
        )

    values = []
    cursor = 4
    for _ in range(element_count):
        decoded, consumed = _decode_scalar_property(element_type, data[cursor:])
        if consumed == 0 and element_count > 0:
            raise ValueError("zero-sized vector element")
        values.append(decoded)
        cursor += consumed

    trailing = data[cursor:]
    encoded = json.dumps(values, ensure_ascii=False)
    if any(trailing):
        encoded += f" [trailing=0x{trailing.hex()}]"
    return encoded


def _property_type_name(property_type: int) -> str:
    names = []
    if property_type & VT_VECTOR:
        names.append("VT_VECTOR")
    if property_type & VT_ARRAY:
        names.append("VT_ARRAY")
    if property_type & VT_BYREF:
        names.append("VT_BYREF")

    scalar_type = property_type & VT_TYPE_MASK
    names.append(PROPERTY_TYPE_NAMES.get(scalar_type, f"0x{scalar_type:04x}"))
    return " | ".join(names)


def _decode_property_value(property_type: int, data: bytes) -> str:
    if property_type & (VT_ARRAY | VT_BYREF):
        return f"0x{data.hex()}"
    if property_type & VT_VECTOR:
        return _decode_vector_property(property_type, data)

    decoded, consumed = _decode_scalar_property(property_type, data)
    trailing = data[consumed:]
    if any(trailing):
        decoded += f" [trailing=0x{trailing.hex()}]"
    return decoded


def _property_name(format_id: str, property_id: int) -> str | None:
    if format_id == FMTID_INTERNET_SITE:
        return INTERNET_SITE_PROPERTY_NAMES.get(property_id)
    return None


def parse_response_properties(data: bytes) -> tuple[list[Record], list[str]]:
    """Decode concatenated MS-PROPSTORE buffers without discarding raw input."""

    properties = []
    errors = []
    cursor = 0
    store_index = 0

    while cursor < len(data):
        remaining = len(data) - cursor
        if remaining < 4:
            errors.append(f"store {store_index}: {remaining} trailing byte(s)")
            break

        store_size = struct.unpack_from("<I", data, cursor)[0]
        if store_size < 4:
            errors.append(
                f"store {store_index}: invalid store size {store_size} at offset {cursor}"
            )
            break

        store_end = cursor + 4 + store_size
        if store_end > len(data):
            errors.append(
                f"store {store_index}: size {store_size} exceeds "
                f"the {remaining - 4} available byte(s)"
            )
            break

        storage_cursor = cursor + 4
        storage_index = 0
        storage_terminated = False
        while storage_cursor < store_end:
            if store_end - storage_cursor < 4:
                errors.append(
                    f"store {store_index}: truncated storage size at offset "
                    f"{storage_cursor}"
                )
                break

            storage_size = struct.unpack_from("<I", data, storage_cursor)[0]
            if storage_size == 0:
                storage_cursor += 4
                storage_terminated = True
                if storage_cursor != store_end:
                    errors.append(
                        f"store {store_index}: data follows the storage terminator"
                    )
                break

            if storage_size < 28:
                errors.append(
                    f"store {store_index}, storage {storage_index}: "
                    f"invalid storage size {storage_size}"
                )
                break

            storage_end = storage_cursor + storage_size
            if storage_end > store_end:
                errors.append(
                    f"store {store_index}, storage {storage_index}: size "
                    f"{storage_size} exceeds its enclosing store"
                )
                break

            version = data[storage_cursor + 4 : storage_cursor + 8]
            if version != PROPERTY_STORAGE_VERSION:
                errors.append(
                    f"store {store_index}, storage {storage_index}: invalid version "
                    f"0x{version.hex()}"
                )
                storage_cursor = storage_end
                storage_index += 1
                continue

            format_id = str(
                UUID(bytes_le=data[storage_cursor + 8 : storage_cursor + 24])
            )
            property_cursor = storage_cursor + 24
            property_terminated = False

            while property_cursor < storage_end:
                if storage_end - property_cursor < 4:
                    errors.append(
                        f"store {store_index}, storage {storage_index}: "
                        "truncated property size"
                    )
                    break

                value_size = struct.unpack_from("<I", data, property_cursor)[0]
                if value_size == 0:
                    property_cursor += 4
                    property_terminated = True
                    if property_cursor != storage_end:
                        errors.append(
                            f"store {store_index}, storage {storage_index}: "
                            "data follows the property terminator"
                        )
                    break

                if value_size < 13:
                    errors.append(
                        f"store {store_index}, storage {storage_index}: invalid "
                        f"property size {value_size} at offset {property_cursor}"
                    )
                    break

                property_end = property_cursor + value_size
                if property_end > storage_end:
                    errors.append(
                        f"store {store_index}, storage {storage_index}: property "
                        f"size {value_size} exceeds its storage"
                    )
                    break

                property_id = struct.unpack_from("<I", data, property_cursor + 4)[0]
                reserved = data[property_cursor + 8]
                property_type = struct.unpack_from("<H", data, property_cursor + 9)[0]
                padding = data[property_cursor + 11 : property_cursor + 13]
                property_data = data[property_cursor + 13 : property_end]

                if reserved != 0:
                    errors.append(
                        f"store {store_index}, storage {storage_index}, property "
                        f"{property_id}: reserved byte is 0x{reserved:02x}"
                    )
                if padding != b"\x00\x00":
                    errors.append(
                        f"store {store_index}, storage {storage_index}, property "
                        f"{property_id}: padding is 0x{padding.hex()}"
                    )

                try:
                    property_value = _decode_property_value(
                        property_type, property_data
                    )
                except (OSError, OverflowError, ValueError) as e:
                    errors.append(
                        f"store {store_index}, storage {storage_index}, property "
                        f"{property_id}: {e}"
                    )
                    property_value = f"0x{property_data.hex()}"

                property_record = Record()
                property_record.add("store_index", value(store_index))
                property_record.add("storage_index", value(storage_index))
                property_record.add("format_id", value(format_id))
                property_record.add("id", value(property_id))
                property_record.add(
                    "name", value(_property_name(format_id, property_id))
                )
                property_record.add(
                    "value_type", value(_property_type_name(property_type))
                )
                property_record.add("value", Value.String(property_value))
                properties.append(property_record)
                property_cursor = property_end

            if not property_terminated:
                errors.append(
                    f"store {store_index}, storage {storage_index}: "
                    "missing property terminator"
                )

            storage_cursor = storage_end
            storage_index += 1

        if not storage_terminated:
            errors.append(f"store {store_index}: missing storage terminator")

        cursor = store_end
        store_index += 1

    return properties, errors


class IeWebCache(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "IeWebCache",
            "Parse IE history from Webcache database (WebCacheV01.dat)",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()

        with Output(run_config, plugin_config, metadata) as output:
            esedb_file = None
            try:
                esedb_file = pyesedb.file()
                esedb_file.open(input_file)

                # Find the History container

                # table_count = esedb_file.get_number_of_tables()
                # print(f"Database contains {table_count} table(s):\n")

                # for idx in range(table_count):
                #     try:
                #         table = esedb_file.get_table(idx)

                #         print(f"{idx + 1:>3}. {table.get_name()}")
                #     except Exception as e:
                #         print(f"   (failed to read table #{idx}: {e})")

                # Find the History container
                history_container_ids = []
                containers_table = esedb_file.get_table_by_name("Containers")
                if containers_table is not None:
                    for i in range(containers_table.get_number_of_records()):
                        record = containers_table.get_record(i)
                        try:
                            container_name = record.get_value_data_as_string(
                                CONTAINER_NAME_IDX
                            )

                            container_directory = record.get_value_data_as_string(
                                CONTAINER_DIRECTORY_IDX
                            )
                            if (
                                container_name == "History"
                                and "History.IE5" in container_directory
                            ):
                                history_container_ids.append(
                                    record.get_value_data_as_integer(0)
                                )
                        except Exception as e:
                            report.add_error(f"{e}")
                            continue

                # Extract records from every matching History container
                for history_container_id in history_container_ids:
                    table_name = f"Container_{history_container_id}"
                    history_table = esedb_file.get_table_by_name(table_name)
                    if history_table is not None:
                        for j in range(history_table.get_number_of_records()):
                            try:
                                record = history_table.get_record(j)
                                output.write(self._parse_record(record))
                            except Exception as e:
                                report.add_error(str(e))

                esedb_file.close()

            except Exception as e:
                report.add_error(str(e))
            finally:
                if esedb_file is not None:
                    try:
                        esedb_file.close()
                    except Exception:
                        ...

            report.add_output_report(output.get_report())

        return report

    def _parse_record(self, record: pyesedb.record) -> Record:
        """Transform a raw ESEDB record into an ogre `Record` object"""
        record_obj = Record()

        # Parse all values from the record
        values = {}
        for i in range(record.get_number_of_values()):
            col_name = record.get_column_name(i)
            data = self._get_value_data(record, i)
            values[col_name] = data

        record_obj.add("file_size", value(values.get("FileSize")))
        record_obj.add("type", value(values.get("Type")))
        record_obj.add("flags", value(values.get("Flags")))
        record_obj.add("access_count", value(values.get("AccessCount")))
        record_obj.add("sync_count", value(values.get("SyncCount")))
        record_obj.add("exemption_delta", value(values.get("ExemptionDelta")))
        record_obj.add("url", value(values.get("Url")))
        record_obj.add("filename", value(values.get("Filename")))
        record_obj.add("file_extension", value(values.get("FileExtension")))
        record_obj.add("redirect_url", value(values.get("RedirectUrl")))

        # Handle binary fields
        if values.get("RequestHeaders"):
            record_obj.add("request_headers", value(values.get("RequestHeaders")))
        response_properties = values.get("ResponseHeaders")
        if response_properties:
            record_obj.add("response_properties_raw", value(response_properties))
            if isinstance(response_properties, (bytes, bytearray)):
                parsed_properties, parse_errors = parse_response_properties(
                    bytes(response_properties)
                )
                record_obj.add(
                    "response_properties",
                    Value.Array([Value.Object(prop) for prop in parsed_properties]),
                )
                if parse_errors:
                    record_obj.add(
                        "response_properties_parse_error",
                        Value.String("; ".join(parse_errors)),
                    )
            else:
                record_obj.add("response_properties", Value.Array([]))
                record_obj.add(
                    "response_properties_parse_error",
                    Value.String(
                        "unsupported ResponseHeaders value type: "
                        f"{type(response_properties).__name__}"
                    ),
                )
        if values.get("Group"):
            record_obj.add("group", value(values.get("Group")))

        # Convert filetimes to UTC for timestamp fields
        sync_time = values.get("SyncTime")
        if sync_time:
            record_obj.add("sync_date", value(filetime_to_utc(sync_time)))

        creation_time = values.get("CreationTime")
        if creation_time:
            record_obj.add("creation_date", value(filetime_to_utc(creation_time)))

        expiry_time = values.get("ExpiryTime")
        if expiry_time:
            record_obj.add("expiry_date", value(filetime_to_utc(expiry_time)))

        modified_time = values.get("ModifiedTime")
        if modified_time:
            record_obj.add("modified_date", value(filetime_to_utc(modified_time)))

        accessed_time = values.get("AccessedTime")
        if accessed_time:
            record_obj.add("accessed_date", value(filetime_to_utc(accessed_time)))

        post_check_time = values.get("PostCheckTime")
        if post_check_time:
            record_obj.add("post_check_date", value(filetime_to_utc(post_check_time)))

        return record_obj

    def _get_value_data(self, record: pyesedb.record, column_index: int):
        """Extract data from an ESEDB record value."""
        try:
            if record.is_long_value(column_index):
                try:
                    lv = record.get_value_data_as_long_value(column_index)
                    if lv is not None:
                        try:
                            return lv.get_data_as_string()
                        except Exception:
                            return lv.get_data()
                except Exception as e:
                    logger.debug(f"Error getting long value: {e}")
                    return None
            else:
                col_type = record.get_column_type(column_index)
                if col_type in [
                    pyesedb.column_types.DOUBLE_64BIT,
                    pyesedb.column_types.FLOAT_32BIT,
                ]:
                    return record.get_value_data_as_floating_point(column_index)
                elif col_type in [
                    pyesedb.column_types.INTEGER_32BIT_SIGNED,
                    pyesedb.column_types.INTEGER_32BIT_UNSIGNED,
                    pyesedb.column_types.INTEGER_16BIT_SIGNED,
                    pyesedb.column_types.INTEGER_16BIT_UNSIGNED,
                    pyesedb.column_types.INTEGER_64BIT_SIGNED,
                    pyesedb.column_types.INTEGER_8BIT_UNSIGNED,
                ]:
                    return record.get_value_data_as_integer(column_index)
                elif col_type in [
                    pyesedb.column_types.TEXT,
                    pyesedb.column_types.LARGE_TEXT,
                ]:
                    return record.get_value_data_as_string(column_index)
                else:
                    return record.get_value_data(column_index)
        except Exception as e:
            logger.debug(f"Error getting value data for column {column_index}: {e}")
            return None
