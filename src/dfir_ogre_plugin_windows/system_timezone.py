import os
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dfir_ogre_common import BatchEntry, Registry, RunReport

from dfir_ogre_plugin_windows.common import win_tz_to_iana


def entry_snapshot(entry: BatchEntry) -> Optional[str]:
    snapshot = entry.metadata.vss
    if snapshot is None:
        return None
    return str(snapshot).casefold()


def entry_source_basename(entry: BatchEntry) -> str:
    source = entry.metadata.original_filename or entry.file
    return os.path.basename(str(source).replace("\\", "/")).casefold()


def is_system_hive(entry: BatchEntry) -> bool:
    filename = entry_source_basename(entry)
    if filename.endswith(
        (".lnk", ".automaticdestinations-ms", ".customdestinations-ms")
    ):
        return False
    return (
        filename == "system"
        or filename.startswith("system.")
        or filename.startswith("system_")
    )


def resolve_system_timezone(
    system_entries: List[BatchEntry],
    snapshot: Optional[str],
    report: RunReport,
) -> Optional[ZoneInfo]:
    if not system_entries:
        report.add_error(f"No SYSTEM hive found for VSS snapshot {snapshot!r}")
        return None

    for entry in system_entries:
        try:
            registry = Registry.load(entry.file, "\\HKLM\\SYSTEM")
        except Exception as e:
            report.add_error(f"Unable to load SYSTEM hive {entry.file!r}: {e}")
            continue

        timezone_info = get_system_timezone(registry)
        if timezone_info is not None:
            return timezone_info

        report.add_error(
            f"Unable to resolve Windows timezone from SYSTEM hive {entry.file!r}"
        )

    return None


def get_system_timezone(registry: Registry) -> Optional[ZoneInfo]:
    current = registry_value_data(registry, "\\HKLM\\SYSTEM\\Select", "Current")
    try:
        control_set = f"ControlSet{int(current):03d}"
    except (TypeError, ValueError):
        control_set = "ControlSet001"

    timezone_path = f"\\HKLM\\SYSTEM\\{control_set}\\Control\\TimeZoneInformation"
    windows_name = registry_value_data(registry, timezone_path, "TimeZoneKeyName")
    if not windows_name:
        windows_name = registry_value_data(registry, timezone_path, "StandardName")
    if not isinstance(windows_name, str):
        return None

    windows_name = windows_name.rstrip("\x00")
    iana_name = win_tz_to_iana.get(windows_name)
    if iana_name is None:
        return None

    try:
        return ZoneInfo(iana_name)
    except ZoneInfoNotFoundError:
        return None


def registry_value_data(registry: Registry, path: str, name: str):
    keys = registry.glob_keys(path)
    if not keys:
        return None
    registry_value = keys[-1].value(name)
    if registry_value is None:
        return None
    return registry_value.data()
