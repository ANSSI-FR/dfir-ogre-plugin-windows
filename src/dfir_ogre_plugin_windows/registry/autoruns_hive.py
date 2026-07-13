import logging
import os
from typing import Dict, List, Tuple
from construct import CString
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

SYSTEM_KEYS: Dict[str, List[Tuple[str, Tuple]]] = {
    'Session Manager *Execute': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager',
        ('BootExecute', 'BootShell', 'Execute', 'SetupExecute'))
    ],
    'Service Control Manager Extension': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control',
        ('ServiceControlManagerExtension',))
    ],
    'Crashdump Filter': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\CrashControl', ('DumpFilters', )),
    ],
    'LSA Packages': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Lsa',
        ('Authentication Packages', 'Notification Packages', 'Security Packages', )),
    ],
    'Network Providers': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\NetworkProvider\\*', ('ProviderOrder', )),
    ],
    'Security Providers': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\SecurityProviders', ('SecurityProviders',)),
    ],
    'Application Certification Dlls': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager\\AppCertDlls', ('*',)),
    ],
    'Excluded Known Dlls': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager', ('ExcludeFromKnownDlls',)),
    ],
    'WinSock Helper Dlls': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Services\\*\\Parameters\\Winsock', ('HelperDllName',)),
    ],
    'Null Session Pipes': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Services\\lanmanserver\\Parameters\\NullSessionPipes', ('pipes',)),
    ],
    'Null Session Shares': [
        ('\\HKLM\\SYSTEM\\*ControlSet*\\Services\\lanmanserver\\Parameters\\NullSessionShares', ('shares',)),
    ],
}
class RegAutorunsSystem(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAutorunsSystem",
            "Extract Persistence mechanisms from the System Registry",
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
            reg = Registry.load(input_file, "\\HKLM\\SYSTEM")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata, None) as output:
            try:
                for persistence_type, paths in SYSTEM_KEYS.items():
                    for (path, target_values) in paths:
                        keys = reg.glob_keys(path)
                        for key in keys:
                            parse_key(key, persistence_type,target_values,output)

                parse_winsock_parameters(reg, output)
            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report



SOFTWARE_KEYS: Dict[str, List[Tuple[str, Tuple]]] = {
    'AppInit DLLs': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Windows',
         ('AppInit_DLLs',))
    ],
    'Image File Execution Option': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\*',
         ('Debugger',))
    ],
    'Winlogon UserInit': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon',
         ('UserInit',)),
    ],
    'Winlogon Shell': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon',
         ('Shell',)),
    ],
    'Winlogon Notify': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify',
         ('DllName',)),
    ],
    'Startup Run': [
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce\\Setup', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnceEx\\*',('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnceEx\\*\\Depend', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunServices', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunServicesOnce', ('*',)),
        ('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer\\Run', ('*',)),
    ],

    'Shell Load and Run': [
        ('HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Windows', ('Load', 'Run')),
    ],
}
class RegAutorunsSoftware(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAutorunsSoftware",
            "Extract Persistence mechanisms from the Software Registry",
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
            reg = Registry.load(input_file, "\\HKLM\\SOFTWARE")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata, None) as output:
            try:
                for persistence_type, paths in SOFTWARE_KEYS.items():
                    for (path, target_values) in paths:
                        keys = reg.glob_keys(path)
                        for key in keys:
                            parse_key(key, persistence_type,target_values,output)

                startup_keys = [
                    '\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\Scripts\\Startup\\*',
                    '\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\Scripts\\Shutdown\\*',
                ]
                parse_startup_scripts(startup_keys,reg, output)

            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report

USER_KEYS: Dict[str, List[Tuple[str, Tuple]]] = {
    'Winlogon UserInit': [
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon',
         ('UserInit',))
    ],
    'Winlogon Shell': [
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon',
         ('Shell',))
    ],
    'Winlogon Notify': [
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Notify',
         ('DllName',))
    ],
    'Startup Run': [
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce\\Setup', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnceEx\\*', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnceEx\\*\\Depend', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunServices', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunServicesOnce', ('*',)),
        ('\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer\\Run', ('*',)),
    ],
    'Office Test': [
        ('\\HKCU\\Software\\Microsoft\\Office Test\\Special\\Perf', ('*',))
    ],
    'Shell Load and Run': [
        ('\\HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Windows', ('Load', 'Run')),
    ],
    'Screen Saver': [
        ('\\HKCU\\Control Panel\\Desktop', ('SCRNSAVE.EXE',)),
    ],
}

