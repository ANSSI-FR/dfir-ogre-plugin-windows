import json
import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    Record,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows import RegNetworkConfig

from . import CONF_FOLDER, TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class NetworkConfig(TestCase):
    def test_missing_enable_dhcp_defaults_to_static(self):
        values = {
            "IPAddress": ["192.0.2.10"],
            "SubnetMask": ["255.255.255.0"],
            "Domain": "example.test",
            "NameServer": "192.0.2.53",
        }
        key = Mock()
        key.values.return_value = list(values.values())
        key.value_data.side_effect = lambda name, default=None: values.get(
            name, default
        )
        key.value.return_value = None
        key.path = (
            r"\HKLM\System\ControlSet001\Services\Tcpip\Parameters"
            r"\Interfaces\static-without-flag"
        )
        key.mtime = datetime(2026, 1, 1, tzinfo=timezone.utc)
        key.security_descriptor.to_record.return_value = Record()

        output = Mock()
        report = RunReport()
        RegNetworkConfig().parse_key(key, output, report)

        self.assertIsNone(report.last_error)
        self.assertEqual(output.write.call_count, 1)
        record = json.loads(output.write.call_args.args[0].to_string())
        self.assertFalse(record["dhcp"])
        self.assertEqual(record["ip_address"], "192.0.2.10")
        self.assertEqual(record["network_mask"], "255.255.255.0")
        self.assertEqual(record["dns_suffix"], "example.test")
        self.assertEqual(record["name_servers"], "192.0.2.53")

    def test_empty_interface_key_is_ignored_without_error(self):
        key = Mock()
        key.values.return_value = []
        key.value_data.side_effect = AssertionError(
            "empty interface key data should not be read"
        )

        output = Mock()
        report = RunReport()
        RegNetworkConfig().parse_key(key, output, report)

        self.assertIsNone(report.last_error)
        output.write.assert_not_called()

    # python -m unittest tests.hive.test_network_config.NetworkConfig.test_network_config -v
    def test_network_config(self):
        plugin_file = os.path.join(CONF_FOLDER, "network_configuration.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat")

        base_output_name = "network_config"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".network_config.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=False,
        )
        run_config = RunConfiguration([output_config])

        metadata = Metadata("test")
        parser = RegNetworkConfig()
        self.assertEqual("RegNetworkConfig", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 4
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0

            for line in fp:
                js = json.loads(line)
                if i == 1:
                    js["description"] = "dhcp_enabled: false - ip_address: 10.1.7.1"
                    js["additional_description"] = (
                        "network_mask: 255.0.0.0 - gateway: 10.0.0.2"
                    )
                i += 1
            self.assertEqual(i, expected_lines)
