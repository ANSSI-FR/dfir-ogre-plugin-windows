# OCSF Name XML Metadata Design

## Context

The Windows plugin XML configuration files define DFIR-Ogre output field names, but those names are local to the plugin and are not normalized against OCSF. OCSF 1.8.0 provides an event and object schema with reusable attribute names. This change introduces a descriptive bridge from plugin output fields to OCSF paths.

## Goals

- Add an optional XML metadata attribute named `ocsf-name`.
- Store full dotted OCSF paths, such as `process.pid`, `actor.user.uid`, or `file.path`.
- Add mappings only when the OCSF target is high confidence.
- Keep the attribute descriptive for now, with no parser behavior change.

## Non-Goals

- Do not rename existing DFIR-Ogre output fields.
- Do not emit new runtime fields.
- Do not validate `ocsf-name` values in tests or CI.
- Do not fetch or vendor the OCSF schema.
- Do not attempt complete coverage of every XML field.

## XML Placement

`ocsf-name` belongs on the XML element that owns the DFIR-Ogre output name. This includes `<field>`, `<object>`, and `<multi_input>` elements when their semantic OCSF target is clear.

Example:

```xml
<field input="pid" parser="Int" ocsf-name="process.pid" />
```

For nested mappings, the value remains the full OCSF path rather than a relative path:

```xml
<object input="System" output="system" ocsf-name="metadata">
  <field
    input="EventID"
    output="event_id"
    parser="String"
    ocsf-name="metadata.event_code"
  />
</object>
```

If a field has no confident OCSF equivalent, omit `ocsf-name`. Absence means "not mapped yet".

## Mapping Strategy

Initial annotations should focus on fields with clear OCSF equivalents, such as:

- process identifiers and command details
- file paths, names, hashes, sizes, and timestamps
- URL and browser history fields
- user names and SIDs
- host or computer names
- event IDs, provider names, and event timestamps
- common creation, modification, access, and termination timestamps

Avoid speculative mappings for overloaded or artifact-specific fields, including generic names like `name`, `type`, `id`, and `description`, registry-specific fields, Windows event payload internals, counters, flags, or source-specific enum values unless the OCSF path is obvious from context.

## Architecture

The implementation is XML-only in this plugin repository. Existing parser code and `dfir-ogre-common` configuration structures continue to ignore this metadata until a later feature consumes it.

No new abstraction is required. Contributors can add `ocsf-name` next to existing `input`, `output`, `parser`, `display_name`, `qualifier`, and `description` attributes.

## Data Flow

Current data flow remains unchanged:

1. A plugin loads XML configuration.
2. The common configuration parser reads known runtime attributes.
3. Parsed artifact records are emitted with existing DFIR-Ogre output names.

`ocsf-name` does not participate in runtime parsing or output generation. It exists only in the source XML as documentation for future normalization work.

## Error Handling

Because `ocsf-name` is descriptive and not validated, malformed values will not fail parsing or tests in this pass. Review discipline is the only guardrail: add the attribute only when the mapping is high confidence.

A future runtime or validation feature can add strict handling after the expected consumer and schema source are defined.

## Testing

No new tests are added for `ocsf-name` in this design. Existing XML configuration tests should continue to pass because the attribute does not affect the existing test logic.

Manual verification for implementation should include:

- XML files remain well formed.
- Existing test suite still passes.
- No unrelated XML output names are changed.

## References

- OCSF schema browser: https://schema.ocsf.io/1.8.0/?extensions=
- OCSF schema repository: https://github.com/ocsf/ocsf-schema
- OCSF 1.8.0 dictionary: https://raw.githubusercontent.com/ocsf/ocsf-schema/v1.8.0/dictionary.json
