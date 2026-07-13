
from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_csv,
    win_frn_hex_parser,
)


LOG_BEFORE_FAIL = 1000


class I30Info(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "I30Info",
            "I30Info parser.",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        rust_mapping = {
            "FRN": win_frn_hex_parser(""),
            "ParentFRN": win_frn_hex_parser("parent_"),
        }
        plugin_config = PluginConfiguration.load(plugin_file, extension=rust_mapping)
        return parse_csv(
            input_file,
            run_config,
            plugin_config,
            metadata,
            LOG_BEFORE_FAIL,
        )
