#!/usr/bin/env python3
"""Opt-in real SRUM benchmark; run with the plugin's installed dependencies.

Uses this checkout's Python plugin and the interpreter's installed native runtime.
Each run starts a fresh process; filesystem caches are not flushed. Temporary
JSONL output is removed after each run. No performance pass/fail threshold is set.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def at_least(minimum):
    def parse(text):
        number = int(text)
        if number < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}")
        return number

    return parse


def peak_rss_bytes():
    # ru_maxrss is a process high-water mark, including native allocations.
    if sys.platform not in ("linux", "darwin"):
        return None
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def run_worker(database, configuration):
    sys.path.insert(0, str(ROOT / "src"))
    import dfir_ogre_common as common
    import pyesedb
    from dfir_ogre_plugin_windows import srum

    plugin_config = common.PluginConfiguration.load(str(configuration))
    with TemporaryDirectory(prefix="srum-benchmark-") as folder:
        run_config = common.RunConfiguration(
            [
                common.OutputConfiguration(
                    "srum",
                    folder,
                    format="jsonl",
                    with_timeline=False,
                    include_empty=True,
                )
            ],
            True,
        )
        metadata = common.Metadata("benchmark")
        srum._timestamp_value.cache_clear()
        started = time.perf_counter()
        report = srum.parse_srum(str(database), run_config, plugin_config, metadata)
        elapsed = time.perf_counter() - started
        for item in [report, *report.output_reports]:
            if item.num_errors:
                raise RuntimeError(f"SRUM parse failed: {item.last_error}")
        rows = sum(f.num_lines for o in report.output_reports for f in o.file_reports)

    # Count source provider records outside the parse/output timing.
    ese = pyesedb.file()
    ese.open(str(database))
    try:
        providers = 0
        for _, guid in srum.SRUM_TABLES:
            table = ese.get_table_by_name(guid)
            if table is not None:
                providers += table.get_number_of_records()
    finally:
        ese.close()
    if rows != providers:
        raise RuntimeError(
            f"SRUM output has {rows} rows for {providers} provider records"
        )
    return {
        "pid": os.getpid(),
        "provider_records": providers,
        "output_rows": rows,
        "parse_output_seconds": elapsed,
        "peak_rss_bytes": peak_rss_bytes(),
        "plugin_source": str(Path(srum.__file__).resolve()),
        "common_runtime": str(Path(common.__file__).resolve()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="real SRUDB.dat to benchmark")
    parser.add_argument(
        "--configuration", type=Path, default=ROOT / "configuration" / "srum.xml"
    )
    parser.add_argument("--repeats", type=at_least(1), default=3)
    parser.add_argument("--warmups", type=at_least(0), default=1)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("database", "configuration"):
        path = getattr(args, name).resolve()
        if not path.is_file():
            parser.error(f"{name} not a file: {path}")
        setattr(args, name, path)
    if args.worker:
        print(json.dumps(run_worker(args.database, args.configuration)))
        return

    runs = []
    for number in range(args.warmups + args.repeats):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(args.database),
                "--configuration",
                str(args.configuration),
                "--worker",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or f"worker exited {result.returncode}"
            )
        if number >= args.warmups:
            runs.append(json.loads(result.stdout))
    counts = {(run["provider_records"], run["output_rows"]) for run in runs}
    if len(counts) != 1:
        raise RuntimeError("SRUM record counts changed between measured runs")
    providers, rows = counts.pop()
    median = statistics.median(run["parse_output_seconds"] for run in runs)
    peaks = [run["peak_rss_bytes"] for run in runs if run["peak_rss_bytes"] is not None]
    print(
        json.dumps(
            {
                "database": str(args.database),
                "database_bytes": args.database.stat().st_size,
                "configuration": str(args.configuration),
                "output": {
                    "format": "jsonl",
                    "with_timeline": False,
                    "include_empty": True,
                },
                "repeats": args.repeats,
                "warmups": args.warmups,
                "provider_records": providers,
                "output_rows": rows,
                "parse_output_seconds_median": median,
                "rows_per_second": rows / median,
                "peak_rss_bytes": max(peaks) if peaks else None,
                "peak_rss_scope": "whole worker process high-water mark, including imports, "
                "configuration, source counting, Python and native ESE memory; "
                "maximum of measured runs; null if unsupported",
                "cache_policy": "fresh subprocess and cleared timestamp cache per run; "
                "filesystem caches are not flushed",
                "runs": runs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1)
