import json
import os
from tempfile import TemporaryDirectory
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import Evtx

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "evtx")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class EvtxTest(TestCase):
    def test_real_fixture_preserves_event_values_and_timeline_context(self):
        # Raw EVTX record headers at 0x1200 and 0x16f60 contain IDs 1/123
        # and FILETIMEs 131061798135205626 / 131062090095218561.
        # First-record BinXML substitutions contain EventID 403, PID 4,
        # TID 8, SID S-1-5-18, and the device/driver values asserted below.
        with TemporaryDirectory() as output_folder:
            metadata = Metadata("collection-host")
            metadata.original_filename = (
                r"C:\Windows\System32\winevt\Logs\Kernel-PnP.evtx"
            )
            report = Evtx().parse(
                os.path.join(DATA_FOLDER, "evtx", "kernel_pnp.evtx"),
                os.path.join(CONF_FOLDER, "evtx.xml"),
                RunConfiguration([
                    OutputConfiguration("semantic", output_folder, with_timeline=True)
                ]),
                metadata,
            )
            self.assertIsNone(report.last_error)
            with open(
                os.path.join(output_folder, "semantic.windows_events.jsonl"),
                encoding="utf-8",
            ) as fp:
                rows = [json.loads(line) for line in fp]

        # One timeline row per event: header timestamp and SystemTime have
        # the same value and must retain both meanings without duplication.
        self.assertEqual(len(rows), 123)
        events = {
            row["data"]["system"]["event_record_id"]: row for row in rows
        }
        self.assertEqual(set(events), set(range(1, 124)))
        for row in rows:
            self.assertEqual(row["data_type"], "windows_events")
            self.assertEqual(row["metadata"]["computer"], "collection-host")
            self.assertEqual(
                row["metadata"]["original_filename"], metadata.original_filename
            )
            self.assertEqual(row["related_user"], "S-1-5-18")
            self.assertEqual(row["timestamp"], row["data"]["timestamp"])
            self.assertEqual(
                row["timestamp"],
                row["data"]["system"]["time_created"]["system_time"],
            )
            self.assertEqual(
                set(row["timestamp_meaning"].split(" - ")),
                {"Event generation time", "system_time"},
            )

        first = events[1]
        self.assertEqual(first["timestamp"], "2016-04-26T21:30:13.520562+00:00")
        self.assertEqual(first["description"], "Microsoft-Windows-Kernel-PnP:403")
        self.assertEqual(
            first["additional_description"],
            r"device_instance_id: ROOT\ACPI_HAL\0000 - driver_name: hal.inf",
        )
        system = first["data"]["system"]
        self.assertEqual(system["computer"], "MINWINPC")
        self.assertEqual(system["event_id"], 403)
        self.assertIs(type(system["event_id"]), int)
        self.assertEqual(system["execution"], {"process_id": 4, "thread_id": 8})
        self.assertIs(type(system["execution"]["process_id"]), int)
        self.assertEqual(
            system["provider"]["guid"], "9c205a39-1250-487d-abd7-e831c6290539"
        )
        data = first["data"]["event_data"]
        self.assertEqual(data["class_guid"], "4d36e966-e325-11ce-bfc1-08002be10318")
        self.assertIs(data["driver_inbox"], True)
        self.assertIs(data["device_updated"], False)
        self.assertEqual(data["driver_version"], "10.0.10586.0")
        self.assertEqual(data["status"], "0x0")
        last = events[123]
        self.assertEqual(last["timestamp"], "2016-04-27T05:36:49.521856+00:00")
        self.assertEqual(last["data"]["system"]["computer"], "WIN-PRH3EMBS8GI")
        # An embedded identifier remains evidence text, including case/braces.
        self.assertEqual(
            last["data"]["event_data"]["device_instance_id"],
            r"SWD\PRINTENUM\{225F3EF5-7B9A-4BFA-879A-B9E126C19891}",
        )

    # python -m unittest tests.test_evtx.EvtxTest.test_evtx -v
    def test_evtx(self):
        plugin_file = os.path.join(CONF_FOLDER, "evtx.xml")

        input_file = os.path.join(DATA_FOLDER, "evtx", "kernel_pnp.evtx")
        base_output_name = "kernel_pnp"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".windows_events.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
                    include_empty=True,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Evtx()
        self.assertEqual("Evtx", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, 123)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    data = jsoned["data"]
                    self.assertEqual(
                        data["system"]["provider"]["guid"],
                        "9c205a39-1250-487d-abd7-e831c6290539",
                    )
                    self.assertEqual(
                        data["event_data"]["class_guid"],
                        "4d36e966-e325-11ce-bfc1-08002be10318",
                    )
                    self.assertEqual(
                        data["event_data"]["device_instance_id"],
                        r"ROOT\ACPI_HAL\0000",
                    )
                if i == 3:
                    self.assertEqual(
                        jsoned["data"]["system"]["security"]["user_id"],
                        "S-1-5-18",
                    )

                i += 1
            self.assertEqual(i, 123)
