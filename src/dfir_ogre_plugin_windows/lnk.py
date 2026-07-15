import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from dfir_ogre_common import (
    BatchEntry,
    FieldParserTree,
    Metadata,
    OgrePlugin,
    OgreBatchedPlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
    win_frn_int_parser,
)
from jumplist_parser import parse_jumplist

from dfir_ogre_plugin_windows.system_timezone import (
    entry_snapshot,
    is_system_hive,
    resolve_system_timezone,
)

logger = logging.getLogger(__name__)


@dataclass
class LnkBatch:
    lnk_entries: List[BatchEntry]
    system_entries: List[BatchEntry]


class Lnk(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription("Lnk", "Windows Lnk parser")

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        # Initialise the report to be returned
        report = RunReport()

        rust_mapping = {
            "droid_file_mft_seq": win_frn_int_parser("droid_file_"),
            "birth_droid_file_mft_seq": win_frn_int_parser("birth_droid_file_"),
        }
        plugin_config = PluginConfiguration.load(plugin_file, extension=rust_mapping)
        parser_tree = plugin_config.get_parsers()

        try:
            # Load and parse the lnk
            with open(input_file, "rb") as file:
                jumplist = parse_jumplist(file)

        except Exception as e:
            report.add_error(f"{e}")
            return report

        fat_timestamp_count = normalize_lnk_fat_timestamps(jumplist, None)
        if fat_timestamp_count:
            report.add_error(
                "Unable to normalize LNK target DOS/FAT timestamps without a "
                "matching SYSTEM hive; use the LnkBatched plugin"
            )

        # Open the output
        with Output(run_config, plugin_config, metadata) as output:
            # Early returns on parsing error
            status = jumplist.get("status", None)
            if status == "error":
                error_message = jumplist.get("message", None)
                if error_message:
                    report.add_error(error_message)
                    logger.error(error_message)
                return report

            # Parse each lnk into a distinct tuple.
            # It relies on ogre metadata to provide information about the file it comes from.
            lnk_list = jumplist.get("lnk", [])
            for lnk in lnk_list:
                status = jumplist.get("status", "")

                # filter errors
                if status == "error":
                    error_message = jumplist.get("message", None)
                    if error_message:
                        report.add_error(error_message)
                        logger.error(error_message)
                else:
                    # recursively parse the lnk and write result to the output
                    tuple = parse_object(lnk, parser_tree)  # type: ignore

                    if metadata.creation_date:
                        tuple.add(
                            "file_creation_date", Value.Date(metadata.creation_date)
                        )

                    if metadata.modif_date:
                        tuple.add("file_modif_date", Value.Date(metadata.modif_date))

                    output.write(tuple)

            # feed the report
            report.add_output_report(output.get_report())

        return report


class LnkBatched(OgreBatchedPlugin):
    def description(self) -> PluginDescription:
        return PluginDescription("LnkBatched", "Windows Lnk Batch parser")

    def parse(
        self,
        input_files: List[BatchEntry],
        plugin_file: str,
    ) -> RunReport:
        report = RunReport()
        rust_mapping = {
            "droid_file_mft_seq": win_frn_int_parser("droid_file_"),
            "birth_droid_file_mft_seq": win_frn_int_parser("birth_droid_file_"),
        }
        plugin_config = PluginConfiguration.load(plugin_file, extension=rust_mapping)
        parser_tree = plugin_config.get_parsers()

        batches = group_lnk_inputs(input_files)
        lnk_count = sum(len(batch.lnk_entries) for batch in batches.values())
        logger.info(f"processing {lnk_count} Lnk file(s)")

        processed = 0
        for snapshot, batch in batches.items():
            if not batch.lnk_entries:
                continue

            timezone_info = resolve_system_timezone(
                batch.system_entries, snapshot, report
            )
            for batch_entry in batch.lnk_entries:
                processed += 1
                if processed % 1000 == 0:
                    logger.info(f"{processed} Lnk processed")

                self.parse_entry(
                    batch_entry,
                    plugin_config,
                    parser_tree,
                    timezone_info,
                    report,
                )

        return report

    def parse_entry(
        self,
        batch_entry: BatchEntry,
        plugin_config: PluginConfiguration,
        parser_tree: FieldParserTree,
        timezone_info: Optional[ZoneInfo],
        report: RunReport,
    ) -> None:
        metadata = batch_entry.metadata
        with Output(
            batch_entry.run_config, plugin_config, batch_entry.metadata
        ) as output:
            try:
                with open(batch_entry.file, "rb") as file:
                    jumplist = parse_jumplist(file)
            except Exception as e:
                report.add_error(f"{e}")
                report.add_output_report(output.get_report())
                return

            normalize_lnk_fat_timestamps(jumplist, timezone_info)

            status = jumplist.get("status", None)
            if status == "error":
                error_message = jumplist.get("message", None)
                if error_message:
                    report.add_error(error_message)
                    logger.error(error_message)
            else:
                for lnk in jumplist.get("lnk", []):
                    status = lnk.get("status", "")
                    if status == "error":
                        error_message = lnk.get("message", None)
                        if error_message:
                            report.add_error(error_message)
                            logger.error(error_message)
                        continue

                    tuple = parse_object(lnk, parser_tree)
                    if metadata.creation_date:
                        tuple.add(
                            "file_creation_date", Value.Date(metadata.creation_date)
                        )
                    if metadata.modif_date:
                        tuple.add("file_modif_date", Value.Date(metadata.modif_date))
                    output.write(tuple)

            report.add_output_report(output.get_report())


def group_lnk_inputs(
    input_files: List[BatchEntry],
) -> Dict[Optional[str], LnkBatch]:
    grouped: Dict[Optional[str], LnkBatch] = {}
    for entry in input_files:
        snapshot = entry_snapshot(entry)
        batch = grouped.setdefault(snapshot, LnkBatch([], []))
        if is_system_hive(entry):
            batch.system_entries.append(entry)
        else:
            batch.lnk_entries.append(entry)
    return grouped


def normalize_lnk_fat_timestamps(
    jumplist: Dict[str, Any], timezone_info: Optional[ZoneInfo]
) -> int:
    """Normalize DOS/FAT target-item wall times emitted by LnkParse3."""
    timestamp_count = 0
    for lnk in jumplist.get("lnk", []):
        if not isinstance(lnk, dict):
            continue
        target = lnk.get("target")
        if not isinstance(target, dict):
            continue
        items = target.get("items")
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict) or not item.get("modification_time"):
                continue
            timestamp_count += 1
            item["modification_time"] = lnk_fat_datetime_to_utc(
                item["modification_time"], timezone_info
            )

    return timestamp_count


