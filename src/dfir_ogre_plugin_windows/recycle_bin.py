import logging

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


class RecycleBin(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RecycleBin",
            "Retrieve file information from the recycle bin",
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

        with Output(
            run_config,
            plugin_config,
            metadata,
        ) as output:
            try:
                with open(input_file, "rb") as input:
                    tuple = Record()

                    input_size = input.seek(0, 2)
                    input.seek(0)
                    fixed_fields = input.read(24)
                    if len(fixed_fields) != 24:
                        raise ValueError("Truncated Recycle Bin fixed fields")

                    header = int.from_bytes(fixed_fields[:8], byteorder="little")
                    if header not in (1, 2):
                        raise ValueError(f"Unexpected header value: {header}")
                    tuple.add("header", value(header))

                    size = int.from_bytes(fixed_fields[8:16], byteorder="little")
                    tuple.add("size", value(size))

                    deletion_timestamp_int = int.from_bytes(
                        fixed_fields[16:24], byteorder="little"
                    )
                    deletion_timestamp = filetime_to_utc(deletion_timestamp_int)
                    tuple.add("uninstall_date", value(deletion_timestamp))

                    if header == 1:
                        logger.debug(
                            "INFO2 file version 1 : Windows Vista or Windows 7"
                        )
                        filepath_size = 520

                    elif header == 2:
                        logger.debug("INFO2 file version 2 : Windows 10+")
                        length_bytes = input.read(4)
                        if len(length_bytes) != 4:
                            raise ValueError("Truncated Recycle Bin path length")
                        filepath_length = int.from_bytes(
                            length_bytes, byteorder="little"
                        )
                        filepath_size = filepath_length * 2

                    if filepath_size > input_size - input.tell():
                        raise ValueError("Truncated Recycle Bin path")
                    filepath = input.read(filepath_size)
                    if len(filepath) != filepath_size:
                        raise ValueError("Truncated Recycle Bin path")

                    path = filepath.decode(encoding="utf-16-le")
                    if "\u0000" not in path or (
                        header == 2 and not path.endswith("\u0000")
                    ):
                        raise ValueError("Recycle Bin path is not NUL terminated")
                    path = path.replace("\u0000", "")
                    tuple.add("path", value(path))
                    output.write(tuple)

            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report
