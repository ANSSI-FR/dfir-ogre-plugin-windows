import argparse
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OgrePlugin,
    OgreBatchedPlugin,
    OutputConfiguration,
    PluginDescription,
    RunConfiguration,
)
from tabulate import tabulate

from .activity_cache import ActivityCache as ActivityCache
from .autoruns import Autoruns as Autoruns
from .chrome_extension import ChromeExtension as ChromeExtension
from .csv import Csv as Csv
from .evt import WinEvt as WinEvt
from .evtx import Evtx as Evtx
from .fastfind import FastFind as FastFind
from .ie_webcache import IeWebCache as IeWebCache
from .firefox_extension import FirefoxExtension as FirefoxExtension
from .get_this import GetThis as GetThis
from .hive import HiveKeys as HiveKeys
from .i30_info import I30Info as I30Info
from .java_idx import JavaIdx as JavaIdx
from .json import Json as Json
from .jsonl import Jsonl as Jsonl
from .list_dll import ListDll as ListDll
from .lnk import Lnk as Lnk
from .lnk import LnkBatched as LnkBatched
from .merge import MergeLine as MergeLine
from .ntfs_info import NTFSInfo as NTFSInfo
from .orc_processes import OrcProcesses1 as OrcProcesses1
from .prefetch import Prefetch as Prefetch
from .recycle_bin import RecycleBin as RecycleBin
from .regexp import RegExp as RegExp
from .registry.acmru import RegAcMru as RegAcMru
from .registry.amcache_driver import RegAmCacheDriver as RegAmCacheDriver
from .registry.amcache_files import RegAmCacheFile as RegAmCacheFile
from .registry.amcache_program import RegAmCacheProgram as RegAmCacheProgram
from .registry.antifishing_file import RegAntifishingFile as RegAntifishingFile
from .registry.app_compat_cache import RegAppCompatCache as RegAppCompatCache
from .registry.autoruns_hive import RegAutorunsSystem as RegAutorunsSystem
from .registry.autoruns_hive import RegAutorunsSoftware as RegAutorunsSoftware
from .registry.autoruns_hive import RegAutorunsUser as RegAutorunsUser
from .registry.bamdam import RegBamDam as RegBamDam
from .registry.certificates import RegSystemCertificates as RegSystemCertificates
from .registry.certificates import RegUserCertificates as RegUserCertificates
from .registry.clsid import RegClsIdIUser as RegClsIdIUser
from .registry.clsid import RegClsIdSoftware as RegClsIdSoftware
from .registry.mass_storage import RegMassStorageSystem as RegMassStorageSystem
from .registry.mui_cache import RegMuiCache as RegMuiCache
from .registry.network_configuration import RegNetworkConfig as RegNetworkConfig
from .registry.pending_file_rename import RegPendingRename as RegPendingRename
from .registry.recent_app import RegRecentApp as RegRecentApp
from .registry.recent_docs import RegRecentDocs as RegRecentDocs
from .registry.run_mru import RegRunMru as RegRunMru
from .registry.scheduled_task import RegScheduledTask as RegScheduledTask
from .registry.services import RegServicesControlSet as RegServicesControlSet
from .registry.shellbag import RegShellBag as RegShellBag
from .registry.shim_database import RegShimDb as RegShimDb
from .registry.snapshot_exclude import RegSnapExclude as RegSnapExclude
from .registry.subject_interface_package import RegSIPP as RegSIPP
from .registry.system_info import RegSystemInfo as RegSystemInfo
from .registry.user_assist import RegUserAssist as RegUserAssist
from .registry.user_profile import RegUserProfile as RegUserProfile
from .registry.explorer_search_history import (
    RegExplorerSearchHistory as RegExplorerSearchHistory,
)
from .tcp_connection import TCPConn as TCPConn
from .sqlite import SQLite as SQLite
from .srum import Srum as Srum
from .usn_info import USNInfo as USNInfo
from .wer import Wer as Wer
from .xml import XML as XML

logger = logging.getLogger(__name__)


