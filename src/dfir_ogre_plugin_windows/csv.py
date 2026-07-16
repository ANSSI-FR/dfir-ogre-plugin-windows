from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_csv,
)
from typing_extensions import override

from dfir_ogre_plugin_windows.common import GuidParser

LOG_BEFORE_FAIL = 100


class Csv(OgrePlugin):
    @override
    def description(self) -> PluginDescription:
        return PluginDescription(
            "Csv",
            "A generic CSV parser.",
        )

    @override
    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        python_mapping = {
            "ShadowCopyId": GuidParser.build("shadow_copy"),
            "SnapshotID": GuidParser.build("snapshot_id"),
        }
        plugin_config = PluginConfiguration.load(
            plugin_file,
            python=python_mapping,
        )
        return parse_csv(
            input_file, run_config, plugin_config, metadata, LOG_BEFORE_FAIL
        )
