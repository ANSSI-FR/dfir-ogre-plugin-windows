import logging
from typing import Optional

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RegValue,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import add_list, value

logger = logging.getLogger(__name__)


class RegServicesControlSet(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegServicesControlSet",
            "Retrieve the services from the System hive control set",
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

        """Parse Services from \\HKLM\\System\\ControlSet*\\Services\\*"""
        try:
            reg = Registry.load(input_file, "\\HKLM\\System")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys("\\HKLM\\System\\*ControlSet*\\Services\\*")
                for key in keys:
                    self.parse_control_set_keys(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_control_set_keys(self, key: RegKey, output: Output, report: RunReport):
        try:
            service = Record()

            service.add("name", value(key.name))

            display_name = key.value_data("DisplayName")
            if isinstance(display_name, list):
                display_name = "".join(display_name)
            service.add("display_name", value(display_name))

            description = key.value_data("Description")
            service.add("description", value(description))

            error_control_data = key.value_data("ErrorControl")
            if error_control_data:
                error_control = SERVICE_ERROR_CONTROL_TYPES.get(
                    error_control_data, f"{error_control_data} - Unknown"
                )
                service.add("error_control", value(error_control))

            service_type = ServiceType(key.value("Type"))

            service.add("service_type", value(service_type.service_type_str))
            service.add("is_interactive", value(service_type.is_interactive))
            service.add("is_packaged_service", value(service_type.is_packaged_service))
            service.add("is_service_driver", value(service_type.is_service_driver))
            service.add("is_service_win32", value(service_type.is_service_win32))

            # Command line specifying what the service should execute. See the documentation; depending on the command line, the information present here is not sufficient.
            image_path = key.value_data("ImagePath")
            service.add("image_path", value(image_path))

            start_type_value = key.value("Start")
            if start_type_value:
                start_type = start_type_value.data()

                if start_type_value.type() == "REG_SZ":
                    start_type = int(start_type, base=16)

                stype = SERVICE_START_TYPES.get(start_type, str(start_type))
                service.add("start_type", value(stype))

            group = key.value_data("Group")
            service.add("group", value(group))

            tag = key.value_data("Tag")
            service.add("tag", value(tag))

            depend_on_group = key.value_data("DependOnGroup")
            add_list(service, "depend_on_group", depend_on_group)

            depend_on_service = key.value_data("DependOnService")
            add_list(service, "depend_on_service", depend_on_service)

            delete_flag = key.value_data("DeleteFlag")
            service.add("delete_flag", value(delete_flag))

            object_name = key.value_data("ObjectName")
            if service_type.is_service_driver:
                service.add("object_name", value(object_name))
            else:
                service.add("run_as", value(object_name))

            wow64 = key.value_data("WOW64")
            service.add("wow64", value(wow64))

            alias = key.value_data("Alias")
            service.add("alias", value(alias))

            delayed_auto_start = key.value_data("DelayedAutoStart")
            service.add("delayed_auto_start", value(delayed_auto_start))

            preshutdown_timeout = key.value_data("PreshutdownTimeout")

            service.add("preshutdown_timeout", value(preshutdown_timeout))

            service_sid_type_data = key.value_data("ServiceSidType")
            if service_sid_type_data:
                service_sid_type = SERVICE_SID_TYPES.get(
                    service_sid_type_data, f"{service_sid_type_data} - Unknown"
                )
                service.add("service_sid_type", value(service_sid_type))

            required_privileges = key.value_data("RequiredPrivileges")

            add_list(service, "required_privileges", required_privileges)

            launch_protected_data = key.value_data("LaunchProtected")
            if launch_protected_data:
                launch_protected = SERVICE_LAUNCH_PROTECTED.get(
                    launch_protected_data, f"{launch_protected_data} - Unknown"
                )
                service.add("launch_protected", value(launch_protected))

            user_service_flags = key.value_data("UserServiceFlags")
            service.add("user_service_flags", value(user_service_flags))

            svchost_split_disable = key.value_data("SvcHostSplitDisable")
            service.add("svchost_split_disable", value(bool(svchost_split_disable)))

            package_fullname = key.value_data("PackageFullName")
            service.add("package_fullname", value(package_fullname))

            app_usermodel_id = key.value_data("AppUserModelId")
            service.add("app_usermodel_id", value(app_usermodel_id))

            package_origin_data = key.value_data("PackageOrigin")
            if package_origin_data:
                package_origin = PACKAGE_ORIGIN.get(
                    package_origin_data, f"{package_origin_data} - Unknown"
                )
                service.add("package_origin", value(package_origin))

            ## We want to have all possible values for service_dll. The one under Parameters takes precedence over the one directly under the service key,
            ## but we want to have all the information we can get for the analyst.

            service_dll = key.value_data("ServiceDll")
            service.add("service_dll", value(service_dll))

            service_manifest = key.value_data("ServiceManifest")
            service.add("service_manifest", value(service_manifest))

            service_main = key.value_data("ServiceMain")
            service.add("service_main", value(service_main))

            parameters_key = key.sub_key("Parameters")
            if parameters_key:
                parameters_key_last_modif = parameters_key.mtime
                service.add(
                    "parameters_key_last_modif", value(parameters_key_last_modif)
                )

                parameters_service_dll = parameters_key.value_data("ServiceDll")
                service.add("parameters_service_dll", value(parameters_service_dll))

                parameters_service_manifest = parameters_key.value_data(
                    "ServiceManifest"
                )
                service.add(
                    "parameters_service_manifest", value(parameters_service_manifest)
                )

                parameters_service_main = parameters_key.value_data("ServiceMain")
                service.add("parameters_service_main", value(parameters_service_main))

            performance_key = key.sub_key("Performance")
            if performance_key:
                performance_key_last_modif = performance_key.mtime
                service.add(
                    "performance_key_last_modif", value(performance_key_last_modif)
                )

                performance_library = performance_key.value_data("Library")
                service.add("performance_library", value(performance_library))

                performance_open_function = performance_key.value_data("Open")

                service.add(
                    "performance_open_function", value(performance_open_function)
                )

                performance_collect_function = performance_key.value_data("Collect")

                service.add(
                    "performance_collect_function", value(performance_collect_function)
                )

                performance_close_function = performance_key.value_data("Close")

                service.add(
                    "performance_close_function", value(performance_close_function)
                )

            failure_actions = key.value_data("FailureActions")
            service.add(
                "failure_actions",
                value(failure_actions),
            )

            failure_command = key.value_data("FailureCommand")
            service.add("failure_command", value(failure_command))

            failure_actions_on_non_crash_failures = key.value_data(
                "FailureActionsOnNonCrashFailures"
            )
            service.add(
                "failure_actions_on_non_crash_failures",
                value(bool(failure_actions_on_non_crash_failures)),
            )

            service.add("key_path", value(key.path))
            service.add("key_modif_time", value(key.mtime))
            service.add(
                "key_security", Value.Object(key.security_descriptor.to_record())
            )

            output.write(service)
        except Exception as e:
            report.add_error(f"{e}")


class ServiceType:
    """Converts the flags in ServiceType into human-understable info.
    Boolean values are assigned as Windows code does.
    """

    service_type: int = -1
    service_type_str: str = ""
    is_interactive: bool = False
    is_packaged_service: bool = False
    # To be a service driver, be a kernel, file_system or recognizer driver. Adapter might be treated differently but it is unclear...
    is_service_driver: bool = False
    # To be a WIN32 service, be a WIN32 own process or a WIN32 shared process service (or other service type combining those)
    is_service_win32: bool = False

    def __init__(self, val: Optional[RegValue]):
        if not val:
            return

        # Translate value according to type
        # Note : supports REG_SZ because orc2db does. No example found for tests.
        # When type is REG_SZ, the value is a string to be interpreted as an integer in hexadecimal notation,
        # whereas when the value is of usual type DWORD, it is directly an integer.
        if val.type() == "REG_SZ":
            my_value = int(val.data(), base=16)
        else:
            my_value = val.data()

        self.service_type = my_value & 0xFF
        self.service_type_str = SERVICE_TYPES.get(
            self.service_type, f"{self.service_type} - Unknown"
        )
        self.is_interactive = bool(my_value & 0x100)
        self.is_packaged_service = bool(my_value & 0x200)
        # To be a service driver, be a kernel, file_system or recognizer driver. Adapter might be treated differently but it is unclear...
        self.is_service_driver = bool(my_value & 0b1111)
        # To be a WIN32 service, be a WIN32 own process or a WIN32 shared process service (or other service type combining those)
        self.is_service_win32 = bool(my_value & 0b110000)


# Flag interpretation below was sourced from orc2db-python3 parser,
# MSDN (e.g. here : https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/change-method-in-class-win32-service) except for user services,
# and https://helgeklein.com/blog/per-user-services-in-windows-info-and-configuration/.
SERVICE_TYPES = {
    0x01: "Kernel driver",
    0x02: "(Kernel-mode) filesystem driver",
    0x04: "Adapter (reserved)",  # Obsolete.
    0x08: "Recognizer driver (reserved)",
    0x10: "Service WIN32 own process",
    0x20: "Service WIN32 share process",
    0x40: "User Service Template Key",  # Never exists by itself, type for User Service Template keys
    0x50: "User service own process",  # 0x10 | 0x40 => combined Own process & User Service
    0x60: "User service share process",  # 0x20 | 0x40 => combined Shared Process & User Service
    0x80: "SERVICE_USERSERVICE_INSTANCE",  # Never exists by itself, type for User Service Instances
    0xD0: "User service own process instance",  # 0x50 | 0x80 => combined User Service Own Process + Instance
    0xE0: "User service shared process instance",  # 0x60 | 0x80 => combined User Service Shared Process + Instance
}

SERVICE_START_TYPES = {
    0: "Boot start",
    1: "System start",
    2: "Auto start",
    3: "Ondemand start",
    4: "Disabled",
}

# Source : MSDN CreateService
SERVICE_ERROR_CONTROL_TYPES = {
    0: "Ignore Error",  # No warning logged or displayed.
    1: "Normal Error",  # On error, an event log message is written.
    2: "Severe Error",  # The startup program logs the error in the event log. If the last-known-good configuration is being started, the startup operation continues. Otherwise, the system is restarted with the last-known-good configuration.
    3: "Critical Error",  # The startup program logs the error in the event log, if possible. If the last-known-good configuration is being started, the startup operation fails. Otherwise, the system is restarted with the last-known good configuration.
}

# Source : Windows Internals 7th edition, chapter 10
SERVICE_SID_TYPES = {
    0x0: "SERVICE_SID_TYPE_NONE",
    0x1: "SERVICE_SID_TYPE_UNRESTRICTED",
    0x3: "SERVICE_SID_TYPE_RESTRICTED",
}

# Source : Windows Internals 7th edition, chapter 10
SERVICE_LAUNCH_PROTECTED = {
    0x0: "SERVICE_LAUNCH_PROTECTED_NONE",
    0x1: "SERVICE_LAUNCH_PROTECTED_WINDOWS",  # protected process
    0x2: "SERVICE_LAUNCH_PROTECTED_WINDOWS_LIGHT",  # protected process light
    0x3: "SERVICE_LAUNCH_PROTECTED_ANTIMALWARE_LIGHT",  # antimalware protected process light
    0x4: "SERVICE_LAUNCH_PROTECTED_APP_LIGHT",  # app protected process light ("internal only")
}

# Source : Windows Internals 7th edition (with little correction in semantics)
USER_SERVICE_FLAGS = {
    0x1: "USER_SERVICE_FLAG_DSMA_ALLOW",  # allows the default user to start the service
    0x2: "USER_SERVICE_FLAG_NONDSMA_ALLOW",  # allow non-default users to start the service
}

# Source : Windows Internals 7th edition, chapter 10
PACKAGE_ORIGIN = {
    0x1: "PACKAGE_ORIGIN_UNSIGNED",
    0x2: "PACKAGE_ORIGIN_INBOX",
    0x3: "PACKAGE_ORIGIN_STORE",
    0x4: "PACKAGE_ORIGIN_DEVELOPER_UNSIGNED",
    0x5: "PACKAGE_ORIGIN_DEVELOPER_SIGNED",
}