def lnk_fat_datetime_to_utc(
    timestamp: object, timezone_info: Optional[ZoneInfo]
) -> Optional[str]:
    if timezone_info is None:
        return None

    try:
        parsed = (
            timestamp
            if isinstance(timestamp, datetime)
            else datetime.fromisoformat(str(timestamp))
        )
    except (TypeError, ValueError):
        return None

    # LnkParse3 labels this DOS/FAT local wall time as UTC. Discard that
    # incorrect label before applying the source machine's timezone.
    local_wall_time = parsed.replace(tzinfo=None, fold=0)
    return (
        local_wall_time.replace(tzinfo=timezone_info)
        .astimezone(timezone.utc)
        .isoformat()
    )


def parse_object(
    object_dict: Dict[str, Any],
    parser_tree: FieldParserTree,
) -> Record:
    """Recursively parse a dictionary structure into a Record using a parser tree.

    Args:
        object_dict: Dictionary containing the data to parse.
        parser_tree: FieldParserTree used to map the data to the structured output."""

    record = Record()

    # Early return if object is empty or not a dict
    if not object_dict or not isinstance(object_dict, dict):
        return record

    for key, item in object_dict.items():
        # Manage lists
        if isinstance(item, list):
            # The list contains 'normal' fields
            list_parser = parser_tree.get_parser(key)
            list_res: List[Value]
            if list_parser:
                list_res = []
                for lst_value in item:
                    value = list_parser.parse_into_value(str(lst_value))
                    if value:
                        list_res.append(value)

                list_parser.set_value(Value.Array(list_res), record)
            # The list contains objects
            else:
                sub_tree = parser_tree.get_parser_subtree(key)
                if sub_tree:
                    list_res = []
                    for lst_value in item:
                        value = parse_object(lst_value, sub_tree)
                        if value:
                            list_res.append(Value.Object(value))

                    record.add(sub_tree.get_output_name(), Value.Array(list_res))

        # Manage objects
        elif isinstance(item, dict):
            sub_tree = parser_tree.get_parser_subtree(key)
            if sub_tree:
                value = parse_object(item, sub_tree)
                if value:
                    record.add(sub_tree.get_output_name(), Value.Object(value))

        # Manage 'normal' fields
        else:
            list_parser = parser_tree.get_parser(key)
            if list_parser:
                if item:
                    list_parser.parse(str(item), record)
                else:
                    record.add(key, Value.Null())

    return record
