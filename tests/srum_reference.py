"""Repeatable full-output comparisons for the SRUM Rust-to-Python migration."""

import csv
import hashlib
import itertools
import json
from pathlib import Path

from dfir_ogre_common import (
    Metadata,
    OutputConfiguration,
    PluginConfiguration,
    RunConfiguration,
)


def output_cases():
    # Normalized output also checks the identifiers computed from typed values.
    for format, timeline, empty in itertools.product(
        ("jsonl", "csv", "normalized_jsonl"), (False, True), (False, True)
    ):
        yield (
            f"{format}-timeline{int(timeline)}-empty{int(empty)}",
            {
                "format": format,
                "with_timeline": timeline,
                "include_empty": empty,
            },
        )


def output_digest(path):
    """Compare complete records, ignoring the runtime's unordered timeline rows."""
    if path.suffix == ".csv":
        with path.open(newline="") as stream:
            rows = list(csv.reader(stream))
        header, records = (rows[0], rows[1:]) if rows else ([], [])
        content = [header, sorted(records)]
    else:
        # Sorting retains duplicates and every field, including normalized IDs.
        content = sorted(
            json.dumps(json.loads(line), sort_keys=True, ensure_ascii=True)
            for line in path.read_text().splitlines()
        )
    return hashlib.sha256(json.dumps(content, ensure_ascii=True).encode()).hexdigest()


def run_reference(parser, folder, options, database=None, configuration=None):
    """Run either callable with identical metadata and return every output digest."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise AssertionError("Reference output folder must be empty (writers append)")
    config = PluginConfiguration.load(configuration or "configuration/srum.xml")
    run_config = RunConfiguration(
        [OutputConfiguration("srum", str(folder), **options)], True
    )
    report = parser(
        str(database or "tests/data/srum/SRUDB.dat"),
        run_config,
        config,
        Metadata("test"),
    )
    if report.num_errors:
        raise AssertionError(report.last_error)
    files = {}
    for output_report in report.output_reports:
        if output_report.num_errors:
            raise AssertionError(output_report.last_error)
        for file_report in output_report.file_reports:
            path = Path(file_report.file_name)
            files[path.name] = {
                "rows": file_report.num_lines,
                "sha256": output_digest(path),
            }
    return files
