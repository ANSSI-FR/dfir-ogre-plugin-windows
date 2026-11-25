# DFIR-OGRE-PLUGIN-WINDOWS

[![badge_repo](https://img.shields.io/badge/ANSSI--FR-DFIR--Ogre-white)](https://github.com/ANSSI-FR/dfir-ogre)
[![category_badge_external](https://img.shields.io/badge/category-external-%23b556b6)](https://anssi-fr.github.io/README.en.html#project-categories)
[![openess_badge_A](https://img.shields.io/badge/code.gouv.fr-collaborative-blue)](https://anssi-fr.github.io/README.en.html#openness-level)

This project is part of the [DFIR-OGRE](https://github.com/ANSSI-FR/dfir-ogre) suite and provides an open source library of windows artefact parsers

Please refers to the ogre documentation for more details.

Run an individual parser with the main application's `dfir-ogre plugin` command:

```shell
dfir-ogre plugin --filename artifact --plugin_config configuration/prefetch.xml \
    --computer_name evidence-host --output_folder output
```

The standalone `dfir-ogre-plugin` command has been removed.

## Raw MFT

The `MFT` plugin reads a collected `$MFT` file using `ntfs-core`; no volume,
boot sector or journal is needed. Install the matching `dfir-ogre-common`
branch/version that provides `parse_mft` together with this plugin.

```shell
dfir-ogre plugin --filename '$MFT' --plugin_config configuration/mft.xml \
    --computer_name evidence-host --output_folder output
```

Fields shared with `NTFSInfo` use the same names, output types and qualifiers.
Binary file references retain the full 48-bit record and 16-bit sequence parts;
attributes use the shared Windows flag-name table. `file_attributes_ea` and
`file_attributes_recall_on_open` expose the same `0x40000` bit: their intended
meaning cannot be distinguished in a raw MFT. `file_attribute_raw` retains the
complete hexadecimal bitmask, including unknown bits. The directory boolean
comes from the record header.

One row is emitted per long name/hard link, with unambiguous DOS aliases in
`short_name`. Unknown stream sizes remain absent; a verified empty stream has
size zero.
Parent resolution checks sequences and places unresolved chains under
`\$OrphanFiles`. Extension attributes are matched through their full base
reference and allocation state. Resident `$ATTRIBUTE_LIST` references are
checked against the referenced record, sequence, attribute id and stream name;
for nonresident lists, only the collected extension records are available.
Stream sizes come from resident data or the VCN-0 fragment. Deleted
records are included, but reconstructed paths are not historical certainty.
Hashes, PE metadata, volume identifiers and stream contents are unavailable.
Malformed records are reported while subsequent valid records are retained.

The small test fixture and its provenance are in [tests/data/mft](tests/data/mft/README.md).

## SRUM parser migration

The `Srum` plugin now parses ESE databases with `libesedb-python`, sharing the
engine used by the other Windows ESE plugins. Its command, XML mappings, output
fields and timeline behavior are unchanged. Install this Windows plugin version
before or together with the common version that removes its Rust SRUM parser.

Direct callers of `dfir_ogre_common.parse_srum` should use:

```python
from dfir_ogre_plugin_windows.srum import parse_srum

report = parse_srum(input_file, run_config, plugin_config, metadata)
```

The arguments and result are unchanged. Full-output comparisons against the
original Rust parser cover two databases and 24 output configurations; see
[SRUM validation and fixture provenance](tests/data/srum/README.md), including
recent Windows coverage and performance limitations.

## ⚠️ Beta Status
This software is currently in **beta**. While functional and actively developed, it may still undergo breaking changes, and some artefact parsers may not yet be fully stabilized. We welcome feedback, bug reports, and contributions using the [issue tracker](https://github.com/ANSSI-FR/dfir-ogre/issues).

## French Cybersecurity Agency (ANSSI)

<img src="https://www.sgdsn.gouv.fr/files/styles/ds_image_paragraphe/public/files/Notre_Organisation/logo_anssi.png" alt="ANSSI logo" width="25%">

*This projet is managed by [ANSSI](https://cyber.gouv.fr/). To find out more, you can visit the [page](https://cyber.gouv.fr/enjeux-technologiques/open-source/) (in French) dedicated to ANSSI’s open-source strategy. You can also click on the badges above to learn more about their meaning.*
