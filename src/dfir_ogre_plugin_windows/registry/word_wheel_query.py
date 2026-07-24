import struct

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import value

MRU_LIST_TERMINATOR = 0xFFFFFFFF


def parse_mru_list_ex(data: bytes) -> list[int]:
    if not isinstance(data, bytes):
        raise ValueError("MRUListEx is not binary data")
    if len(data) % 4 != 0:
        raise ValueError(f"MRUListEx length {len(data)} is not a multiple of 4")

    values = [unpacked[0] for unpacked in struct.iter_unpack("<I", data)]
    try:
        terminator = values.index(MRU_LIST_TERMINATOR)
    except ValueError as error:
        raise ValueError("MRUListEx has no terminator") from error
    return values[:terminator]


def decode_word_wheel_value(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise ValueError("value is not binary data")
    if len(data) % 2 != 0:
        raise ValueError(f"UTF-16LE value length {len(data)} is odd")
    try:
        return data.decode("utf-16-le").rstrip("\x00")
    except UnicodeDecodeError as error:
        raise ValueError("value is not valid UTF-16LE") from error


class RegWordWheelQuery(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegWordWheelQuery",
            "Get Windows 7 and later Explorer WordWheelQuery history "
            "from NTUSER.DAT",
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
        try:
            registry = Registry.load(input_file, r"\HKCU")
        except Exception as error:
            report.add_error(str(error))
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = registry.glob_keys(
                    r"\HKCU\Software\Microsoft\Windows\CurrentVersion"
                    r"\Explorer\WordWheelQuery"
                )
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as error:
                report.add_error(str(error))
            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        mru_list = key.value_data("MRUListEx")
        if mru_list is None:
            return

        try:
            value_indices = parse_mru_list_ex(mru_list)
        except ValueError as error:
            report.add_error(f"{key.path}: {error}")
            return

        for order_index, value_index in enumerate(value_indices):
            raw_value = key.value_data(str(value_index))
            if raw_value is None:
                report.add_error(
                    f"{key.path}: missing WordWheelQuery value {value_index}"
                )
                continue
            try:
                search_request = decode_word_wheel_value(raw_value)
            except ValueError as error:
                report.add_error(
                    f"{key.path}: invalid UTF-16LE value {value_index}: {error}"
                )
                continue

            record = Record()
            record.add("search_request", value(search_request))
            record.add("order_index", value(order_index))
            record.add("value_index", value(value_index))
            record.add("key_path", value(key.path))
            if order_index == 0:
                record.add("key_modif_time", value(key.mtime))
            record.add(
                "key_security",
                Value.Object(key.security_descriptor.to_record()),
            )
            output.write(record)
