import logging
from typing import Any, Dict, List

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

logger = logging.getLogger(__name__)


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
                        tuple.add("file_creation_date", Value.Date(metadata.creation_date))

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
        # Initialise the report to be returned
        report = RunReport()

        rust_mapping = {
            "droid_file_mft_seq": win_frn_int_parser("droid_file_"),
            "birth_droid_file_mft_seq": win_frn_int_parser("birth_droid_file_"),
        }
        plugin_config = PluginConfiguration.load(plugin_file, extension=rust_mapping)
        parser_tree = plugin_config.get_parsers()

        logger.info(f"processing {len(input_files)} Lnk file(s)")
        processed=1

        #parse each lnk
        for batch_entry in input_files:
            if processed % 1000 == 0:
                logger.info(f"{processed} Lnk processed")
            processed += 1

            metadata =  batch_entry.metadata
            input_file = batch_entry.file

            # Open the output
            with Output(batch_entry.run_config, plugin_config, batch_entry.metadata) as output:

                try:
                    # Load and parse the lnk
                    with open(input_file, "rb") as file:
                        jumplist = parse_jumplist(file)

                except Exception as e:
                    report.add_error(f"{e}")
                    continue

                # Early returns on parsing error
                status = jumplist.get("status", None)
                if status == "error":
                    error_message = jumplist.get("message", None)
                    if error_message:
                        report.add_error(error_message)
                        logger.error(error_message)
                        continue

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
                            tuple.add("file_creation_date", Value.Date(metadata.creation_date))

                        if metadata.modif_date:
                            tuple.add("file_modif_date", Value.Date(metadata.modif_date))

                        output.write(tuple)


            report.add_output_report(output.get_report())
        return report


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
