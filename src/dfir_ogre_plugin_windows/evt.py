from typing import List
import pyevt

from datetime import datetime, timezone
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

from dfir_ogre_plugin_windows.common import value

class WinEvt(OgrePlugin):

    def description(self) -> PluginDescription:
        return PluginDescription(
            "WinEvt",
            "Parse Windows EventLog (EVT) files and emit one record per event.",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()

        with Output(run_config, plugin_config, metadata) as output:
            evt_file = None
            try:
                with open(input_file, "rb") as f:
                    evt_file = pyevt.file()

                    # evt_file.set_ascii_codepage("utf-8")
                    evt_file.open_file_object(f)

                    # Normal records
                    for record_index in range(evt_file.number_of_records):
                        try:
                            evt_record = evt_file.get_record(record_index)
                            event = _get_event_data(evt_record, recovered=False)
                            output.write(event)
                        except Exception as exc:  # Broad catch – we still want to continue.
                            report.add_error(
                                f"Failed to parse record {record_index}: {exc}"
                            )

                    # Recovered records (those that were partially overwritten)
                    for record_index in range(evt_file.number_of_recovered_records):
                        try:
                            evt_record = evt_file.get_recovered_record(record_index)
                            event = _get_event_data(evt_record, recovered=True)

                            output.write(event)
                        except Exception as exc:
                            report.add_error(
                                f"Failed to parse recovered record {record_index}: {exc}"
                            )
            except Exception as outer_exc:
                report.add_error(f"Could not process EVT file: {outer_exc}")

            finally:
                try:
                    if evt_file:
                        evt_file.close()
                except Exception:
                    pass

        report.add_output_report(output.get_report())
        return report



def _get_event_data(evt_record: pyevt.record, recovered=False) -> Record:
    """Extract the fields from a ``pyevt.record`` object."""
    rec = Record()

    # Record number – may raise OverflowError for malformed files.
    try:
        record_number = evt_record.identifier
    except OverflowError:
        record_number = None
    rec.add("record_number", value(record_number))

    # 32‑bit event identifier encodes several sub‑fields.
    try:
        identifier = evt_record.event_identifier
        event_identifier = identifier & 0xffff
        facility = (identifier >> 16) & 0x0fff
        severity = identifier >> 30
        message_identifier = identifier

        rec.add("event_id", value(event_identifier))
        rec.add("facility", value(facility))
        rec.add("severity", value(severity))
        rec.add("message_identifier", value(message_identifier))
    except OverflowError:
        rec.add("event_id", Value.Null())
        rec.add("facility", Value.Null())
        rec.add("severity", Value.Null())
        rec.add("message_identifier", Value.Null())


    rec.add("offset", value(evt_record.offset))
    rec.add("recovered", value(recovered))

    rec.add("event_type", value(evt_record.event_type))
    rec.add("event_category", value(evt_record.event_category))
    rec.add("provider_name", value(evt_record.source_name))

    rec.add("computer_name", value(evt_record.computer_name))
    rec.add("user_sid", value(evt_record.user_security_identifier))

    strings:List[Value] = []
    for val in evt_record.strings:
        strings.append(value(val))

    rec.add("event_data", Value.Array(strings))

    # Creation / written timestamps – both are optional in the source format.
    try:
        creation_ts = evt_record.get_creation_time_as_integer()
        date = datetime.fromtimestamp(creation_ts, tz=timezone.utc)

        rec.add("creation_time", value(date))
    except (OverflowError, AttributeError):
        rec.add("creation_time", Value.Null())

    try:
        written_ts = evt_record.get_written_time_as_integer()
        date = datetime.fromtimestamp(written_ts, tz=timezone.utc)
        rec.add("written_time", Value.Date(date))
    except (OverflowError, AttributeError):
        rec.add("written_time", Value.Null())

    return rec
