import csv
import os
import tempfile
from datetime import datetime
from datetime import timezone as tz
from typing import List, Optional, cast

from dateutil import parser as date_parser
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
)

LOG_BEFORE_FAIL = 1000


class Autoruns(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "Autoruns",
            "Parse CSV files produced by the Windows Autoruns utility.",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        python_mapping = {"Time": AutorunsDateParser()}
        plugin_config = PluginConfiguration.load(plugin_file, python=python_mapping)

        normalized_input = normalize_autoruns_csv(input_file)
        try:
            return parse_csv(
                normalized_input,
                run_config,
                plugin_config,
                metadata,
                LOG_BEFORE_FAIL,
            )
        finally:
            os.remove(normalized_input)


class AutorunsDateParser(AbstractParser):
    DATE_FORMATS = (
        "%Y%m%d-%H%M%S",
        "%d/%m/%Y %H:%M",
    )

    def parse(self, input: str, output_name: str) -> Record:
        record = Record()
        if not input:
            return record

        date = self.parse_date(input)
        if date is None:
            return record

        record.add(output_name, Value.Date(date))
        return record

    def output_fields_names(self) -> List[FieldName]:
        return []

    def parse_date(self, input: str) -> Optional[datetime]:
        # Prefer observed Autoruns formats before the permissive dateutil fallback.
        for date_format in self.DATE_FORMATS:
            try:
                return self.to_utc(datetime.strptime(input, date_format))
            except ValueError:
                continue

        try:
            return self.to_utc(cast(datetime, date_parser.parse(input, dayfirst=True)))
        except (OverflowError, ValueError):
            return None

    def to_utc(self, date: datetime) -> datetime:
        if date.tzinfo is None:
            return date.replace(tzinfo=tz.utc)
        return date.astimezone(tz.utc)


def normalize_autoruns_csv(input_file: str) -> str:
    with open(
        input_file,
        encoding=detect_autoruns_csv_encoding(input_file),
        newline="",
    ) as csv_file:
        rows = list(csv.reader(csv_file))

    output = tempfile.NamedTemporaryFile(
        delete=False,
        mode="w",
        encoding="utf-16le",
        newline="",
        suffix=".csv",
    )
    with output:
        if not rows:
            return output.name

        writer = csv.writer(output)
        header = rows[0]
        header_len = len(header)
        writer.writerow(header)

        for row in rows[1:]:
            if len(row) < header_len:
                row = row + [""] * (header_len - len(row))
            elif len(row) > header_len:
                row = row[:header_len]
            writer.writerow(row)

    return output.name


def detect_autoruns_csv_encoding(input_file: str) -> str:
    with open(input_file, "rb") as fp:
        bom = fp.read(2)

    if bom in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"

    return "utf-16le"
