import logging
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

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

SQLITE_HEADER = b"SQLite format 3\x00"
WAL_HEADER_SIZE = 32
WAL_MAGIC_LITTLE_ENDIAN_CHECKSUM = 0x377F0682
WAL_MAGIC_BIG_ENDIAN_CHECKSUM = 0x377F0683
WAL_FORMAT_VERSION = 3007000


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


def _wal_checksum(
    data: bytes,
    byteorder: Literal["little", "big"],
) -> tuple[int, int]:
    if len(data) % 8:
        raise ActivityCacheError(
            "malformed SQLite WAL: checksum input is not 8-byte aligned"
        )
    first = 0
    second = 0
    for offset in range(0, len(data), 8):
        word1 = int.from_bytes(data[offset : offset + 4], byteorder)
        word2 = int.from_bytes(data[offset + 4 : offset + 8], byteorder)
        first = (first + word1 + second) & 0xFFFFFFFF
        second = (second + word2 + first) & 0xFFFFFFFF
    return first, second


def _sqlite_page_size(database: Path) -> tuple[int, int, int]:
    with database.open("rb") as file_object:
        header = file_object.read(20)
    if len(header) != 20 or header[:16] != SQLITE_HEADER:
        raise ActivityCacheError(
            "incompatible SQLite WAL: invalid database header"
        )
    encoded_page_size = int.from_bytes(header[16:18], "big")
    page_size = 65536 if encoded_page_size == 1 else encoded_page_size
    return page_size, header[18], header[19]


def _validate_wal(database: Path) -> None:
    """Validate copied WAL compatibility before SQLite opens it."""
    wal = Path(f"{database}-wal")
    if not wal.is_file() or wal.stat().st_size == 0:
        return

    wal_size = wal.stat().st_size
    if wal_size < WAL_HEADER_SIZE:
        raise ActivityCacheError(
            "malformed SQLite WAL: file is shorter than its 32-byte header"
        )

    database_page_size, write_version, read_version = _sqlite_page_size(
        database
    )
    if (write_version, read_version) != (2, 2):
        raise ActivityCacheError(
            "incompatible SQLite WAL: database is not in WAL mode"
        )

    with wal.open("rb") as file_object:
        header = file_object.read(WAL_HEADER_SIZE)
        magic = int.from_bytes(header[0:4], "big")
        if magic == WAL_MAGIC_LITTLE_ENDIAN_CHECKSUM:
            checksum_byteorder = "little"
        elif magic == WAL_MAGIC_BIG_ENDIAN_CHECKSUM:
            checksum_byteorder = "big"
        else:
            raise ActivityCacheError(
                f"malformed SQLite WAL: invalid magic 0x{magic:08x}"
            )

        format_version = int.from_bytes(header[4:8], "big")
        if format_version != WAL_FORMAT_VERSION:
            raise ActivityCacheError(
                "incompatible SQLite WAL: "
                f"format version {format_version}, expected "
                f"{WAL_FORMAT_VERSION}"
            )

        wal_page_size = int.from_bytes(header[8:12], "big")
        if (
            wal_page_size < 512
            or wal_page_size > 65536
            or wal_page_size & (wal_page_size - 1)
        ):
            raise ActivityCacheError(
                f"malformed SQLite WAL: invalid page size {wal_page_size}"
            )
        if wal_page_size != database_page_size:
            raise ActivityCacheError(
                "incompatible SQLite WAL: page size "
                f"{wal_page_size} does not match database page size "
                f"{database_page_size}"
            )

        checksum = _wal_checksum(
            header[:24],
            checksum_byteorder,
        )
        stored_header_checksum = (
            int.from_bytes(header[24:28], "big"),
            int.from_bytes(header[28:32], "big"),
        )
        if checksum != stored_header_checksum:
            raise ActivityCacheError(
                "malformed SQLite WAL: invalid header checksum"
            )


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
                _validate_wal(snapshot)
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
