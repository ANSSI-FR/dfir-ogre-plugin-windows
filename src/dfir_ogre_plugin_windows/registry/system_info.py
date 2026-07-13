from dataclasses import dataclass
import logging
from datetime import datetime, timezone
import os
import re
from typing import Any, List, Set
from zoneinfo import ZoneInfo
from dfir_ogre_common import (
    OgreBatchedPlugin,
    BatchEntry,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc, value,win_tz_to_iana
from dfir_ogre_plugin_windows.wer import Dict

logger = logging.getLogger(__name__)
@dataclass
class Registries:
    system: Registry
    software: Registry
    batch_entry: BatchEntry

class RegSystemInfo(OgreBatchedPlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegSystemInfo",
            "Get system info from the SYSTEM and SOFWARE hives",
        )

    def parse(
        self,
        input_files: List[BatchEntry],
        plugin_file: str,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()
        for registries in build_registries_by_vss(input_files, report):
            with Output(registries.batch_entry.run_config, plugin_config, registries.batch_entry.metadata) as output:
                try:
                    self.build_system_info(registries,output,report )
                except Exception as e:
                    report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def build_system_info(self, reg: Registries, output: Output,report: RunReport):
        record = Record()

        controlset = get_data(reg.system, "\\HKLM\\SYSTEM\\Select","Current" )
        current_control_set = "ControlSet000"
        if controlset:
            current_control_set = 'ControlSet'+str(controlset).zfill(3)
            record.add("control_set", value(current_control_set))

        product_name = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', "ProductName")
        record.add("product_name", value(product_name))

        shutdown_time_data = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\Windows', "ShutdownTime")
        if shutdown_time_data:
            shutdown_time = filetime_to_utc(int.from_bytes(shutdown_time_data, byteorder='little'))
            record.add("shutdown_date", value(shutdown_time))

        computer_name = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\ComputerName\\ComputerName', "ComputerName")
        if not computer_name:
            computer_name =     computer_name = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\ComputerName\\ActiveComputerName', "ComputerName")

        record.add("computer_name", value(computer_name))

        timezone_name = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\TimeZoneInformation', "TimeZoneKeyName")
        record.add("timezone_windows", value(timezone_name))

        iana_timezone = win_tz_to_iana.get(str(timezone_name), None)

        if iana_timezone:
            timezone_info  = ZoneInfo(iana_timezone)
        else:
            timezone_info = None # fallback to the local timezone of the machine that runs this program

        record.add("timezone_iana", value(iana_timezone))

        tmp_local_install_date = get_data(reg.software,"\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion","InstallDate")

        if tmp_local_install_date:
            lid = datetime.fromtimestamp(float(tmp_local_install_date), tz=timezone_info)
            #do not write it as a date to avoid putting it in the timeline
            record.add("install_date_local", value(str(lid)))
            install_date = lid.astimezone(timezone.utc)
            record.add("install_date", value(install_date))


        build_number = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', 'CurrentBuildNumber')
        record.add("build_number", value(build_number))
        os_version = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', 'CurrentVersion')
        # Windows 8.1 and 10 both have 6.3 as CurrentVersion, we need the build number to tell them apart
        # First build of Windows 10 is 9841
        if build_number and os_version == '6.3' and int(build_number) >= 9841:
            major_version_number = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', 'CurrentMajorVersionNumber')
            minor_version_number = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', 'CurrentMinorVersionNumber')
            os_version = '{0}.{1}'.format(major_version_number,minor_version_number)

        record.add("os_version", value(os_version))
        architecture = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\Session Manager\\Environment', 'PROCESSOR_ARCHITECTURE')
        record.add("architecture", value(architecture))

        domain = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\History', 'MachineDomain')
        if not domain :
            # Fallback to ugly hack (DC dns name: can it be different than AD domain name ?)
            domain = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\History', 'DCName')
            domain = '.'.join(domain.split('.')[1:]) if domain else None
        if not domain:
            domain = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Services\\Tcpip\\Parameters', "Domain")
        record.add("domain", value(domain))

        system_root = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion', 'SystemRoot')
        record.add("system_root", value(system_root))

        #windows update
        wu_last_check = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\Results\\Detect','LastSuccessTime' )
        if wu_last_check:
            wu_last_check_date = datetime.strptime(wu_last_check,'%Y-%m-%d %H:%M:%S' ).replace(tzinfo=timezone.utc)
            record.add("wu_last_check", value(wu_last_check_date))

        wu_last_download = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\Results\\Download','LastSuccessTime' )
        if wu_last_download:
            wu_last_download = datetime.strptime(wu_last_download,'%Y-%m-%d %H:%M:%S' ).replace(tzinfo=timezone.utc)
            record.add("wu_last_download", value(wu_last_download))


        wu_last_install = get_data(reg.software,'\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\Results\\Install','LastSuccessTime' )
        if wu_last_install:
            wu_last_install = datetime.strptime(wu_last_install,'%Y-%m-%d %H:%M:%S' ).replace(tzinfo=timezone.utc)
            record.add("wu_last_install", value(wu_last_install))

        # Check if EMET is installed
        if reg.software.glob_keys('\\HKLM\\SOFTWARE\\Microsoft\\EMET'):
            record.add("has_emet", value(True))
        else:
            record.add("has_emet", value(False))

        # Check if Application Whitelisting is enabled
        if reg.software.glob_keys('\\HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\SrpV2'):
            record.add("app_whitelisting", value("AppLocker"))
        else:
            val = None
            for key in reg.software.glob_keys('\\HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\safer\\codeidentifiers'):
                if key.sub_keys():
                    val = 'SRP'
                    break
            record.add("app_whitelisting", value(val))
        #interfaces
        guids:Set[str]=set()
        interfaces_old = reg.system.glob_keys('\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\Network\\{4D36E972-E325-11CE-BFC1-08002BE10318}')
        for interface_old in interfaces_old:
            for i in interface_old.sub_keys():
                if i.name not in ['Descriptions']:
                    guids.add(i.name.lower())

        # group membership
        add_group_membership(reg.software, record)
        #starting with W7
        interfaces_old = reg.system.glob_keys('\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\NetworkSetup2\\Interfaces')
        for interface_old in interfaces_old:
            for i in interface_old.sub_keys():
                guids.add(i.name.lower())

        interfaces: List[Value] = []
        for guid in guids:
            interface = Record()
            interface.add("guid", value(guid))

            name = get_data(reg.system,'\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\Network\\{4D36E972-E325-11CE-BFC1-08002BE10318}\\'+guid.upper()+'\\Connection', "Name")

            net_keys = reg.system.glob_keys('\\HKLM\\SYSTEM\\'+current_control_set+'\\Control\\NetworkSetup2\\Interfaces\\'+guid.upper()+'\\Kernel')
            if net_keys:
                net_key = net_keys.pop()
                if not name:
                    name = net_key.value_data("IfAlias")
                mac = net_key.value_data("PermanentAddress")
                interface.add("mac", value(mac))
                descr = net_key.value_data("IfDescr")
                interface.add("description", value(descr))

            interface.add("name", value(name))

            ipv4_keys = reg.system.glob_keys('\\HKLM\\SYSTEM\\'+current_control_set+'\\Services\\Tcpip\\Parameters\\Interfaces\\'+guid)
            if ipv4_keys:
                tcpip_key = ipv4_keys.pop()
                interface.add("ipv4", value(tcpip_key.value_data("IPAddress")))
                interface.add("dhcp_enabled", value(tcpip_key.value_data("EnableDHCP")))
                interface.add("dhcp_ipv4", value(tcpip_key.value_data("DhcpIPAddress")))
                interface.add("dhcp_ipv4_server", value(tcpip_key.value_data("DhcpServer")))

            ipv6_keys = reg.system.glob_keys('\\HKLM\\SYSTEM\\'+current_control_set+'\\Services\\Tcpip6\\Parameters\\Interfaces\\'+guid)
            if ipv6_keys:
                tcpip_key = ipv6_keys.pop()
                interface.add("ipv6", value(tcpip_key.value_data("IPAddress")))
                interface.add("dhcp_enabled", value(tcpip_key.value_data("EnableDHCP")))
                interface.add("dhcp_ipv6", value(tcpip_key.value_data("DhcpIPAddress")))
                interface.add("dhcp_ipv6_server", value(tcpip_key.value_data("DhcpServer")))

            interfaces.append(Value.Object(interface))
        record.add("interfaces", Value.Array(interfaces))
        output.write(record)

def add_group_membership(reg: Registry, record: Record):
    re_sid = re.compile(r'^S-1-5-21-(?:\d+-){3}(?P<rid>\d+)$')
    groups = dict(
        is_dc=False,
        is_pki=False,
        is_ias=False,
    )
     # Get computer group membership (does not look for the primaryGroupId, so might be wrong)
    groups_list = reg.glob_keys('\\HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\GroupMembership')
    if groups_list:
        group = groups_list.pop()
        for reg_value in group.values():
            if reg_value.name().startswith('Group'):
                match = re_sid.match(reg_value.data())
                if match:
                    rid = match.group('rid')
                    if rid == '516':
                        groups['is_dc'] = True
                    elif rid == '517':
                        groups['is_pki'] = True
                    elif rid == '553':
                        groups['is_ias'] = True

    record.add('is_dc', value(groups['is_dc']))
    record.add('is_pki', value(groups['is_pki']))
    record.add('is_ias', value(groups['is_ias']))



def print_key(reg: Registry, key: str):
    keys =  reg.glob_keys(key)
    for reg_key in keys:

        print(reg_key.to_record().to_string())


def get_data(reg: Registry,path:str, name:str) -> Any | None:
    keys = reg.glob_keys(path)
    if len(keys) > 0:
        reg_key = keys.pop()
        value = reg_key.value(name)
        if value:
            return value.data()

@dataclass
class RegistriesTmp:
    system: Registry | None
    software: Registry | None
    batch_entry: BatchEntry


### files are retrieved using the regexp: \\(?:SYSTEM|SOFTWARE)$
def build_registries_by_vss(input_files: List[BatchEntry],report :RunReport)->List[Registries]:
    tmp_vss_dict:Dict[str|None, RegistriesTmp] = {}
    for entry in input_files:
        file_path = ""
        if entry.metadata.original_filename:
            dirname = entry.metadata.original_filename.split("\\")
            dirname.pop()
            file_path = "/".join(dirname)
        key = str(entry.metadata.vss) + file_path
        key = key.lower()

        file = entry.metadata.original_filename or entry.file
        file = file.replace("\\","/")
        file = os.path.basename(file).lower()
        registries = tmp_vss_dict.get(key, RegistriesTmp(None, None, entry))

        if "system" in file:
            try:
                registries.system = Registry.load(entry.file,"\\HKLM\\SYSTEM")
            except Exception as e:
                report.add_error(f"{e}")
        elif "software" in file:
            try:
                registries.software = Registry.load(entry.file,"\\HKLM\\SOFTWARE")
            except Exception as e:
                report.add_error(f"{e}")

        tmp_vss_dict[key] = registries

    vss_list:List[Registries] =[]

    for key, value in tmp_vss_dict.items():
        if value.software and value.system:
            logger.info(f"Extracting data from hives in path : {key}")
            vss_list.append(Registries(value.system,value.software, value.batch_entry ))

    return vss_list
