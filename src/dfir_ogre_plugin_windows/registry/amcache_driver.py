import logging
from datetime import datetime, timezone

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

from dfir_ogre_plugin_windows.common import normalize_amcache_sha1, value

logger = logging.getLogger(__name__)


class RegAmCacheDriver(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAmCacheDriver",
            "Retrieve drivers from the AmCache hive",
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

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys("\\AmCache\\Root\\InventoryDriverBinary\\*")
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        try:
            tuple = Record()

            if key.name.startswith("0000"):
                driver_id = key.name

            else:
                driver_id = key.value_data("DriverId")

                path = key.name.replace("/", "\\")
                tuple.add("path", value(path))

            tuple.add("driver_id", value(driver_id))
            tuple.add("sha1", value(normalize_amcache_sha1(driver_id)))

            name = key.value_data("DriverName")
            tuple.add("name", value(name))

            inf = key.value_data("Inf")
            tuple.add("inf", value(inf))

            version = key.value_data("DriverVersion")
            tuple.add("version", value(version))

            product = key.value_data("Product")
            tuple.add("product", value(product))

            product_version = key.value_data("ProductVersion")
            tuple.add("product_version", value(product_version))

            wdf_version = key.value_data("WdfVersion")
            tuple.add("wdf_version", value(wdf_version))

            company = key.value_data("DriverCompany")
            tuple.add("company", value(company))

            package_name = key.value_data("DriverPackageStrongName")
            tuple.add("package_name", value(package_name))

            service = key.value_data("Service")
            tuple.add("service", value(service))

            driver_type = key.value_data("DriverType")
            tuple.add("driver_type", value(parse_int(driver_type)))

            compilation_date = key.value_data("DriverTimeStamp")
            tuple.add("compilation_date", value(parse_date(compilation_date)))

            checksum = key.value_data("DriverCheckSum")
            tuple.add("checksum", value(parse_int(checksum)))

            image_size = key.value_data("ImageSize")
            tuple.add("image_size", value(parse_int(image_size)))

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
