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


class RegAcMru(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAcMru",
            "Get Windows XP Search Assistant history from NTUSER.DAT",
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

        with Output(run_config, plugin_config, metadata, None) as output:
            try:
                keys = reg.glob_keys(
                    "\\HKCU\\Software\\Microsoft\\Search Assistant\\ACMru\\*"
                )
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        try:
            self._parse_key(key, output, report)
        except Exception as error:
            report.add_error(f"{key.path}: {error}")

    def _parse_key(self, key: RegKey, output: Output, report: RunReport):
        indexed_values = []
        for reg_value in key.values():
            value_name = reg_value.name()
            if (
                not isinstance(value_name, str)
                or not value_name
                or not value_name.isascii()
                or not value_name.isdecimal()
            ):
                report.add_error(
                    f"{key.path}: invalid ACMru value name {value_name!r}"
                )
                continue
            order_index = int(value_name, 10)
            indexed_values.append((order_index, reg_value))

        for order_index, reg_value in sorted(
            indexed_values,
            key=lambda item: item[0],
        ):
            record = Record()
            record.add("search_request", value(reg_value.data()))
            record.add("order_index", value(order_index))
            record.add("category", value(key.name))
            record.add("key_path", value(key.path))
            if order_index == 0:
                record.add("key_modif_time", value(key.mtime))
            record.add(
                "key_security",
                Value.Object(key.security_descriptor.to_record()),
            )
            output.write(record)