def main() -> None:
    # init_logger()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # disable WARNING level from evtx(to much noisen and a case of infinite loop creating too much logs)
    logging.getLogger("evtx").setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(
        prog="Ogre plugin",
        description="Run plugins",
    )

    sub_parser = parser.add_subparsers()
    list_parser = sub_parser.add_parser("list", help="list available plugins")
    list_parser.set_defaults(func=display_list)

    run = sub_parser.add_parser("run", help="parse file using a plugin")
    run.add_argument("-f", "--filename", required=True, help="input file path")
    run.add_argument(
        "-p",
        "--plugin_config",
        required=True,
        help="XML plugin configuration file path",
    )
    run.add_argument("-o", "--output_folder", required=True, help="output folder")
    run.add_argument("-t", "--timeline", action="store_true", help="add timeline data")
    run.add_argument(
        "-i", "--include_empty", action="store_true", help="include empty fields"
    )
    run.set_defaults(func=run_plugin)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


def run_plugin(
    args,
):
    output_name = Path(args.filename).stem

    rust_output = OutputConfiguration(
        base_file_name=output_name,
        output_folder=args.output_folder,
        output_type="file",
        format="jsonl",
        date_format="iso",
        with_timeline=args.timeline,
        include_empty=args.include_empty,
        params={},
    )

    plugin_file = args.plugin_config

    # create element tree object
    tree = ET.parse(plugin_file)
    root = tree.getroot()
    plugin = root.attrib.get("parser")
    is_batch = root.attrib.get("batch", None)

    addition_conf = {}

    runconfig = RunConfiguration([rust_output], False, addition_conf)

    found = False
    # process batched plugins
    if is_batch:
        for parser in OgreBatchedPlugin.__subclasses__():
            parser_obj = parser()
            parser_descr = parser_obj.description()
            if parser_descr.get_command() == plugin:
                found = True
                try:
                    logger.info(f"Running '{plugin}', on file '{args.filename}' ")

                    result = parser_obj.parse(
                        [ BatchEntry(args.filename,runconfig, Metadata("test") )], plugin_file,
                    )

                    if result.last_error:
                        logger.error(
                            f"file: '{args.filename}' with parser: '{plugin}' error: {result.last_error}"
                        )
                except Exception as e:
                    logger.error(
                        f"file: '{args.filename}' with parser: '{plugin}' error: {e}"
                    )


    # process batched plugins
    else:
        for parser in OgrePlugin.__subclasses__():
            parser_obj = parser()
            parser_descr = parser_obj.description()
            if parser_descr.get_command() == plugin:
                found = True
                try:
                    logger.info(f"Running '{plugin}', on file '{args.filename}' ")

                    result = parser_obj.parse(
                        args.filename, plugin_file, runconfig, Metadata("test")
                    )

                    if result.last_error:
                        logger.error(
                            f"file: '{args.filename}' with parser: '{plugin}' error: {result.last_error}"
                        )
                except Exception as e:
                    logger.error(
                        f"file: '{args.filename}' with parser: '{plugin}' error: {e}"
                    )

    if not found:
        logger.error(f"Unknown plugin '{plugin}'")


def list_parsers() -> List[PluginDescription]:
    parser_dict = {}
    descriptions = []
    for parser in OgrePlugin.__subclasses__():
        module_name = parser.__module__
        parser_descr = parser().description()
        entry_module = parser_dict.get(parser_descr.get_command())
        if entry_module:
            raise KeyError(
                f"Parser: '{parser_descr.get_command()}' for class: {parser.__class__} module: {module_name} is already defined in module: {entry_module}"
            )
        else:
            parser_dict[parser_descr.get_command()] = module_name
            descriptions.append(parser_descr)

    return descriptions


def display_list(args):
    unsorted = {}
    for c in list_parsers():
        unsorted[c.get_command()] = c.get_description()

    sorted_command = dict(sorted(unsorted.items()))
    print(
        tabulate(
            sorted_command.items(),
            headers=["Command", "Description"],
            tablefmt="simple_grid",
        )
    )