class RegAutorunsUser(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAutorunsUser",
            "Extract Persistence mechanisms from the User Registry",
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
                for persistence_type, paths in USER_KEYS.items():
                    for (path, target_values) in paths:
                        keys = reg.glob_keys(path)
                        for key in keys:
                            parse_key(key, persistence_type,target_values,output)

                startup_keys = [
                    '\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\Scripts\\Logon\\*',
                    '\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\Scripts\\Logoff\\*',
                ]
                parse_startup_scripts(startup_keys,reg, output)
            except Exception as e:
                report.add_error(f"{e}")
            report.add_output_report(output.get_report())

        return report


def parse_key(
    key: RegKey, persistence_type:str, target_values: Tuple, output: Output
):
    record = Record()
    record.add("type",value(persistence_type))

    value_array: List[Value]= []

    for target in target_values:

        if target == '*':
            for val in key.values():
                data = val.data()
                if data:
                    val_rec = Record()
                    val_rec.add("name", value(val.name()))
                    val_rec.add("data", value(val.data()))
                    value_array.append(Value.Object(val_rec))

        else:
            val = key.value_data(target)
            if val:
                val_rec = Record()
                val_rec.add("name", value(target))
                val_rec.add("data", value(val))
                value_array.append(Value.Object(val_rec))

    if len(value_array) == 0:
        return

    record.add("values", Value.Array(value_array))
    record.add("key_path", value(key.path))
    record.add("key_modif_time", value(key.mtime))
    record.add("key_security", Value.Object(key.security_descriptor.to_record()))
    output.write(record)


def parse_startup_scripts(keys: List[str], registry: Registry, output: Output):
        persistence_type = 'Startup Scripts'
        for key in keys:
            for policy_key in registry.glob_keys(key):
                script_path = policy_key.value_data('FileSysPath')
                policy_name = policy_key.value('GPOName')
                for script_key in policy_key.sub_keys():
                    script_file = script_key.value_data('Script')
                    if not script_file:
                        continue
                    if os.path.isabs(script_file):
                        script_full_path = script_file
                    elif script_path:

                        script_full_path = os.path.join(script_path, script_file)
                    else:
                        script_full_path = os.path.join('<unknown path>', script_file)

                    script_params = script_key.value_data('Parameters')

                    value_array: List[Value]= []
                    val_rec = Record()
                    val_rec.add("name", value("script_path"))
                    val_rec.add("data", value(script_full_path))
                    value_array.append(Value.Object(val_rec))

                    val_rec = Record()
                    val_rec.add("name", value("script_params"))
                    val_rec.add("data", value(script_params))
                    value_array.append(Value.Object(val_rec))

                    record = Record()
                    record.add("type",value(persistence_type))
                    record.add("values", Value.Array(value_array))
                    record.add("key_path", value(script_key.path))
                    record.add("key_modif_time", value(script_key.mtime))
                    record.add("key_security", Value.Object(script_key.security_descriptor.to_record()))

                    output.write(record)

def parse_winsock_parameters(registry: Registry, output: Output):
        persistence_type = 'Winsock2 Parameters'

        key_path = '\\HKLM\\SYSTEM\\*ControlSet*\\Services\\WinSock2\\Parameters\\NameSpace_Catalog5\\*\\*'
        for key in registry.glob_keys(key_path):

            value_array: List[Value]= []  # pyright: ignore[reportRedeclaration]
            display_string = key.value_data('DisplayString')
            val_rec = Record()
            val_rec.add("name", value("display"))
            val_rec.add("data", value(display_string))
            value_array.append(Value.Object(val_rec))

            library_path = key.value_data('LibraryPath')
            val_rec = Record()
            val_rec.add("name", value("library_path"))
            val_rec.add("data", value(library_path))
            value_array.append(Value.Object(val_rec))

            record = Record()
            record.add("type",value(persistence_type))
            record.add("values", Value.Array(value_array))
            record.add("key_path", value(key.path))
            record.add("key_modif_time", value(key.mtime))
            record.add("key_security", Value.Object(key.security_descriptor.to_record()))
            output.write(record)

        key_path = '\\HKLM\\SYSTEM\\*ControlSet*\\Services\\WinSock2\\Parameters\\Protocol_Catalog9\\*\\*'
        for key in registry.glob_keys(key_path):

            value_array: List[Value]= []
            catalog_item = key.value_data('PackedCatalogItem')
            if catalog_item:
                item = CString("utf8").parse(catalog_item)
            else:
                item = None

            val_rec = Record()
            val_rec.add("name", value("PackedCatalogItem"))
            val_rec.add("data", value(item))
            value_array.append(Value.Object(val_rec))

            record = Record()
            record.add("type",value(persistence_type))
            record.add("values", Value.Array(value_array))
            record.add("key_path", value(key.path))
            record.add("key_modif_time", value(key.mtime))
            record.add("key_security", Value.Object(key.security_descriptor.to_record()))
            output.write(record)
