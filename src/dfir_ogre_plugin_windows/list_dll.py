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

PROCESS_HEADER_PATTERN = re.compile(
    r"""
    ^(?P<program_name>[a-zA-Z0-9_\-\.]+)\s+          # program name
    pid:\s*(?P<pid>\d+)\s*$                         # pid (integer)
    \n
    Command\s+line:\s*(?P<command_line>.+?)\s*$      # command line
    """,
    re.MULTILINE | re.VERBOSE
)

MODULE_LINE_PATTERN = re.compile(
    r"""
    ^(?P<base>0x[0-9A-Fa-f]{16})\s+                 # base address (16 hex chars)
    (?P<size_hex>0x[0-9A-Fa-f]+)\s+                # size (hexa)
    (?P<path>.+?)\s*$                              # path (lazy match, strip whitespace)
    """, re.MULTILINE | re.VERBOSE
)

class ListDll(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "ListDll", "parse Orc Listdll file"
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
            content = input.read()
            with Output(run_config, plugin_config, metadata) as output:
                # find all process block
                headers = list(PROCESS_HEADER_PATTERN.finditer(content))
                if not headers:
                    raise ValueError("No process header found, check the input file")

                for i, header in enumerate(headers):

                    program_name = header.group('program_name')
                    pid = int(header.group('pid'))
                    command_line = header.group('command_line').strip()

                    # Extract current block
                    start_pos = header.end()
                    end_pos = headers[i + 1].start() if i + 1 < len(headers) else len(content)
                    block = content[start_pos:end_pos]

                    # find all dll in the block
                    for mod in MODULE_LINE_PATTERN.finditer(block):
                        record = Record()
                        record.add("process_name", value(program_name))
                        record.add("pid", value(pid))
                        record.add("command_line", value(command_line))

                        base_addr = mod.group('base')
                        record.add("base_addr", value(base_addr))

                        size_hex = mod.group('size_hex')
                        record.add("size", value( int(size_hex, 16)))
                        path = mod.group('path').strip()
                        record.add("path", value( path))
                        output.write(record)

        report.add_output_report(output.get_report())
        return report
