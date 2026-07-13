import logging
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
    )

from dfir_ogre_plugin_windows.common import filetime_to_utc, value

logger = logging.getLogger(__name__)
CONTAINER_NAME_IDX = 8
CONTAINER_DIRECTORY_IDX = 10

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
                history_container_id = None
                containers_table = esedb_file.get_table_by_name("Containers")
                if containers_table is not None:
                    for i in range(containers_table.get_number_of_records()):
                        record = containers_table.get_record(i)
                        try:
                            container_name = record.get_value_data_as_string(CONTAINER_NAME_IDX)

                            container_directory = record.get_value_data_as_string(CONTAINER_DIRECTORY_IDX)
                            if container_name == "History" and "History.IE5" in container_directory:
                                history_container_id = record.get_value_data_as_integer(0)
                                break
                        except Exception as e:
                            report.add_error(f"{e}")
                            continue

                # Extract records from the History container
                if history_container_id is not None:
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
        if values.get("ResponseHeaders"):
            record_obj.add("response_headers", value(values.get("ResponseHeaders")))
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


import struct

def parse_length_prefixed_headers(binary_data):
    """
    Parse headers where each string is prefixed with a 4-byte length (little-endian)
    """
    headers = []
    offset = 0

    while offset < len(binary_data):
        # Read 4-byte length
        if offset + 4 > len(binary_data):
            break

        length = struct.unpack('<I', binary_data[offset:offset+4])[0]
        offset += 4

        # Read string
        if offset + length > len(binary_data):
            break

        string = binary_data[offset:offset+length].decode('utf-8', errors='ignore')
        headers.append(string)
        offset += length

    return headers

def decode_superfetch_format(binary_data):
        """
        Parse Windows SuperFetch Format (1SPS header)
        This is a property set serialization format
        """
        if not binary_data.startswith(b'1SPS'):
            print("Not a SuperFetch format")
            return None

        # Skip the '1SPS' magic bytes and version
        offset = 4

        properties = {}

        # The format contains length-prefixed property values
        # Each property typically has: type tag + length + data

        while offset < len(binary_data):
            # Read property type/tag (1 byte)
            if offset >= len(binary_data):
                break

            prop_type = binary_data[offset]
            offset += 1

            # Read length (4 bytes, little-endian)
            if offset + 4 > len(binary_data):
                break

            length = struct.unpack('<I', binary_data[offset:offset+4])[0]
            offset += 4

            # Read value
            if offset + length > len(binary_data):
                break

            value_bytes = binary_data[offset:offset+length]
            offset += length

            # Try to decode as UTF-16 (common in Windows formats)
            try:
                # Check if it looks like UTF-16 (alternating nulls)
                if b'\x00' in value_bytes[::2] or b'\x00' in value_bytes[1::2]:
                    value = value_bytes.decode('utf-16-le', errors='ignore')
                else:
                    value = value_bytes.decode('utf-8', errors='ignore')

                # Only print non-empty, printable values
                if value.strip():
                    properties[f"prop_{len(properties)}"] = value
                    print(f"Property: {value}")
            except:
                pass

        return properties


def decode_windows_property_set(binary_data):
    """
    Decode Windows Property Set Serialization Format (1SPS)
    This stores HTTP headers and metadata as serialized properties
    """

    # Check for 1SPS magic
    if b'1SPS' not in binary_data:
        print("Not a valid property set format")
        return None

    properties = {}

    # Find all 1SPS blocks
    offset = 0
    block_num = 0

    while offset < len(binary_data):
        # Look for 1SPS magic
        sps_pos = binary_data.find(b'1SPS', offset)
        if sps_pos == -1:
            break

        print(f"\n=== Property Set Block {block_num} ===")

        # Skip past 1SPS and version bytes
        offset = sps_pos + 4 + 4  # 4 for '1SPS', 4 for version info

        # Parse properties in this block
        while offset < len(binary_data) and binary_data[offset:offset+4] != b'1SPS':
            if offset + 5 > len(binary_data):
                break

            # Read property tag (1 byte)
            prop_tag = binary_data[offset]
            offset += 1

            # Read length (4 bytes, little-endian)
            if offset + 4 > len(binary_data):
                break

            length = struct.unpack('<I', binary_data[offset:offset+4])[0]
            offset += 4

            # Sanity check
            if length > 10000 or length == 0:
                continue

            if offset + length > len(binary_data):
                break

            # Read value
            value_bytes = binary_data[offset:offset+length]
            offset += length

            # Decode value - try UTF-16 LE first (Windows standard)
            try:
                # Check if it's UTF-16 (has null bytes)
                if b'\x00' in value_bytes:
                    value = value_bytes.decode('utf-16-le', errors='ignore').rstrip('\x00')
                else:
                    value = value_bytes.decode('utf-8', errors='ignore')

                if value.strip():
                    print(f"  Property {prop_tag}: {value}")
                    properties[f"tag_{prop_tag}"] = value
            except Exception:
                # Try raw hex for binary data
                if len(value_bytes) < 50:
                    print(f"  Property {prop_tag} (binary): {value_bytes.hex()}")

        block_num += 1

    return properties
