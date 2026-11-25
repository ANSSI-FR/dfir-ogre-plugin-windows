import logging

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

from dfir_ogre_plugin_windows.common import add_list, value

logger = logging.getLogger(__name__)


class RegSnapExclude(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegSnapExclude",
            "Extract the list of files excluded from VSS and backup operations, from System hive",
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
            reg = Registry.load(input_file, "\\HKLM\\System")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        paths = [
            "HKLM\\System\\*ControlSet*\\Control\\BackupRestore\\FilesNotToBackup",
            "HKLM\\System\\*ControlSet*\\Control\\BackupRestore\\FilesNotToSnapshot",
        ]

        with Output(
            run_config,
            plugin_config,
            metadata,
        ) as output:
            for path in paths:
                self.parse_path(reg, path, output, report)

            report.add_output_report(output.get_report())

        return report

    def parse_path(self, reg: Registry, path: str, output: Output, report: RunReport):
        try:
            keys = reg.glob_keys(path)
            for key in keys:
                self.parse_key(key, output, report)
        except Exception as e:
            report.add_error(f"{e}")

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        try:
            for key_val in key.values():
                tuple = Record()
                name = key_val.name()
                tuple.add("type", value(key.name))
                tuple.add("name", value(name))
                add_list(tuple, "file_path", key_val.data())
                tuple.add("key_path", value(key.path))
                tuple.add("key_modif_time", value(key.mtime))
                tuple.add(
                    "key_security", Value.Object(key.security_descriptor.to_record())
                )
                output.write(tuple)
        except Exception as e:
            report.add_error(f"{e}")
