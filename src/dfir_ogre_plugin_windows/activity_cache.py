import logging
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
)

from dfir_ogre_plugin_windows.activity_cache_model import (
    ActivityCacheError,
    parse_activity_cache,
)
from dfir_ogre_plugin_windows.common import value


logger = logging.getLogger(__name__)


@contextmanager
def activity_cache_snapshot(input_file: str) -> Iterator[Path]:
    source = Path(input_file)
    with tempfile.TemporaryDirectory(
        prefix="dfir-ogre-activity-cache-",
    ) as temporary:
        snapshot = Path(temporary) / source.name
        shutil.copy2(source, snapshot)
        source_wal = Path(f"{source}-wal")
        if source_wal.is_file():
            shutil.copy2(source_wal, Path(f"{snapshot}-wal"))
        yield snapshot


def _quick_check(connection: sqlite3.Connection) -> None:
    results = tuple(
        str(row[0])
        for row in connection.execute("PRAGMA quick_check")
    )
    if results != ("ok",):
        raise ActivityCacheError(
            "SQLite quick_check failed: " + "; ".join(results)
        )


class ActivityCache(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "ActivityCache",
            "Parse Windows Activity Cache databases across schema versions",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        report = RunReport()
        try:
            plugin_config = PluginConfiguration.load(plugin_file)
        except Exception as exception:
            report.add_error(f"ActivityCache configuration: {exception}")
            return report

        try:
            with activity_cache_snapshot(input_file) as snapshot:
                connection = sqlite3.connect(snapshot)
                connection.row_factory = sqlite3.Row
                try:
                    connection.execute("PRAGMA query_only=ON")
                    _quick_check(connection)
                    parsed = parse_activity_cache(connection)
                finally:
                    connection.close()
        except (ActivityCacheError, OSError, sqlite3.Error) as exception:
            report.add_error(f"ActivityCache: {exception}")
            return report

        for warning in parsed.warnings:
            logger.warning("ActivityCache: %s", warning)
        for diagnostic in parsed.diagnostics:
            logger.warning("ActivityCache: %s", diagnostic)
            report.add_error(f"ActivityCache: {diagnostic}")

        try:
            with Output(
                run_config,
                plugin_config,
                metadata,
            ) as output:
                for parsed_record in parsed.records:
                    record = Record()
                    for name, parsed_value in parsed_record.values.items():
                        record.add(name, value(parsed_value))
                    output.write(record)
                report.add_output_report(output.get_report())
        except Exception as exception:
            report.add_error(f"ActivityCache output: {exception}")
        return report
