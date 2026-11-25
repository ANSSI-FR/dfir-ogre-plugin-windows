import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration
from dfir_ogre_plugin_windows import TCPConn

from . import BASE_TEMP_FOLDER, CONF_FOLDER


DATA_FOLDER = os.path.join("tests", "data")
TCPVCON_FILE = os.path.join(DATA_FOLDER, "tcpconv", "Tcpvcon.txt")
CONF_FILE = os.path.join(CONF_FOLDER, "tcp_connection.xml")

TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "tcp_connection")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TcpConnectionTest(TestCase):
    """Tests for the TCPView “Tcpvcon.txt” export parser."""

    #   python -m unittest tests.test_tcp_connection.TcpConnectionTest.test_tcp_connection -v
    def test_tcp_connection(self):
        base_output_name = "Tcpvcon"
        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".tcpvcon.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
                    include_empty=True,            # no extra parameters
        )

        metadata = Metadata("test")
        parser = TCPConn()
        run_configuration = RunConfiguration([output_config])

        report = parser.parse(TCPVCON_FILE, CONF_FILE, run_configuration, metadata)
             # helpful if a test fails
        self.assertIsNone(report.last_error)   # no error should be reported

        file_report = report.output_reports[0].file_reports[0]
        self.assertEqual(file_report.num_lines, 35)
        self.assertEqual(file_report.file_name, output_file)

        # ------------------------------------------------------------------
        # Spot‑check a few records to ensure fields are parsed correctly
        # ------------------------------------------------------------------
        with open(output_file) as fp:
            for i, line in enumerate(fp):
                jsoned = json.loads(line)

                # 0 – first TCP entry
                if i == 0:
                    self.assertEqual(jsoned["protocol"], "TCP")
                    self.assertEqual(jsoned["process_name"], "svchost.exe")
                    self.assertEqual(jsoned["pid"], 960)
                    self.assertEqual(jsoned["state"], "LISTENING")
                    self.assertEqual(jsoned["local_adress"], "0.0.0.0")
                    self.assertEqual(jsoned["remote_adress"], "0.0.0.0")

                # 13 – first UDP entry (state is “*” for UDP)
                if i == 13:
                    self.assertEqual(jsoned["protocol"], "UDP")
                    self.assertEqual(jsoned["process_name"], "svchost.exe")
                    self.assertEqual(jsoned["pid"], 2024)
                    self.assertEqual(jsoned["state"], "*")
                    self.assertEqual(jsoned["local_adress"], "0.0.0.0")
                    self.assertEqual(jsoned["remote_adress"], "*")

                # 20 – first IPv6 entry – brackets must be stripped
                if i == 20:
                    self.assertEqual(jsoned["protocol"], "TCPV6")
                    self.assertEqual(jsoned["process_name"], "svchost.exe")
                    self.assertEqual(jsoned["pid"], 960)
                    self.assertEqual(jsoned["state"], "LISTENING")
                    # IPv6 addresses appear without surrounding brackets
                    self.assertEqual(jsoned["local_adress"], "0:0:0:0:0:0:0:0")
                    self.assertEqual(jsoned["remote_adress"], "0:0:0:0:0:0:0:0")

                # 34 – last line (UDPV6 entry)
                if i == 34:
                    self.assertEqual(jsoned["protocol"], "UDPV6")
                    self.assertEqual(jsoned["process_name"], "svchost.exe")
                    self.assertEqual(jsoned["pid"], 1472)
                    self.assertEqual(jsoned["state"], "*")
                    self.assertEqual(jsoned["local_adress"], "0:0:0:0:0:0:0:0")
                    self.assertEqual(jsoned["remote_adress"], "*")
