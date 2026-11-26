"""Read systeminfo CSV without interpreting locale-dependent field values."""

import codecs
import csv

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


# In canonical systeminfo order, also used for localized 33-column exports.
_COLUMNS = {
    "Host Name": "host_name",
    "OS Name": "os_name",
    "OS Version": "os_version",
    "OS Manufacturer": "os_manufacturer",
    "OS Configuration": "os_configuration",
    "OS Build Type": "os_build_type",
    "Registered Owner": "registered_owner",
    "Registered Organization": "registered_organization",
    "Product ID": "product_id",
    "Original Install Date": "original_install_date",
    "System Boot Time": "system_boot_time",
    "System Manufacturer": "system_manufacturer",
    "System Model": "system_model",
    "System Type": "system_type",
    "Processor(s)": "processors",
    "BIOS Version": "bios_version",
    "Windows Directory": "windows_directory",
    "System Directory": "system_directory",
    "Boot Device": "boot_device",
    "System Locale": "system_locale",
    "Input Locale": "input_locale",
    "Time Zone": "time_zone",
    "Total Physical Memory": "total_physical_memory",
    "Available Physical Memory": "available_physical_memory",
    "Virtual Memory: Max Size": "virtual_memory_max_size",
    "Virtual Memory: Available": "virtual_memory_available",
    "Virtual Memory: In Use": "virtual_memory_in_use",
    "Page File Location(s)": "page_file_location",
    "Domain": "domain",
    "Logon Server": "logon_server",
    "Hotfix(s)": "hotfix",
    "Network Card(s)": "network_cards",
    "Hyper-V Requirements": "hyper_v_requirements",
}
_HEADER_FIELDS = {
    header.casefold(): name
    for header, name in {
        **_COLUMNS,
        "System Up Time": "system_up_time",
        "Page File: Max Size": "virtual_memory_max_size",
        "Page File: Available": "virtual_memory_available",
        "Page File: In Use": "virtual_memory_in_use",
    }.items()
}


def _field_names(headers: list[str]) -> list[str]:
    normalized = [header.strip().casefold() for header in headers]
    fields = [_HEADER_FIELDS.get(header) for header in normalized]
    if not any(fields) and len(headers) == len(_COLUMNS):
        # The previous parser ignored the header language. Preserve canonical
        # modern exports, but do not use positions for partially known headers.
        if len(set(normalized)) != len(normalized) or not all(normalized):
            raise ValueError("CSV header contains empty or duplicate columns")
        return list(_COLUMNS.values())

    if not all(fields):
        raise ValueError("CSV header contains unsupported column names or shape")
    if len(set(fields)) != len(fields):
        raise ValueError("CSV header maps multiple columns to the same field")
    if "host_name" not in fields or "os_name" not in fields:
        raise ValueError("CSV header must contain Host Name and OS Name")
    return [field for field in fields if field is not None]


class SystemInfo(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription("SystemInfo", "Parse Windows systeminfo CSV exports")

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        report = RunReport()
        try:
            plugin_config = PluginConfiguration.load(plugin_file)
        except Exception as exception:
            report.add_error(f"SystemInfo configuration: {exception}")
            return report

        line_number = 1
        try:
            with open(input_file, "rb") as stream:
                prefix = stream.read(4)
            encoding = plugin_config.file_encoding
            if prefix.startswith(codecs.BOM_UTF8):
                encoding = "utf-8-sig"
            elif prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
                encoding = "utf-16"
            with open(
                input_file, encoding=encoding, newline=""
            ) as stream:
                reader = csv.reader(stream, strict=True)
                headers = next(reader, None)
                if headers is None:
                    raise ValueError("missing CSV header")
                fields = _field_names(headers)

                with Output(run_config, plugin_config, metadata) as output:
                    while True:
                        line_number = reader.line_num + 1
                        try:
                            row = next(reader)
                        except StopIteration:
                            break
                        except csv.Error as exception:
                            report.add_error(
                                f"SystemInfo CSV line {line_number}: {exception}"
                            )
                            break
                        if not row:
                            continue
                        if len(row) != len(fields):
                            report.add_error(
                                f"SystemInfo CSV line {line_number}: expected "
                                f"{len(fields)} columns, got {len(row)}"
                            )
                            continue
                        record = Record()
                        for field, raw_value in zip(fields, row):
                            record.add(field, Value.String(raw_value))
                        output.write(record)
                report.add_output_report(output.get_report())
        except Exception as exception:
            report.add_error(f"SystemInfo CSV line {line_number}: {exception}")
        return report
