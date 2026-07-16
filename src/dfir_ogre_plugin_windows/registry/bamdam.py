import logging
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

from dfir_ogre_plugin_windows.common import filetime_to_utc, value

# from .api import RegKey, Registry

logger = logging.getLogger(__name__)


class RegBamDam(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegBamDam",
            "Get informations about Activity Moderator(BAM/DAM), from System hive",
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

        KEY_LIST = [
            # old and new version for the frist 3 control sets
            "\\HKLM\\System\\*ControlSet*\\Services\\bam\\State\\UserSettings\\*",
            "\\HKLM\\System\\*ControlSet*\\Services\\dam\\State\\UserSettings\\*",
            "\\HKLM\\System\\*ControlSet*\\Services\\bam\\UserSettings\\*",
            "\\HKLM\\System\\*ControlSet*\\Services\\dam\\UserSettings\\*",
        ]

        with Output(run_config, plugin_config, metadata) as output:
            for bam_dam in KEY_LIST:
                try:
                    keys = reg.glob_keys(bam_dam)
                    for key in keys:
                        self.parse_key(key, output, report)
                except Exception as e:
                    report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        for val in key.values():
            try:
                if val.name() not in ["SequenceNumber", "Version"]:
                    tuple = Record()
                    tuple.add("exec_path", value(val.name()))
                    tuple.add("user_sid", value(key.name))
                    exec_time_int: int = struct.unpack("<Q", val.data()[0:8])[0]
                    exec_time = filetime_to_utc(exec_time_int)
                    tuple.add("exec_time", value(exec_time))
                    tuple.add("key_path", value(key.path))
                    tuple.add("key_modif_time", value(key.mtime))
                    tuple.add(
                        "key_security",
                        Value.Object(key.security_descriptor.to_record()),
                    )
                    output.write(tuple)

            except Exception as e:
                report.add_error(f"{e}")
