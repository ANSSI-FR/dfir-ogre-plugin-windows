from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_xml,
)

from dfir_ogre_plugin_windows.common import AmcacheSha1Parser, GuidParser

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
            python={
                "@CLSID": GuidParser.build("id"),
                # Amcache XML reports: file identifiers are "0000" + SHA-1
                "@DriverId": AmcacheSha1Parser.build("sha1"),
                "@Id": AmcacheSha1Parser.build("sha1"),
                "InstallInfo/@Id": AmcacheSha1Parser.build("sha1"),
            },
        )
        return parse_xml(input_file, run_config, plugin_config, metadata)
