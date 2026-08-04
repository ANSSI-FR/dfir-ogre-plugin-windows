# Forensic Mapping Descriptions Design

## Context

The 72 XML files under `configuration/` contain 85 mapping-level `description` elements. Their
current normalized lengths range from 20 to 930 characters. Some descriptions provide little more
than a parser label, while others repeat most of the field schema or use long Markdown lists.

Each mapping now also has a `short_description` capped at 120 characters. That field is intended
for catalog-wide discovery. The detailed `description` is loaded into the LLM context only after a
mapping has been selected, so it can carry more forensic meaning while remaining bounded.

## Goal

Rewrite every mapping-level description as compact forensic guidance that helps an LLM understand
what evidence the mapping exposes, how an investigator can use or correlate it, and which
limitations prevent overconfident conclusions.

## Scope

The rewrite covers the direct `description` child of all 85 `mapping` elements in every `.xml`
file recursively under `configuration/`, including the 14 mappings in `configuration/srum.xml`.

The change does not modify:

- `short_description` elements;
- timeline `description` elements;
- field-level `description` attributes;
- parser behavior, fields, queries, timelines, or output schemas; or
- XML fixtures under `tests/data/`.

## Description Structure

Each description uses one to three plain-text sentences and follows this evidence-first order:

1. Identify the artefact or collection source, its scope, and the activity represented by a row.
2. Name only the most important evidence and explain useful investigative correlations or
   hypotheses.
3. State a material caveat when applicable, such as ambiguous execution meaning, timestamp
   semantics, version-dependent behavior, collection-time state, retention, or incomplete source
   coverage.

A simple mapping may need only one or two sentences. A third sentence is included only when it
adds investigative value or prevents a likely misinterpretation.

## Content Rules

Every description:

- is non-empty and no longer than 600 characters after collapsing consecutive whitespace;
- uses plain prose without Markdown, bullet lists, embedded citations, or exhaustive field lists;
- mentions only the key fields needed to understand the evidence;
- explains forensic value rather than merely saying that the parser extracts data;
- uses cautious language such as `supports`, `can indicate`, `correlate`, or `is consistent with`
  when moving from an observation to an inference;
- never treats a single artefact as definitive proof when alternate explanations exist;
- describes only evidence emitted by the mapping and behavior supported by the implementation or
  an authoritative source;
- distinguishes mappings that share a data type but use different sources or formats; and
- keeps specialized or opaque data conservative instead of inventing semantics.

The 600-character limit includes spaces and punctuation in the normalized prose. XML indentation
and line wrapping do not count toward the limit.

## Research and Accuracy

The source hierarchy for each rewrite is:

1. the mapping's declared fields, detailed query or selector, and local parser implementation;
2. official format specifications or platform documentation, such as Microsoft Open
   Specifications;
3. the authoritative repository or documentation for the collection or parsing tool that produced
   the source data.

If those sources do not establish a forensic interpretation, the description stays limited to the
observable fields. Research links are not embedded in XML because they would consume context and
become stale; they are used only to validate wording.

## Examples

An execution-oriented artefact with a material caveat:

```xml
<description>Windows Prefetch records execution-optimization metadata for applications, including the executable name, run count, recent run times, referenced files, and volumes. Use it to support execution hypotheses, identify related files, and correlate activity across timelines. Absence is not proof that a program did not run, and timestamp availability varies by Windows version.</description>
```

An opaque mapping where interpretation must remain conservative:

```xml
<description>The SRUM energy-estimation table preserves timestamped, application- and user-associated binary records. Use its identifiers and times to correlate otherwise opaque entries with better-understood SRUM activity. This mapping does not decode the binary payload, so it cannot establish what energy metric the record represents.</description>
```

## Validation

`tests/test_configuration.py` gains a repository-wide invariant test for mapping descriptions. For
each configuration mapping, the test verifies that:

1. exactly one direct `description` exists;
2. its normalized text is non-empty; and
3. its normalized text contains no more than 600 characters.

Content validation also checks all 85 descriptions against their declared fields and verifies that
`short_description` values remain unchanged. All 72 XML files must parse, the existing mapping and
timeline invariants must pass, and the complete project test suite must remain green.

## Non-Goals

- Turning descriptions into incident conclusions or automated detection rules.
- Documenting every output field, because field-level descriptions already provide that detail.
- Adding citations, confidence scores, ATT&CK mappings, or investigation playbooks to the XML.
- Changing artefact extraction or normalizing unrelated XML formatting.
