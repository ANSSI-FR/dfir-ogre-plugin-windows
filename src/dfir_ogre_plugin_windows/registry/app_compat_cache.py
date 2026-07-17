import logging
from collections.abc import Iterator

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
from dfir_ogre_plugin_windows.registry.app_compat_cache_formats import (
    AppCompatCacheEntry,
    AppCompatCacheParseError,
    parse_appcompat_cache,
)

logger = logging.getLogger(__name__)

CACHE_KEY_PATTERNS = (
    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager\\AppCompatibility",
    "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\Session Manager\\AppCompatCache",
)


class RegAppCompatCache(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegAppCompatCache",
            "Get the Application Compatibility cache from System hive",
        )

    @staticmethod
    def add_diagnostic(report: RunReport, location: str, reason: str) -> None:
        message = f"AppCompatCache {location}: {reason}"
        logger.warning("%s", message)
        report.add_error(message)

    def cache_keys(self, reg: Registry, report: RunReport) -> Iterator[RegKey]:
        for pattern in CACHE_KEY_PATTERNS:
            try:
                yield from reg.glob_keys(pattern)
            except Exception as exception:
                self.add_diagnostic(report, pattern, str(exception))

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
            reg = Registry.load(input_file, "\\HKLM\\SYSTEM")
        except Exception as exception:
            report.add_error(f"{exception}")
            return report

        with Output(run_config, plugin_config, metadata) as output:
            for key in self.cache_keys(reg, report):
                self.parse_key(key, output, report)
            report.add_output_report(output.get_report())

        return report

    def write_entry(
        self,
        parsed_entry: AppCompatCacheEntry,
        index: int,
        key: RegKey,
        key_security: Value,
        output: Output,
    ) -> None:
        record = Record()
        record.add("index", value(index))
        record.add("path", value(parsed_entry.path))
        record.add("modification_date", value(parsed_entry.modification_date))
        if parsed_entry.flag1 is not None:
            record.add("flag1", value(parsed_entry.flag1))
        if parsed_entry.flag2 is not None:
            record.add("flag2", value(parsed_entry.flag2))
        record.add("key_path", value(key.path))
        record.add("key_modif_time", value(key.mtime))
        record.add("key_security", key_security)
        output.write(record)

    def parse_key(self, key: RegKey, output: Output, report: RunReport) -> None:
        try:
            cache_value = key.value("AppCompatCache")
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        if cache_value is None:
            self.add_diagnostic(report, key.path, "missing AppCompatCache value")
            return

        try:
            cache = cache_value.data()
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        if not isinstance(cache, bytes):
            self.add_diagnostic(report, key.path, "AppCompatCache value is not bytes")
            return

        try:
            result = parse_appcompat_cache(cache)
        except AppCompatCacheParseError as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return
        except Exception as exception:
            self.add_diagnostic(report, key.path, f"unexpected parser failure: {exception}")
            return

        for diagnostic in result.diagnostics:
            self.add_diagnostic(report, key.path, diagnostic)

        try:
            key_security = Value.Object(key.security_descriptor.to_record())
        except Exception as exception:
            self.add_diagnostic(report, key.path, str(exception))
            return

        for index, parsed_entry in enumerate(result.entries):
            try:
                self.write_entry(
                    parsed_entry,
                    index,
                    key,
                    key_security,
                    output,
                )
            except Exception as exception:
                self.add_diagnostic(report, key.path, str(exception))
                break
