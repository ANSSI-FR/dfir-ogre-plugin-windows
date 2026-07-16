from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_csv,
    win_frn_hex_parser,
    win_ntfs_flag_parser,
)

from dfir_ogre_plugin_windows.common import GuidParser

LOG_BEFORE_FAIL = 1000


class USNInfo(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "USNInfo",
            "USNInfo parser.",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        rust_mapping = {
            "FileAttributes": win_ntfs_flag_parser(),
            "FRN": win_frn_hex_parser(""),
            "ParentFRN": win_frn_hex_parser("parent_"),
        }
        plugin_config = PluginConfiguration.load(
            plugin_file,
            python={"SnapshotID": GuidParser.build("snapshot_id")},
            extension=rust_mapping,
        )
        return parse_csv(
            input_file,
            run_config,
            plugin_config,
            metadata,
            LOG_BEFORE_FAIL,
        )
