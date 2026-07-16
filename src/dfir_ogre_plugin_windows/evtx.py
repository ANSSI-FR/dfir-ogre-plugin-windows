from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_evtx,
)

from dfir_ogre_plugin_windows.common import GuidParser


class Evtx(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription("Evtx", "Windows Event Log parser")

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(
            plugin_file,
            python={
                "ClassGuid": GuidParser.build("class_guid"),
                "Guid": GuidParser.build("guid"),
            },
        )
        return parse_evtx(input_file, run_config, plugin_config, metadata)
