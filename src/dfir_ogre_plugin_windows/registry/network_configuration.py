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


class RegNetworkConfig(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegNetworkConfig",
            "Network configuration (mostly ip addresses) of the computer, from System hive",
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
            reg = Registry.load(input_file, "\\HKLM\\System")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys(
                    "\\HKLM\\System\\ControlSet*\\Services\\Tcpip\\Parameters\\Interfaces\\*"
                )
                for key in keys:
                    self.parse_key(key, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, output: Output, report: RunReport):
        if not key.values():
            return

        try:
            dhcp = key.value_data("EnableDHCP", 0)

            if dhcp == 0:
                dns_suffix = key.value_data("Domain")

                name_servers = key.value_data("NameServer")

                default_gateway_key = key.value("DefaultGateway")
                gateway = ""
                if default_gateway_key:
                    if default_gateway_key.type() == "REG_MULTI_SZ":
                        gateway = ",".join(default_gateway_key.data())
                    else:
                        gateway = default_gateway_key.data()

                for ip_address, network_mask in zip(
                    key.value_data("IPAddress", []),  # type: ignore
                    key.value_data("SubnetMask", []),  # type: ignore
                ):
                    pass
                    tuple = Record()
                    tuple.add("dhcp", value(False))

                    tuple.add("ip_address", value(ip_address))
                    tuple.add("network_mask", value(network_mask))

                    tuple.add("name_servers", value(name_servers))
                    tuple.add("dns_suffix", value(dns_suffix))

                    tuple.add("gateway", value(gateway))
                    tuple.add("key_path", value(key.path))
                    tuple.add("key_modif_time", value(key.mtime))
                    tuple.add(
                        "key_security",
                        Value.Object(key.security_descriptor.to_record()),
                    )
                    output.write(tuple)
            else:
                tuple = Record()
                tuple.add("dhcp", value(True))

                ip_address = key.value_data("DhcpIPAddress")
                tuple.add("ip_address", value(ip_address))

                network_mask = key.value_data("DhcpSubnetMask")
                tuple.add("network_mask", value(network_mask))

                dhcp_server = key.value_data("DhcpServer")
                tuple.add("dhcp_server", value(dhcp_server))

                dns_suffix = key.value_data("DhcpDomain")
                tuple.add("dns_suffix", value(dns_suffix))

                name_servers = key.value_data("DhcpNameServer")
                tuple.add("name_servers", value(name_servers))

                default_gateway_key = key.value("DhcpDefaultGateway")
                if default_gateway_key:
                    if default_gateway_key.type() == "REG_MULTI_SZ":
                        gateway = ",".join(default_gateway_key.data())
                    else:
                        gateway = default_gateway_key.data()
                    tuple.add("gateway", value(gateway))

                tuple.add("key_path", value(key.path))
                tuple.add("key_modif_time", value(key.mtime))
                tuple.add(
                    "key_security", Value.Object(key.security_descriptor.to_record())
                )
                output.write(tuple)
        except Exception as e:
            report.add_error(f"{e}")
