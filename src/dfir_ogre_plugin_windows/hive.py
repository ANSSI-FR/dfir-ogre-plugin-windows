from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    RunConfiguration,
    RunReport,
    parse_hive_keys, parse_hive_values,
)


class HiveKeys(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "HiveKey",
            "Extract Keys and Values from Windows Registry File",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        root_name = run_config.params.get("root_name", None)
        filter = run_config.params.get("filter", None)

        return parse_hive_values(
            input_file,
            run_config,
            plugin_config,
            metadata,
            root_name,
            filter,
        )
