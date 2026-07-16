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
            input.read(1)  # ignore the BOM prefix

            with Output(run_config, plugin_config, metadata) as output:
                record = Record()
                tables: Dict[str, ObjectBuilder] = {}
                loaded_module: List[Value] = []
                files: List[Value] = []
                current_file: Optional[Record] = None

                for line in input:
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
    type = key.split(".")[1]
    if type == "Name":
        builder.current_key = value
    else:
        if builder.current_key:
            builder.object.add(builder.current_key, Value.String(value))


class ObjectBuilder:
    current_key: str | None
    object: Record

    def __init__(self):
        self.current_key = None
        self.object = Record()
