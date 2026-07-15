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


class RegMuiCache(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegMuiCache",
            "Get MUI cache for each user from UsrClass hive",
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

        paths = [
            "\\HKCU\\Software\\Microsoft\\Windows\\ShellNoRoam\\MuiCache",
            "\\HKCU\\Software\\Microsoft\\Windows\\Shell\\MuiCache",
            "\\HKCU\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\MuiCache",
            "\\HKCU\\Local Settings\\Software\\Microsoft\\Windows\\ShellNoRoam\\MuiCache",
        ]

        with Output(run_config, plugin_config, metadata) as output:
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
            apps = {}
            for val in key.values():
                name = val.name()
                if val.type() == "REG_SZ" and not name.startswith("@"):
                    if name.endswith(".ApplicationCompany"):
                        fields = name.split(".ApplicationCompany")
                        executable = fields[0]
                        if executable in apps:
                            apps[executable]["Company"] = val.data()
                        else:
                            apps[executable] = {"Company": val.data(), "AppName": None}
                    elif name.endswith(".FriendlyAppName"):
                        executable = name.removesuffix(".FriendlyAppName")
                        if executable in apps:
                            apps[executable]["AppName"] = val.data()
                        else:
                            apps[executable] = {"AppName": val.data(), "Company": None}
                    else:
                        executable = name
                        apps[name] = {"AppName": val.data(), "Company": None}

            for exe, desc in apps.items():
                if desc["Company"] is None:
                    description = desc["AppName"]
                else:
                    description = f"{desc['Company']} - {desc['AppName']}"

                tuple = Record()
                tuple.add("executable", value(exe))
                tuple.add("description", value(description))
                tuple.add("key_path", value(key.path))
                tuple.add("key_modif_time", value(key.mtime))
                tuple.add(
                    "key_security", Value.Object(key.security_descriptor.to_record())
                )
                output.write(tuple)

        except Exception as e:
            report.add_error(f"{e}")
