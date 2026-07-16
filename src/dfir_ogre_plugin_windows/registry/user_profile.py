import logging
from typing import Dict

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import value

# from .api import RegKey, Registry

logger = logging.getLogger(__name__)


def _get_hidden_users(reg: Registry) -> Dict[str, bool]:
    hidden_users: Dict[str, bool] = {}
    for reg_key in reg.glob_keys(
        "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
        "\\SpecialAccounts\\UserList"
    ):
        for user_visibility in reg_key.values():
            hidden_users[user_visibility.name().casefold()] = (
                user_visibility.data() == 0
            )
    return hidden_users


class RegUserProfile(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegUserProfile",
            "List logged-on user profiles from Software hive",
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
        try:
            reg = Registry.load(input_file, "\\HKLM\\Software")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        hidden_users = _get_hidden_users(reg)

        with Output(run_config, plugin_config, metadata) as output:
            try:
                keys = reg.glob_keys(
                    "\\HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList\\*"
                )
                for key in keys:
                    self.parse_key(key, hidden_users, output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_key(
        self,
        key: RegKey,
        hidden_users: Dict[str, bool],
        output: Output,
        report: RunReport,
    ):
        try:
            tuple = Record()

            tuple.add("user_sid", value(key.name))
            image_path = key.value_data("ProfileImagePath")
            tuple.add("path", value(image_path))

            if image_path:
                profile = (image_path.split("\\"))[-1].lower()

                profile_lookup = profile.casefold()
                if profile_lookup in hidden_users:
                    tuple.add("is_hidden", value(hidden_users[profile_lookup]))

                tuple.add("user_name", value(profile))

            state = key.value_data("State")
            tuple.add("state", value(state))
            if state:
                is_admin = bool(0x100 & state)
                tuple.add("is_admin", value(is_admin))

            ref_count = key.value_data("RefCount")
            tuple.add("ref_count", value(ref_count))

            tuple.add("key_path", value(key.path))
            tuple.add("key_modif_time", value(key.mtime))
            tuple.add("key_security", Value.Object(key.security_descriptor.to_record()))
            output.write(tuple)
        except Exception as e:
            report.add_error(f"{e}")
