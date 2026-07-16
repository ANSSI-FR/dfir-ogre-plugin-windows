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

from dfir_ogre_plugin_windows.common import normalize_guid, value

logger = logging.getLogger(__name__)


class RegClsIdIUser(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegClsIdIUser",
            "List every user's class ids, from UsrClass hive",
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
            reg = Registry.load(input_file, "\\HKCR")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys("\\HKCR\\CLSID\\*")
                for key in keys:
                    parse_clsid(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report


class RegClsIdSoftware(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegClsIdSoftware",
            "Machine-wide CLSID registrations, from Software hive",
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
            reg = Registry.load(input_file, "\\HKLM\\Software")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys("\\HKLM\\Software\\Classes\\CLSID\\*")
                for key in keys:
                    # print(key.to_record().to_string())
                    parse_clsid(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report


def parse_clsid(key: RegKey, output: Output, report: RunReport):
    try:
        tuple = Record()
        tuple.add("guid", value(normalize_guid(key.name)))
        description = key.value_data("(default)")
        tuple.add("description", value(description))

        treat_as_key = key.sub_key("TreatAs")
        if treat_as_key:
            treat_as = treat_as_key.value_data("(default)")
            if treat_as:
                tuple.add("treat_as", value(normalize_guid(str(treat_as))))

        # Not sure if a CLSID can only have one of the following key (hence only one executable) or several
        executables = []
        for exec_type_key in ["InprocServer32", "LocalServer32", "InprocHandler32"]:
            exec_key = key.sub_key(exec_type_key)
            if exec_key:
                exec = exec_key.value_data("(default)")
                if exec:
                    if str(exec).endswith("mscoree.dll"):
                        # generate the assembly info parts from all the relevant values of the subkey.
                        assembly_info = ",".join(
                            f"{v.name()}={v.data()}"
                            for v in exec_key.values()
                            if v.name() in HANDLER_VALUES
                        )
                        executables.append(f"{exec},{assembly_info}")
                    else:
                        executables.append(exec)
        executable = " - ".join(executables)

        tuple.add("executable", value(executable))
        tuple.add("key_path", value(key.path))
        tuple.add("key_modif_time", value(key.mtime))
        tuple.add("key_security", Value.Object(key.security_descriptor.to_record()))
        output.write(tuple)
    except Exception as e:
        logger.error(f"{e}")
        report.add_error(f"{e}")


HANDLER_VALUES = (
    "Assembly",
    "Class",
    "CodeBase",
    "RuntimeVersion",
)
