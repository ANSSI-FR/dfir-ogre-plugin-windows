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

from dfir_ogre_plugin_windows.common import (
    filetime_to_utc,
    normalize_amcache_sha1,
    value,
)

logger = logging.getLogger(__name__)


class RegAmCacheFile(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAmCacheFile",
            "Retrieve files from the AmCache hive",
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
            "\\AmCache\\Root\\File\\*",
            "\\AmCache\\Root\\InventoryApplicationFile",
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

            if parent_name == "InventoryApplicationFile":
                program_id = key.value_data("ProgramId")
                tuple.add("program_id", value(program_id))

                file_id = key.value_data("FileId")
                tuple.add("file_id", value(file_id))
                tuple.add("sha1", value(normalize_amcache_sha1(file_id)))

                size = key.value_data("Size")
                tuple.add("size", value(parse_int(size)))

                name = key.value_data("Name")
                path = key.value_data("LowerCaseLongPath")
                tuple.add("path", value(path))
                # if we have the path but not the name, we can parse the path to fill the name
                if path and not name:
                    name = path[1 + path.rindex("\\") :]

                tuple.add("name", value(name))

                company_name = key.value_data("Publisher")
                tuple.add("company_name", value(company_name))

                version = key.value_data("Version")
                tuple.add("version", value(version))

                binary_type = key.value_data("BinaryType")
                tuple.add("binary_type", value(binary_type))

                product_name = key.value_data("ProductName")
                tuple.add("product_name", value(product_name))

                product_version = key.value_data("ProductVersion")
                tuple.add("product_version", value(product_version))

                link_date = key.value_data("LinkDate")
                tuple.add("link_date", value(parse_date(link_date)))

                is_pe_file = key.value_data("IsPeFile")
                tuple.add("is_pe_file", value(is_pe_file))

                is_os_component = key.value_data("IsOsComponent")
                tuple.add("is_os_component", value(is_os_component))

            else:
                product_name = key.value_data("0")
                tuple.add("product_name", value(product_name))

                company_name = key.value_data("1")
                tuple.add("company_name", value(company_name))

                program_id = key.value_data("100")
                tuple.add("program_id", value(program_id))

                file_id = key.value_data("101")
                tuple.add("file_id", value(file_id))
                tuple.add("sha1", value(normalize_amcache_sha1(file_id)))

                file_version = key.value_data("2")
                tuple.add("file_version", value(file_version))

                version_language = key.value_data("3")
                tuple.add("version_language", value(parse_int(version_language)))

                product_version = key.value_data("5")
                tuple.add("product_version", value(product_version))

                size = key.value_data("6")
                tuple.add("size", value(parse_int(size)))

                image_size = key.value_data("7")
                tuple.add("image_size", value(parse_int(image_size)))

                creation_date = key.value_data("12")
                if creation_date and isinstance(creation_date, int):
                    tuple.add("creation_date", value(filetime_to_utc(creation_date)))

                path_attr = key.value_data("15")
                if path_attr:
                    tuple.add("path", value(path_attr))
                    name = path_attr[1 + path_attr.rindex("\\") :]
                    tuple.add("name", value(name))

                modification_date = key.value_data("17")
                if modification_date and isinstance(modification_date, int):
                    tuple.add(
                        "modification_date", value(filetime_to_utc(modification_date))
                    )

                original_filename = key.value_data("c")
                tuple.add("original_filename", value(original_filename))

                link_date = key.value_data("f")
                tuple.add("link_date", value(parse_date(link_date)))

            tuple.add("key_path", value(key.path))
            tuple.add("key_modif_time", value(key.mtime))
            tuple.add("key_security", Value.Object(key.security_descriptor.to_record()))
            output.write(tuple)
        except Exception as e:
            # traceback.print_exception(e)

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


def parse_int(value) -> int | None:
    if value:
        if isinstance(value, str):
            return int(value, base=16)
        elif isinstance(value, int):
            return value
