import logging

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

logger = logging.getLogger(__name__)

RECENT_DOCS_KEY = (
    "\\HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RecentDocs"
)


def recent_doc_name(data) -> str:
    """A RecentDocs value begins with a null-terminated UTF-16LE display name,
    followed by a shell item ID list (PIDL) that is not needed here."""
    if not isinstance(data, (bytes, bytearray)):
        return ""
    end = 0
    while end + 1 < len(data):
        if data[end] == 0 and data[end + 1] == 0:
            break
        end += 2
    return data[:end].decode("utf-16-le", errors="replace")


def mru_list_order(key: RegKey) -> dict:
    """MRUListEx is a sequence of little-endian uint32 value ids in
    most-recent-first order, terminated by 0xFFFFFFFF. Map each id to its
    position (0 = most recently opened)."""
    order: dict = {}
    for key_val in key.values():
        if key_val.name() != "MRUListEx":
            continue
        data = key_val.data()
        if isinstance(data, (bytes, bytearray)):
            position = 0
            for i in range(0, len(data) - 3, 4):
                entry = int.from_bytes(data[i : i + 4], "little")
                if entry == 0xFFFFFFFF:
                    break
                order[str(entry)] = position
                position += 1
        break
    return order


def subkey_extension(key: RegKey) -> str:
    return key.path.rstrip("\\").rsplit("\\", 1)[-1]


class RegRecentDocs(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegRecentDocs",
            "Get recently opened files and folders (RecentDocs) from the NTUser hive",
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
            reg = Registry.load(input_file, "\\HKCU")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            try:
                for key in reg.glob_keys(RECENT_DOCS_KEY):
                    # the root key lists recently opened items of every type
                    self.parse_key(key, "", output, report)
                    # each subkey groups recent items by file extension (or "Folder")
                    for subkey in key.sub_keys():
                        self.parse_key(subkey, subkey_extension(subkey), output, report)
            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_key(self, key: RegKey, extension: str, output: Output, report: RunReport):
        try:
            order = mru_list_order(key)
            for key_val in key.values():
                name = key_val.name()
                if name == "MRUListEx":
                    continue
                record = Record()
                record.add("target", value(recent_doc_name(key_val.data())))
                record.add("extension", value(extension))
                record.add("index", value(name))
                record.add("mru_position", value(order.get(name)))
                record.add("key_path", value(key.path))
                record.add("key_modif_time", value(key.mtime))
                record.add(
                    "key_security",
                    Value.Object(key.security_descriptor.to_record()),
                )
                output.write(record)

        except Exception as e:
            report.add_error(f"{e}")
