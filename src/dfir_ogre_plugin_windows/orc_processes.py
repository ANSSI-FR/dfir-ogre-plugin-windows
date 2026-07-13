from datetime import datetime
from datetime import timezone as tz
from typing import List

from dfir_ogre_common import (
    AbstractParser,
    FieldName,
    Metadata,
    OgrePlugin,
    PluginConfiguration,
    PluginDescription,
    Record,
    RunConfiguration,
    RunReport,
    Value,
    parse_csv,
)


LOG_BEFORE_FAIL = 1000


class OrcProcesses1(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "OrcProcesses1",
            "Parse processes from the orc file: processes1.csv",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        python_mapping = {
            "TerminationDate": DateParser1(),
            "CreationDate": DateParser1(),
        }
        plugin_conf = PluginConfiguration.load(plugin_file, python=python_mapping)
        return parse_csv(
            input_file,
            run_config,
            plugin_conf,
            metadata,
            LOG_BEFORE_FAIL,
        )


class DateParser1(AbstractParser):
    """
    The date format of the creation date of processes in Processes1.csv
    has a timezone that is not compliant with the python datetime format: <date>+timezone_minutes
    For example: 20240530162016.698092+120 -> UTC+02
    """

    def parse(self, input: str, output_name: str) -> Record:
        timezone = input.split("+")[-1]
        if "+" in input:
            timezone = input.split("+")[-1]
        else:
            timezone = input.split("-")[-1]
        timezone_hour = int(timezone) // 60
        timezone_minutes = int(timezone) % 60
        if timezone_hour < 10:
            timezone_hour_string = "0" + str(timezone_hour)
        else:
            timezone_hour_string = str(timezone_hour)
        if timezone_minutes < 10:
            timezone_minutes_string = "0" + str(timezone_minutes)
        else:
            timezone_minutes_string = str(timezone_minutes)

        # Recombine value
        if "+" in input:
            input = (
                "+".join(input.split("+")[0:-1])
                + "+"
                + timezone_hour_string
                + timezone_minutes_string
            )
        else:
            input = (
                "-".join(input.split("-")[0:-1])
                + "-"
                + timezone_hour_string
                + timezone_minutes_string
            )

        date = datetime.strptime(input, "%Y%m%d%H%M%S.%f%z").astimezone(tz.utc)
        record = Record()
        record.add(output_name, Value.Date(date))
        return record

    def output_fields_names(self) -> List[FieldName]:
        return []
