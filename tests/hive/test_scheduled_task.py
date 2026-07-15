import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import RegScheduledTask
from dfir_ogre_plugin_windows.registry.scheduled_task import decode_task_action

from . import CONF_FOLDER, DATA_FOLDER, TEMP_FOLDER

os.makedirs(TEMP_FOLDER, exist_ok=True)


def bstr(text: str) -> bytes:
    encoded = text.encode("utf-16-le")
    return len(encoded).to_bytes(4, byteorder="little") + encoded


class TestScheduledTask(TestCase):
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

        metadata = Metadata("test")
        parser = RegScheduledTask()
        self.assertEqual("RegScheduledTask", parser.description().command)  # type: ignore

        run_config = RunConfiguration([output_config])
        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 530
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name
        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]

        self.assertEqual(len(records), expected_lines)

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
