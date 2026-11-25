"""Windows artifact parsers registered for the DFIR-OGRE application."""

from typing import List

from dfir_ogre_common import OgrePlugin, PluginDescription

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
from .mft import MFT as MFT
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
