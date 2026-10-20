# SRUM Python migration

The user approved moving SRUM parsing to the Windows plugin, on branches other
than main, in this order: port, establish output parity, test recent Windows 11
data when available, then retire the common parser and dependency.

Keep `Srum.parse(input_file, plugin_file, run_config, metadata) -> RunReport`, all
14 provider names, configuration mappings, output formats, metadata, hashes and
timeline behavior. Use the already pinned `libesedb-python==20260704`; keep the
shared Rust runtime for configuration, typed values, field mapping and output.
Load the ID map once and stream records. Preserve existing conversions, including
timestamp precision and binary encoding; unrelated decoding corrections are
outside this compatibility migration. Missing provider tables are normal; errors
in present tables must be reported while retaining finalized partial output.

Capture canonical full-output SHA-256 digests and row counts from the original
Rust parser before changing it, for JSONL and CSV with/without timelines and
include-empty settings. Compare all providers using the existing database and
record the source commits and fixture hashes. Tests must run after the old
`dfir_ogre_common.parse_srum` export is removed.

Look for an actual public Windows 11 24H2-or-later SRUDB, retaining provenance and
distinguishing source OS evidence from ESE format revision. Use the existing
24H2 BITS sample as an ESE compatibility check, never as proof of SRUM decoding.
Benchmark against the original parser on available data and report dataset limits.

The only in-workspace production caller of common's SRUM API is the Windows
plugin. Move the callable to `dfir_ogre_plugin_windows.srum.parse_srum` with the
same arguments. Document this API removal and coordinated upgrade requirement;
do not create a reverse common-to-plugin dependency. After parity is established,
remove Rust SRUM code, bindings, stub and Cargo dependency. Preserve the plugin's
existing command interface. Leave both branches unmerged and never push.
