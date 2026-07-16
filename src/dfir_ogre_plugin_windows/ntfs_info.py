from typing import List

from dfir_ogre_common import (
    AbstractParser,
    FieldName,
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
    parse_csv,
    win_frn_hex_parser,
    win_ntfs_flag_parser,
    win_signed_hash_parser,
)

from dfir_ogre_plugin_windows.common import GuidParser


LOG_BEFORE_FAIL = 1000


class NTFSInfo(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "NTFSInfo",
            "NTFSInfo parser.",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        rust_mapping = {
            "Attributes": win_ntfs_flag_parser(),
            "FRN": win_frn_hex_parser(""),
            "SignedHash": win_signed_hash_parser(),
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


class SignedHashParser(AbstractParser):
    """Cast the value of SignedHash field into the right hash"""

    md5 = FieldName("file_pe_md5")
    sha1 = FieldName("file_pe_sha1")
    sha256 = FieldName("file_pe_sha256")

    def parse(self, input: str, output_name: str) -> Record:
        record = Record()
        if not input:
            return record
        match len(input):
            case 32:
                record.add(self.md5.output_name(), Value.String(input))

            case 40:
                record.add(self.sha1.output_name(), Value.String(input))
            case 64:
                record.add(self.sha256.output_name(), Value.String(input))
        return record

    def output_fields_names(self) -> List[FieldName]:
        return [self.md5, self.sha1, self.sha256]
