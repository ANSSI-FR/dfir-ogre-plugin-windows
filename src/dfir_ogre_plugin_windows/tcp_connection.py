import re

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
)
from dfir_ogre_plugin_windows.common import value

# ----------------------------------------------------------------------
# Regular expression that captures all fields.
#   proto   – e.g. TCP, UDP, TCPV6, UDPV6
#   proc    – process name (may contain spaces, but never commas)
#   pid     – numeric process id
#   state   – LISTENING, ESTABLISHED, … (can be empty for UDP)
#   local   – local address (IPv4 or IPv6, IPv6 is wrapped in “[ … ]”)
#   remote  – remote address (same format, “*” for UDP/unknown)
# ----------------------------------------------------------------------
LINE_RE = re.compile(
    r"""^
    (?P<proto>TCPV?6?|UDPV?6?) ,          # protocol
    (?P<proc>[^,]+) ,                     # process name
    (?P<pid>\d+) ,                        # pid
    (?P<state>[^,]*) ,                    # state (may be empty)
    (?P<local>\[?[^\],]+\]?) ,            # local address (optionally in [])
    (?P<remote>\[?[^\],]+\]?)             # remote address (optionally in [])
    $""",
    re.VERBOSE,
)

class TCPConn(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "TCPConn", " parse a TCPView “Tcpvcon.txt” export."
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
        with open(input_file) as input:
            with Output(run_config, plugin_config, metadata) as output:
                for line in input:
                    line_match = LINE_RE.match(line.strip())
                    if  line_match:

                        record = Record()
                        record.add("protocol", value(line_match.group("proto")))
                        record.add("process_name", value(line_match.group("proc")))
                        record.add("pid", value(int(line_match.group("pid"))))
                        record.add("state", value(line_match.group("state")))
                        local = _strip_brackets(line_match.group("local"))
                        record.add("local_adress", value(local))
                        remote = _strip_brackets(line_match.group("remote"))
                        record.add("remote_adress", value(remote))

                        output.write(record)

        report.add_output_report(output.get_report())
        return report

def _strip_brackets(addr: str) -> str:
    """Remove surrounding brackets from an IPv6 address, if present."""
    return addr[1:-1] if addr.startswith("[") and addr.endswith("]") else addr
