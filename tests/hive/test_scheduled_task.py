import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from unittest import TestCase
from zoneinfo import ZoneInfo

from dfir_ogre_common import (
    BatchEntry,
    Metadata,
    OgreBatchedPlugin,
    OutputConfiguration,
    RunConfiguration,
)

from dfir_ogre_plugin_windows import RegScheduledTask
from dfir_ogre_plugin_windows.registry import scheduled_task
from dfir_ogre_plugin_windows.registry.scheduled_task import decode_task_action

from . import CONF_FOLDER, DATA_FOLDER, TEMP_FOLDER

os.makedirs(TEMP_FOLDER, exist_ok=True)


def bstr(text: str) -> bytes:
    encoded = text.encode("utf-16-le")
    return len(encoded).to_bytes(4, byteorder="little") + encoded


class TestScheduledTask(TestCase):
    def test_security_descriptor_mappings_use_plural_ace_arrays(self):
        plugin_file = os.path.join(CONF_FOLDER, "scheduled_task.xml")
        root = ET.parse(plugin_file).getroot()
        fields = root.find("./mapping/fields")
        self.assertIsNotNone(fields)
        assert fields is not None

        self.assertEqual([], root.findall(".//object[@input='dacl_ace']"))
        self.assertEqual([], root.findall(".//object[@input='sacl_ace']"))

        def descriptor(name: str):
            element = fields.find(f"./object[@input='{name}']")
            self.assertIsNotNone(element, f"missing {name} mapping")
            assert element is not None
            return element

        def ace_mapping(element, name: str):
            ace = element.find(f"./array/object[@input='{name}']")
            self.assertIsNotNone(ace, f"missing {name} array mapping")
            assert ace is not None
            return ace

        def direct_fields(element):
            return {field.attrib["input"] for field in element.findall("./field")}

        def array_fields(element):
            return {
                field.attrib["input"] for field in element.findall("./array/field")
            }

        sddl = descriptor("security_descriptor")
        self.assertLessEqual(
            {"owner_sid", "group_sid", "dacl_flags", "sacl_flags"},
            direct_fields(sddl),
        )
        for acl_name in ("sacl_aces", "dacl_aces"):
            ace = ace_mapping(sddl, acl_name)
            self.assertLessEqual(
                {
                    "ace_type",
                    "object_guid",
                    "inherit_object_guid",
                    "account_sid",
                    "resource_attribute",
                },
                direct_fields(ace),
            )
            self.assertLessEqual({"ace_flags", "rights"}, array_fields(ace))

        key_security = descriptor("key_security")
        self.assertLessEqual(
            {"owner_sid", "group_sid"}, direct_fields(key_security)
        )
        self.assertIn("control_flags", array_fields(key_security))
        for acl_name in ("sacl_aces", "dacl_aces"):
            ace = ace_mapping(key_security, acl_name)
            self.assertLessEqual(
                {
                    "ace_type",
                    "account_sid",
                    "ace_size",
                    "object_type_guid",
                    "inherited_object_type_guid",
                    "raw_hex",
                },
                direct_fields(ace),
            )
            self.assertLessEqual({"ace_flags", "rights"}, array_fields(ace))

    def test_decode_com_handler_action(self):
        raw_class_id = bytes.fromhex("824779481f6ab947bd521d5f95d49c1b")
        action = b"\x77\x77" + bstr("handler") + raw_class_id + bstr("payload")

        decoded = json.loads(decode_task_action(action).to_string())

        self.assertEqual(decoded["action_id"], "handler")
        self.assertEqual(decoded["action_type"], "ComHandler")
        self.assertEqual(decoded["com_classid"], "48794782-6a1f-47b9-bd52-1d5f95d49c1b")
        self.assertEqual(decoded["com_data"], "payload")

    def test_decode_email_attachments(self):
        action = b"".join(
            (
                b"\x88\x88",
                bstr("email-action"),
                bstr("from@example.test"),
                bstr("to@example.test"),
                bstr("cc@example.test"),
                bstr("bcc@example.test"),
                bstr("reply@example.test"),
                bstr("smtp.example.test"),
                bstr("Forensic subject"),
                bstr("Non-empty body"),
                (2).to_bytes(4, byteorder="little"),
                bstr(r"C:\evidence\one.txt"),
                bstr(r"C:\evidence\two.zip"),
            )
        )

        decoded = json.loads(decode_task_action(action).to_string())

        self.assertEqual(decoded["action_type"], "SendEmail")
        self.assertEqual(decoded["action_id"], "email-action")
        self.assertEqual(decoded["email_body"], "Non-empty body")
        self.assertEqual(
            decoded["email_attachments"],
            [r"C:\evidence\one.txt", r"C:\evidence\two.zip"],
        )

    def scheduled_helper(self, name: str):
        self.assertTrue(
            hasattr(scheduled_task, name),
            f"Scheduled Task helper {name} is not implemented",
        )
        return getattr(scheduled_task, name)

    def test_groups_software_and_system_hives_by_vss(self):
        run_config = RunConfiguration(
            [OutputConfiguration("unused", TEMP_FOLDER, with_timeline=False)]
        )

        def entry(file: str, original_filename: str, vss: str) -> BatchEntry:
            metadata = Metadata("test")
            metadata.original_filename = original_filename
            metadata.vss = vss
            return BatchEntry(file, run_config, metadata)

        grouped = self.scheduled_helper("group_scheduled_task_inputs")(
            [
                entry(
                    "software-2",
                    r"C:\Windows\System32\config\SOFTWARE",
                    "vss-2",
                ),
                entry(
                    "system-1",
                    r"C:\Windows\System32\config\SYSTEM",
                    "vss-1",
                ),
                entry(
                    "software-1a",
                    r"C:\Windows\System32\config\SOFTWARE",
                    "vss-1",
                ),
                entry("software-1b", "SOFTWARE.dat", "vss-1"),
                entry(
                    "system-2",
                    r"C:\Windows\System32\config\SYSTEM",
                    "vss-2",
                ),
                entry("ignored", r"C:\Windows\System32\config\SAM", "vss-1"),
            ]
        )

        self.assertEqual(
            [item.file for item in grouped["vss-1"].software_entries],
            ["software-1a", "software-1b"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-1"].system_entries],
            ["system-1"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-2"].software_entries],
            ["software-2"],
        )
        self.assertEqual(
            [item.file for item in grouped["vss-2"].system_entries],
            ["system-2"],
        )

    def test_registration_date_uses_source_timezone_not_process_timezone(self):
        normalize = self.scheduled_helper("registration_date_to_utc")
        original_timezone = os.environ.get("TZ")
        results = []
        try:
            if not hasattr(time, "tzset"):
                self.skipTest("process timezone switching requires time.tzset")
            for process_timezone in ("UTC", "America/New_York"):
                os.environ["TZ"] = process_timezone
                time.tzset()
                results.append(
                    normalize(
                        "2024-07-01T12:00:00",
                        ZoneInfo("Europe/Paris"),
                    ).isoformat()
                )
        finally:
            if original_timezone is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_timezone
            if hasattr(time, "tzset"):
                time.tzset()

        self.assertEqual(
            results,
            ["2024-07-01T10:00:00+00:00", "2024-07-01T10:00:00+00:00"],
        )

    def test_registration_date_honors_embedded_offset(self):
        normalized = self.scheduled_helper("registration_date_to_utc")(
            "2024-01-15T12:00:00+05:30",
            ZoneInfo("Europe/Paris"),
        )

        self.assertEqual(normalized.isoformat(), "2024-01-15T06:30:00+00:00")

    def test_registration_date_uses_naive_utc_fallback(self):
        normalized = self.scheduled_helper("registration_date_to_utc")(
            "2024-01-15T12:00:00",
            timezone.utc,
        )

        self.assertEqual(normalized.isoformat(), "2024-01-15T12:00:00+00:00")

    # python -m unittest tests.hive.test_scheduled_task.TestScheduledTask.test_scheduled_task -v
    def test_scheduled_task(self):
        plugin_file = os.path.join(CONF_FOLDER, "scheduled_task.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")

        base_output_name = "scheduled_task"

        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".scheduled_tasks.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=False,
        )

        software_metadata = Metadata("test")
        software_metadata.vss = "test_vss"
        software_metadata.original_filename = (
            r"C:\Windows\System32\config\SOFTWARE"
        )
        system_metadata = Metadata("test")
        system_metadata.vss = "test_vss"
        system_metadata.original_filename = r"C:\Windows\System32\config\SYSTEM"

        parser = RegScheduledTask()
        self.assertIsInstance(parser, OgreBatchedPlugin)
        self.assertEqual("RegScheduledTask", parser.description().command)

        run_config = RunConfiguration([output_config])
        entries = [
            BatchEntry(input_file, run_config, software_metadata),
            BatchEntry(
                os.path.join(DATA_FOLDER, "hive", "SYSTEM.dat"),
                run_config,
                system_metadata,
            ),
        ]
        report = parser.parse(entries, plugin_file)
        self.assertEqual(None, report.last_error)

        expected_lines = 530
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)
        self.assertEqual(
            records[0]["data"]["guid"],
            "{01c7c80f-da6a-4698-ba70-4da27991c5a9}",
        )
        self.assertEqual(
            records[0]["data"]["plain"]["name"],
            "{01C7C80F-DA6A-4698-BA70-4DA27991C5A9}",
        )

        maps_data = next(
            record["data"]
            for record in records
            if record["data"].get("task")
            == r"\Microsoft\Windows\Maps\MapsUpdateTask"
            and "registration_date_local" in record["data"]
        )
        self.assertEqual(
            maps_data["registration_date_local"],
            "2014-11-04T23:00:00.000000+00:00",
        )

        jsoned = records[14]
        self.assertEqual(jsoned["related_user"], "S-1-5-32-544")
        self.assertEqual(
            jsoned["description"],
            "task: \\Microsoft\\Windows\\UPnP\\UPnPHostConfig",
        )
        self.assertEqual(
            jsoned["additional_description"],
            "action_type: Exec - exec_command: sc.exe - exec_arguments: config upnphost start= auto",
        )
        data = jsoned["data"]
        self.assertEqual(
            data["creation_date"],
            "2016-01-21T18:20:43.399251+00:00",
        )
        self.assertEqual(
            data["plain"]["mtime"],
            "2015-10-30T07:25:55.704575+00:00",
        )

        device_install_records = [
            record
            for record in records
            if record["data"].get("task")
            == r"\Microsoft\Windows\Plug and Play\Device Install Reboot Required"
        ]
        self.assertGreater(len(device_install_records), 0)
        class_ids = {
            action["com_classid"]
            for record in device_install_records
            for action in record["data"].get("actions", [])
            if action.get("action_type") == "ComHandler"
        }
        self.assertEqual(class_ids, {"48794782-6a1f-47b9-bd52-1d5f95d49c1b"})

    def test_scheduled_task_without_system_reports_and_uses_utc_fallback(self):
        plugin_file = os.path.join(CONF_FOLDER, "scheduled_task.xml")
        software_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")
        base_output_name = "scheduled_task_without_system"
        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".scheduled_tasks.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=True,
                    include_empty=False,
                )
            ]
        )
        metadata = Metadata("test")
        metadata.vss = "missing-system"
        metadata.original_filename = r"C:\Windows\System32\config\SOFTWARE"
        parser = RegScheduledTask()
        self.assertIsInstance(parser, OgreBatchedPlugin)

        with self.assertLogs(
            "dfir_ogre_plugin_windows.system_timezone",
            level="WARNING",
        ) as logs:
            report = parser.parse(
                [BatchEntry(software_file, run_config, metadata)],
                plugin_file,
            )

        self.assertEqual(report.num_errors, 1)
        self.assertEqual(
            report.last_error,
            "No SYSTEM hive found for VSS snapshot 'missing-system'",
        )
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 531)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]
        maps_data = next(
            record["data"]
            for record in records
            if record["data"].get("task")
            == r"\Microsoft\Windows\Maps\MapsUpdateTask"
            and "registration_date_local" in record["data"]
        )
        self.assertEqual(
            maps_data["registration_date_local"],
            "2014-11-05T00:00:00.000000+00:00",
        )
