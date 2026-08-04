# Mapping Short Descriptions Design

## Context

The 72 XML files under `configuration/` define 85 forensic artefact mappings. Their existing
`description` elements are useful to a human reader but can be long enough to waste LLM context
when every available mapping is presented together.

## Goal

Give an LLM a compact, accurate hint about the evidence available from every mapping without
removing or changing the existing detailed descriptions.

## XML Structure

Every direct `mapping` child receives exactly one direct `short_description` child immediately
after its existing direct `description` child:

```xml
<mapping data_type="browser_history">
  <description>...</description>
  <short_description>Records Chrome URL visits, titles, timestamps, visit counts, and referrers.</short_description>
  <category>Browser Artefacts</category>
  ...
</mapping>
```

The element uses ordinary XML text rather than CDATA. Existing descriptions, fields, timelines,
queries, parser attributes, and element ordering otherwise remain unchanged.

`dfir-ogre-common` already stores unrecognized mapping-level elements in the mapping parameter
map. Consequently, `short_description` remains parser-compatible and is available as the
`short_description` parameter without a dependency or loader change.

## Content Rules

Each short description:

- is a single, non-empty plain-text sentence on one XML line;
- contains no Markdown or field-name inventory syntax;
- is no longer than 120 Unicode characters, including spaces and punctuation;
- identifies the artefact or source when useful;
- names the principal forensic evidence the mapping exposes;
- describes only fields or meaning supported by that mapping; and
- distinguishes mappings that share a file, especially the 14 SRUM table mappings.

The wording is tailored by mapping rather than mechanically truncated from the existing
description or generated as a keyword list. This keeps the hints concise while retaining their
forensic meaning.

## Scope

The change covers every `mapping` in every `.xml` file recursively under `configuration/`,
including top-level, `configuration/registry/`, and `configuration/amcache_file/` files. It does
not modify XML fixtures under `tests/data/` or descriptions attached to fields and timelines.

## Validation

`tests/test_configuration.py` gains a repository-wide invariant test. For each configuration
mapping, the test verifies that:

1. exactly one direct `short_description` element exists;
2. its text is already stripped and non-empty;
3. it contains no line breaks; and
4. its length is at most 120 characters.

The test is first run before the XML edits to confirm that the missing-field requirement fails.
After adding the descriptions, the focused configuration test and complete project test suite are
run. A final XML parse/count check confirms coverage of all 72 files and 85 mappings.

## Non-Goals

- Rewriting or shortening existing `description` elements.
- Adding a new first-class field to `dfir-ogre-common`.
- Changing parser output, timelines, or forensic extraction behavior.
- Adding summaries to test fixtures or files outside `configuration/`.
