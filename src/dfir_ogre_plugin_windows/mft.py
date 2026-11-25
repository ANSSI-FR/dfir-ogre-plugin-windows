from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_mft,
)


class MFT(OgrePlugin):
    """Raw $MFT parser, for collections that hold it instead of NTFSInfo."""

    def description(self) -> PluginDescription:
        return PluginDescription(
            "MFT",
            "Parse a raw NTFS Master File Table ($MFT).",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        return parse_mft(input_file, run_config, plugin_config, metadata)
