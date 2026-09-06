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

from dfir_ogre_plugin_windows.common import value

logger = logging.getLogger(__name__)


class RegTypedPaths(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegTypedPaths",
            "Get paths typed in the Windows Explorer address bar from the NTUser hive",
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
            reg = Registry.load(input_file, "\\HKCU")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys(
                    "\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\TypedPaths"
                )
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        try:
            for key_val in key.values():
                val_name = key_val.name()
                # TypedPaths stores its entries as url1, url2, ... (url1 = most recent)
                if val_name.lower().startswith("url"):
                    record = Record()
                    record.add("path", value(key_val.data()))
                    record.add("index", value(val_name))
                    record.add("key_path", value(key.path))
                    record.add("key_modif_time", value(key.mtime))
                    record.add(
                        "key_security",
                        Value.Object(key.security_descriptor.to_record()),
                    )
                    output.write(record)

        except Exception as e:
            report.add_error(f"{e}")
