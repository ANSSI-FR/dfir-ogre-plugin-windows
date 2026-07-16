import logging
from datetime import datetime, timezone
from typing import List

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

from dfir_ogre_plugin_windows.common import normalize_guid_values, value

logger = logging.getLogger(__name__)


class RegAmCacheProgram(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAmCacheProgram",
            "Retrieve programs from the AmCache hive",
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
            reg = Registry.load(input_file, "\\AmCache")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        paths = [
            "\\AmCache\\Root\\Programs",
            "\\AmCache\\Root\\InventoryApplication",
        ]

        with Output(run_config, plugin_config, metadata) as output:
            self.parse_path(reg, paths, output, report)
            report.add_output_report(output.get_report())

        return report

    def parse_path(
        self, reg: Registry, paths: List[str], output: Output, report: RunReport
    ):
        for path in paths:
            try:
                keys = reg.glob_keys(path)
                for key in keys:
                    for sub_key in key.sub_keys():
                        self.parse_key(key.name, sub_key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

    def parse_key(
        self, parent_name: str, key: RegKey, output: Output, report: RunReport
    ):
        try:
            tuple = Record()

            if parent_name == "Programs":
                tuple.add("id", value(key.name))

                name = key.value_data("0")
                tuple.add("name", value(name))

                version = key.value_data("1")
                tuple.add("version", value(version))

                publisher = key.value_data("2")
                tuple.add("publisher", value(publisher))

                source = key.value_data("6")
                tuple.add("source", value(source))

                msi_product_code = key.value_data("11")
                tuple.add(
                    "msi_product_code",
                    value(normalize_guid_values(msi_product_code)),
                )

                msi_package_code = key.value_data("12")
                tuple.add(
                    "msi_package_code",
                    value(normalize_guid_values(msi_package_code)),
                )

                install_date = key.value_data("a")
                tuple.add("install_date", value(parse_date(install_date)))

                uninstall_date = key.value_data("b")
                tuple.add("uninstall_date", value(parse_date(uninstall_date)))

                install_dirs = key.value_data("d")

                if isinstance(install_dirs, list):
                    dirs_values = []
                    for dir in install_dirs:
                        dirs_values.append(value(dir))
                    tuple.add("install_dir", Value.Array(dirs_values))
                else:
                    tuple.add("install_dir", value(install_dirs))

            elif parent_name == "InventoryApplication":
                id = key.value_data("ProgramId")
                tuple.add("id", value(id))

                name = key.value_data("Name")
                tuple.add("name", value(name))

                version = key.value_data("Version")
                tuple.add("version", value(version))

                publisher = key.value_data("Publisher")
                tuple.add("publisher", value(publisher))

                source = key.value_data("Source")
                tuple.add("source", value(source))

                instance_id = key.value_data("ProgramInstanceId")
                tuple.add("instance_id", value(instance_id))

                os_at_install = key.value_data("OSVersionAtInstallTime")
                tuple.add("os_at_install", value(os_at_install))

                msi_product_code = key.value_data("MsiProductCode")
                tuple.add(
                    "msi_product_code",
                    value(normalize_guid_values(msi_product_code)),
                )

                msi_package_code = key.value_data("MsiPackageCode")
                tuple.add(
                    "msi_package_code",
                    value(normalize_guid_values(msi_package_code)),
                )

                install_date = key.value_data("InstallDate")
                tuple.add("install_date", value(parse_date(install_date)))

                install_dirs = key.value_data("RootDirPath")
                dirs_values = []
                if isinstance(install_dirs, list):
                    dirs_values = []
                    for dir in install_dirs:
                        dirs_values.append(value(dir))
                    tuple.add("install_dir", Value.Array(dirs_values))
                else:
                    tuple.add("install_dir", value(install_dirs))

            tuple.add("key_path", value(key.path))
            tuple.add("key_modif_time", value(key.mtime))
            tuple.add("key_security", Value.Object(key.security_descriptor.to_record()))
            output.write(tuple)
        except Exception as e:
            report.add_error(f"{e}")


def parse_date(date) -> datetime |str | None:
    if date:
        if isinstance(date, str):
            f = "%m/%d/%Y %H:%M:%S"
            try:
                dt = datetime.strptime(date, f)
                return dt.replace(tzinfo=timezone.utc)
            except:
                return date

        else:
            return datetime.fromtimestamp(date, tz=timezone.utc)
