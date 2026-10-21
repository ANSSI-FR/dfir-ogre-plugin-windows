"""Exercise the opt-in benchmark CLI without timing pass/fail thresholds."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmarks" / "benchmark_srum.py"
DATABASE = ROOT / "tests" / "data" / "srum" / "SRUDB.dat"


class SrumBenchmarkTest(TestCase):
    def run_benchmark(self, *arguments, cwd=None, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=30,
        )

    def test_missing_database_is_rejected(self):
        with TemporaryDirectory() as folder:
            result = self.run_benchmark(Path(folder, "missing.dat"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a file", result.stderr)

    def test_invalid_run_counts_are_rejected(self):
        for option, count in (("--repeats", "0"), ("--warmups", "-1")):
            with self.subTest(option=option):
                result = self.run_benchmark(DATABASE, option, count)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(option, result.stderr)
                self.assertIn("must be at least", result.stderr)

    def test_parser_errors_fail_the_benchmark(self):
        with TemporaryDirectory() as folder:
            invalid = Path(folder, "invalid.dat")
            invalid.write_bytes(b"not an ESE database")
            result = self.run_benchmark(invalid, "--repeats", "1", "--warmups", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SRUM parse failed", result.stderr)

    def test_fixture_reports_a_real_measured_run_from_another_directory(self):
        with TemporaryDirectory() as folder:
            result = self.run_benchmark(
                DATABASE,
                "--configuration",
                ROOT / "configuration" / "srum.xml",
                "--repeats",
                "1",
                "--warmups",
                "0",
                cwd=folder,
                env={**os.environ, "TMPDIR": folder, "TMP": folder, "TEMP": folder},
            )
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["database_bytes"], DATABASE.stat().st_size)
        self.assertEqual(report["provider_records"], 2355)
        self.assertEqual(report["output_rows"], 2355)
        self.assertEqual(len(report["runs"]), 1)
        self.assertGreater(report["parse_output_seconds_median"], 0)
        self.assertGreater(report["rows_per_second"], 0)
        self.assertIn("whole worker process", report["peak_rss_scope"])
        self.assertIn("native ESE", report["peak_rss_scope"])
        if sys.platform in ("linux", "darwin"):
            self.assertGreater(report["peak_rss_bytes"], 0)
