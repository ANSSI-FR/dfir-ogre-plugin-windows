from typing import Dict, List, Optional

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import GuidParser


UTF16_LE_BOM = b"\xff\xfe"
UTF16_BE_BOM = b"\xfe\xff"
UTF8_BOM = b"\xef\xbb\xbf"

WER_MARKER_KEYS = frozenset(
    {
        "EventType",
        "ReportIdentifier",
        "IntegratorReportIdentifier",
        "AppSessionGuid",
    }
)
WER_MARKER_PREFIXES = (
    "Sig[",
    "DynamicSig[",
    "OsInfo[",
    "State[",
    "File[",
    "LoadedModule[",
)


class InvalidWerReportError(ValueError):
    """Raised when bytes cannot be decoded as a recognizable WER report."""


def _validate_wer_structure(text: str) -> None:
    has_version = False
    has_marker = False

    for line in text.splitlines():
        fields = line.split("=", 1)
        if len(fields) != 2:
            continue
        key, value = fields
        if key == "Version":
            version = value.strip()
            if not (version.isascii() and version.isdecimal()):
                raise InvalidWerReportError(
                    "Version must be an ASCII decimal integer"
                )
            has_version = True
        elif (
            key in WER_MARKER_KEYS
            or key.startswith(WER_MARKER_PREFIXES)
        ):
            has_marker = True

    if not has_version:
        raise InvalidWerReportError("missing Version field")
    if not has_marker:
        raise InvalidWerReportError("missing independent WER marker")


def _decode_wer_candidate(
    payload: bytes,
    encoding: str,
    label: str,
) -> str:
    try:
        text = payload.decode(encoding)
    except UnicodeDecodeError as exception:
        raise InvalidWerReportError(
            f"invalid {label} encoding"
        ) from exception
    _validate_wer_structure(text)
    return text


def decode_wer_report(payload: bytes) -> str:
    if payload.startswith(UTF16_LE_BOM):
        return _decode_wer_candidate(
            payload[len(UTF16_LE_BOM):],
            "utf-16-le",
            "UTF-16LE",
        )
    if payload.startswith(UTF8_BOM):
        return _decode_wer_candidate(
            payload[len(UTF8_BOM):],
            "utf-8",
            "UTF-8",
        )
    if payload.startswith(UTF16_BE_BOM):
        raise InvalidWerReportError("unsupported UTF-16BE encoding")

    candidates: Dict[str, str] = {}
    for encoding, label in (
        ("utf-16-le", "UTF-16LE"),
        ("utf-8", "UTF-8"),
    ):
        try:
            candidates[encoding] = _decode_wer_candidate(
                payload,
                encoding,
                label,
            )
        except InvalidWerReportError:
            continue

    if not candidates:
        raise InvalidWerReportError(
            "not a WER report in UTF-8 or UTF-16LE"
        )
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    if all(byte < 0x80 for byte in payload):
        return candidates["utf-8"]
    return candidates["utf-16-le"]


class Wer(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "WER",
            "A Windows Event Report (WER) parser",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        report = RunReport()
        plugin_config = PluginConfiguration.load(
            plugin_file,
            python={
                "AppSessionGuid": GuidParser.build("app_session_guid"),
                "IntegratorReportIdentifier": GuidParser.build(
                    "integrator_report_identifier"
                ),
                "ReportIdentifier": GuidParser.build("report_identifier"),
            },
        )
        config = plugin_config.data_type_configs[0]
        field_mapping = config.field_mapping
        if not field_mapping:
            report.add_error("invalid mapping configuration")
            return report

        # parse file
        with open(input_file, "r", encoding="utf-16-le") as input:
            with Output(run_config, plugin_config, metadata) as output:
                record = Record()
                tables: Dict[str, ObjectBuilder] = {}
                loaded_module: List[Value] = []
                files: List[Value] = []
                current_file: Optional[Record] = None

                for line_number, line in enumerate(input):
                    if line_number == 0:
                        line = line.removeprefix("\ufeff")
                    fields = line.split("=", 1)
                    if len(fields) != 2:
                        continue
                    key = fields[0]
                    value = fields[1].strip()

                    if key.startswith("Sig"):
                        build_object(tables, key, value, "Sig")
                    elif key.startswith("DynamicSig"):
                        build_object(tables, key, value, "DynamicSig")
                    elif key.startswith("OsInfo"):
                        build_object(tables, key, value, "OsInfo")
                    elif key.startswith("State"):
                        build_object(tables, key, value, "State")
                    elif key.startswith("File"):
                        key_type = key.split(".")[1]
                        if key_type == "CabName" and current_file:
                            files.append(Value.Object(current_file))
                            current_file = Record()
                        if not current_file:
                            current_file = Record()
                        current_file.add(key_type, Value.String(value))
                    elif key.startswith("LoadedModule"):
                        loaded_module.append(Value.String(value))
                    else:
                        parser = field_mapping.get_parser(key)
                        if parser:
                            parser.parse(value, record)

                if current_file:
                    files.append(Value.Object(current_file))

                # write every collected objects
                for key, value in tables.items():
                    record.add(key, Value.Object(value.object))

                record.add("loaded_module", Value.Array(loaded_module))
                record.add("files", Value.Array(files))

                output.write(record)

        report.add_output_report(output.get_report())
        return report


def build_object(tables: dict, key: str, value: str, pattern: str):
    builder: ObjectBuilder | None = tables.get(pattern, None)
    if not builder:
        builder = ObjectBuilder()
        tables[pattern] = builder

    key_type = key.rsplit(".", 1)[1]
    if key_type in ("Name", "Key"):
        builder.current_key = value
    elif key_type == "Value" and builder.current_key:
        builder.object.add(builder.current_key, Value.String(value))


class ObjectBuilder:
    current_key: str | None
    object: Record

    def __init__(self):
        self.current_key = None
        self.object = Record()
