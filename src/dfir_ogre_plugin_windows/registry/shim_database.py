import logging
import uuid
from typing import Dict, List

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc

logger = logging.getLogger(__name__)


class RegShimDb(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegShimDb",
            "Extract the shim database from Software hive ",
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

        target_guid: Dict[uuid.UUID, List[Value]] = {}

        try:
            reg = Registry.load(input_file, "\\HKLM\\Software")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        try:
            self.build_target_guid(target_guid, reg, report)
        except Exception as e:
            report.add_error(f"{e}")

        with Output(run_config, plugin_config, metadata) as output:
            try:
                self.parse_installed_sdb(target_guid, reg, report, output)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())
        return report

    def parse_installed_sdb(
        self,
        target_guid: Dict[uuid.UUID, List[Value]],
        reg: Registry,
        run_report: RunReport,
        output: Output,
    ):
        for key in reg.glob_keys(
            "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\InstalledSDB\\*"
        ):
            try:
                guid = uuid.UUID(key.name)

                target = target_guid.get(guid, [])

                date_val = key.value("DatabaseInstallTimeStamp")
                if date_val:
                    if date_val.type() == "REG_BINARY":
                        date_int = int.from_bytes(date_val.data(), byteorder="little")
                        date = filetime_to_utc(date_int)
                    else:
                        date = filetime_to_utc(date_val.data())
                else:
                    date = None

                path = key.value("DatabasePath")

                description = key.value("DatabaseDescription")

                tuple = Record()
                tuple.add("key_path", Value.String(key.path))
                tuple.add(
                    "key_security", Value.Object(key.security_descriptor.to_record())
                )
                tuple.add("guid", Value.String(str(guid)))
                tuple.add("target", Value.Array(target))

                if date:
                    tuple.add("install_time", Value.Date(date))
                tuple.add("key_modif_time", Value.Date(key.mtime))

                if path:
                    tuple.add("file_path", Value.String(str(path.data())))
                if description:
                    tuple.add("description", Value.String(str(description.data())))

                output.write(tuple)

            except Exception as e:
                run_report.add_error(f"{e}")

    def build_target_guid(
        self,
        target_guid: Dict[uuid.UUID, List[Value]],
        reg: Registry,
        run_report: RunReport,
    ):
        for key in reg.glob_keys(
            "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\Custom\\*"
        ):
            for value in key.values():
                try:
                    guid = uuid.UUID(value.name().split(".")[0])

                    if guid in target_guid:
                        target_guid[guid].append(Value.String(key.name))
                    else:
                        target_guid[guid] = [
                            Value.String(key.name),
                        ]
                except Exception as e:
                    run_report.add_error(f"{e}")
