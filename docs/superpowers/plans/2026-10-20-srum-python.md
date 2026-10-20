# SRUM Python Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move SRUM into the Windows Python plugin while preserving Rust-parser outputs.

**Architecture:** Read ESE through existing pyesedb, resolve the ID map once and stream each provider through common's field mapping and output runtime. Establish a frozen Rust output baseline before retiring the Rust parser.

**Tech Stack:** Python >=3.10, libesedb-python==20260704, dfir-ogre-common Rust/PyO3 runtime, unittest, Cargo.

**Spec:** `docs/superpowers/specs/2026-10-20-srum-python-design.md`

## Global Constraints

- Both repositories use `migrate-srum-python`; never edit main, merge or push.
- Preserve command, all 14 provider names, XML mappings and output semantics.
- No new product dependencies; Python >=3.10.
- Python tests live in the Windows plugin; common runs its Rust tests.
- Preserve existing conversions; separate unrelated correctness changes.

## Review Focus

- Timestamp rounding, FILETIME remainders and raw DATE_TIME values must preserve output precision.
- Nulls, long/binary values and unresolved IDs must retain their old representation.
- Mapping aliases, unmapped columns and multiple mappings for one input must preserve names and types.
- Missing provider tables are normal; corrupt records and failed output finalization must remain visible.
- Removing common's public SRUM API requires documented caller migration without a reverse dependency.

### Task 1: Capture the Rust reference and implement the Python parser

**Files:** `tests/test_srum.py`, `tests/data/srum/rust-baseline.json`, `tests/data/srum/README.md`, `src/dfir_ogre_plugin_windows/srum.py`.

**Interfaces:** Consume original common `parse_srum`; produce plugin `parse_srum(input_file, run_config, plugin_config, metadata) -> RunReport` and unchanged `Srum.parse`.

- [ ] Capture original output digests/counts for every provider in JSONL/CSV, timeline on/off, empty fields on/off. Save provenance and raw output under temporary storage for detailed comparisons.
- [ ] Add tests for the frozen baseline and for using pyesedb independently of common's SRUM export. Run the new backend test and observe failure with the Rust wrapper.
- [ ] Implement the port using existing common mapping/output APIs. Test timestamp conversion, null/binary/long values, ID map strings/SIDs, aliases and errors with focused cases.
- [ ] Run `.venv/bin/python -m unittest tests.test_srum tests.test_esedb -v`; expect all tests passing with complete frozen-output equality.
- [ ] Commit the port and tests.

### Task 2: Validate newer data and performance

**Files:** `tests/test_srum.py`, `tests/data/srum/README.md`, optional new public fixture and provenance.

**Interfaces:** Consume plugin `Srum.parse` and frozen baseline; produce documented coverage and benchmark evidence.

- [ ] Assess researched public recent SRUM candidates; include an appropriate fixture with attribution if licensing and provenance permit, otherwise retain repeatable download instructions and state the limitation.
- [ ] For a suitable fixture add independent expected provider counts and representative decoded fields, and run the actual plugin end to end. Preserve the 24H2 BITS regression check.
- [ ] Benchmark original Rust and Python parsing on available databases with identical output settings, recording sizes, counts and repeated timings.
- [ ] Run `.venv/bin/python -m unittest tests.test_srum tests.test_esedb -v`; expect all tests passing. Commit new regression coverage and evidence.

### Task 3: Retire the common parser and validate both repositories

**Files:** common `src/parser/srum.rs`, `src/parser/mod.rs`, `src/lib.rs`, `src/lib_py.rs`, `dfir_ogre_common.pyi`, `Cargo.toml`, `Cargo.lock`, `README.md`; plugin migration notes.

**Interfaces:** Consume the standalone plugin parser; remove common `parse_srum`, retaining shared runtime APIs.

- [ ] Add a plugin regression asserting operation without common's old export, observe it fail against the old extension, then remove Rust SRUM code and dependency and regenerate the lockfile offline.
- [ ] Document `dfir_ogre_common.parse_srum` -> `dfir_ogre_plugin_windows.srum.parse_srum` with unchanged arguments and the coordinated upgrade requirement.
- [ ] Run common `cargo test --offline`, `cargo fmt --check`, `cargo clippy --offline --all-targets --all-features -- -D warnings`; expect all passing.
- [ ] Build/install the updated common extension into the plugin's existing environment; rerun SRUM parity tests and the plugin suite against it. Expect no common SRUM export or linked Rust ESE dependency.
- [ ] Review both full diffs with a fresh reviewer, fix substantive findings with regression tests, commit all changes and report branch names, parity evidence and sample/performance limits.
