from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_xml,
)

from dfir_ogre_plugin_windows.common import GuidParser

LOG_BEFORE_FAIL = 100


class XML(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "XML",
            "Extract data from a XML File",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(
            plugin_file,
            python={"@CLSID": GuidParser.build("id")},
        )
        return parse_xml(input_file, run_config, plugin_config, metadata)
