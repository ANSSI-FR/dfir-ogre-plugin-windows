from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_sqlite,
)

from dfir_ogre_plugin_windows.common import GuidParser

LOG_BEFORE_FAIL = 100


class SQLite(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "SQLite",
            "Extract data by querying a SQLite database.",
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
            python={"AppActivityId": GuidParser.build("app_activity_id")},
        )
        return parse_sqlite(
            input_file, run_config, plugin_config, metadata, LOG_BEFORE_FAIL
        )
