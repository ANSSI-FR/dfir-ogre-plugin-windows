import logging
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Dict, List, Optional
from uuid import UUID

from dateutil import parser as date_parser
from dfir_ogre_common import (
    BatchEntry,
    OgreBatchedPlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RegValue,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc, value
from dfir_ogre_plugin_windows.security_descriptor import SecurityDescriptor
from dfir_ogre_plugin_windows.system_timezone import (
    entry_snapshot,
    entry_source_basename,
    is_system_hive,
    resolve_system_timezone_or_utc,
)

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTaskBatch:
    software_entries: List[BatchEntry]
    system_entries: List[BatchEntry]


def is_software_hive(entry: BatchEntry) -> bool:
    filename = entry_source_basename(entry)
    return (
        filename == "software"
        or filename.startswith("software.")
        or filename.startswith("software_")
    )


def group_scheduled_task_inputs(
    input_files: List[BatchEntry],
) -> Dict[Optional[str], ScheduledTaskBatch]:
    grouped: Dict[Optional[str], ScheduledTaskBatch] = {}
    for entry in input_files:
        snapshot = entry_snapshot(entry)
        batch = grouped.setdefault(snapshot, ScheduledTaskBatch([], []))
        if is_system_hive(entry):
            batch.system_entries.append(entry)
        elif is_software_hive(entry):
            batch.software_entries.append(entry)
    return grouped


def registration_date_to_utc(
    registration_date: str,
    source_timezone: tzinfo,
) -> datetime:
    parsed = date_parser.parse(registration_date)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone, fold=0)
    return parsed.astimezone(timezone.utc)


class RegScheduledTask(OgreBatchedPlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegScheduledTask",
            "Get scheduled tasks from the Software hive",
        )

    def parse(
        self,
        input_files: List[BatchEntry],
        plugin_file: str,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()

        for snapshot, batch in group_scheduled_task_inputs(input_files).items():
            if not batch.software_entries:
                continue

            timezone_info = resolve_system_timezone_or_utc(
                batch.system_entries,
                snapshot,
                report,
            )
            for entry in batch.software_entries:
                self.parse_software(entry, plugin_config, timezone_info, report)

        return report

    def parse_software(
        self,
        entry: BatchEntry,
        plugin_config: PluginConfiguration,
        timezone_info: tzinfo,
        report: RunReport,
    ) -> None:
        key_paths = [
            "\\HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache",
            "\\HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows NT\\CurrentVersion\\Schedule",
        ]

        try:
            reg = Registry.load(entry.file, "\\HKLM\\SOFTWARE")
        except Exception as e:
            report.add_error(f"{e}")
            return

        with Output(
            entry.run_config,
            plugin_config,
            entry.metadata,
        ) as output:
            try:
                for key_path in key_paths:
                    keys = reg.glob_keys(key_path)

                    for key in keys:
                        self.parse_key(output, key, report, timezone_info)

            except Exception as e:
                report.add_error(f"{e}")

            report.add_output_report(output.get_report())

    def parse_key(
        self,
        output: Output,
        task_cache_key: RegKey,
        report: RunReport,
        timezone_info: tzinfo,
    ):
        tasks = task_cache_key.sub_key("Tasks")

        if not tasks:
            return

        for task in tasks.sub_keys():
            path_tree = task.value_data("Path")
            if path_tree:
                tree = task_cache_key.sub_path("Tree" + path_tree)
            else:
                tree = None

            tuple = Record()

            tuple.add("guid", value(task.name))

            author = task.value_data("Author")
            tuple.add("author", value(author))

            data = task.value_data("Data")
            tuple.add("data", value(data))

            registration_date_local = task.value_data("Date")
            if registration_date_local:
                registration_date = registration_date_to_utc(
                    registration_date_local,
                    timezone_info,
                )
                tuple.add("registration_date_local", value(registration_date))

            task_description = task.value_data("Description")
            tuple.add("task_description", value(task_description))

            documentation = task.value_data("Documentation")
            tuple.add("documentation", value(documentation))

            dyninfo_dispatcher = task.value("DynamicInfo")
            if dyninfo_dispatcher:
                process_dyninfo(dyninfo_dispatcher, tuple)

            hash = task.value_data("Hash")

            if hash and isinstance(hash, bytes):
                tuple.add("hash", Value.String(hash.hex()))

            task_path = task.value_data("Path")
            tuple.add("task", value(task_path))

            schema = task.value_data("Schema")
            if schema:
                tuple.add("schema", value(int(schema)))

            sd = task.value_data("SecurityDescriptor")
            if sd:
                security_descriptor = SecurityDescriptor()
                security_descriptor.from_string(sd)
                tuple.add(
                    "security_descriptor", Value.Object(security_descriptor.to_record())
                )

            source = task.value_data("Source")
            tuple.add("source", value(source))

            trigger = task.value_data("Trigger")
            tuple.add("trigger", value(trigger))

            uri = task.value_data("URI")
            tuple.add("uri", value(uri))

            version = task.value_data("Version")
            tuple.add("version", value(version))

            actions_data = task.value_data("Actions")
            actions: List[Value] = []
            if actions_data and len(actions_data) > 0x6:
                version = int.from_bytes(
                    actions_data[:0x2], byteorder="little", signed=False
                )
                if version >= 2:
                    context_size = int.from_bytes(
                        actions_data[0x2:0x6], byteorder="little", signed=False
                    )
                    self.actions_context = actions_data[
                        0x6 : 0x6 + context_size
                    ].decode("utf-16-le")
                    index = 0x6 + context_size
                else:
                    index = 0x2
                action_size = len(actions_data)
                while index < action_size:
                    actions.append(parse_task_action(actions_data[index:]))
                    # index of next actions
                    next_index = [
                        i
                        for i in (
                            actions_data[index:].find(b"\x66\x66"),
                            actions_data[index:].find(b"\x77\x77"),
                            actions_data[index:].find(b"\x88\x88"),
                            actions_data[index:].find(b"\x99\x99"),
                        )
                        if i > 0
                    ]
                    # go to next lowest, default to size
                    index = index + min(next_index, default=action_size)

            if actions:
                tuple.add("actions", Value.Array(actions))

            boot = task_cache_key.sub_path(f"Boot\\{task.name}")
            if boot:
                tuple.add("boot", Value.Object(boot.to_record()))

            logon = task_cache_key.sub_path(f"Logon\\{task.name}")
            if logon:
                tuple.add("logon", Value.Object(logon.to_record()))

            maintenance = task_cache_key.sub_path(f"Maintenance\\{task.name}")
            if maintenance:
                tuple.add("maintenance", Value.Object(maintenance.to_record()))

            plain = task_cache_key.sub_path(f"Plain\\{task.name}")
            if plain:
                tuple.add("plain", Value.Object(plain.to_record()))

            if tree:
                tuple.add("tree", Value.Object(tree.to_record()))

            tuple.add("key_path", value(task.path))
            tuple.add("key_modif_time", value(task.mtime))
            tuple.add(
                "key_security", Value.Object(task.security_descriptor.to_record())
            )

            output.write(tuple)


def parse_task_action(data: bytes) -> Value:
    return Value.Object(decode_task_action(data))


def decode_task_action(data: bytes) -> Record:
    task_action = Record()

    cursor = 0x2
    # get action_id
    bstr_size = int.from_bytes(
        data[cursor : cursor + 4], byteorder="little", signed=False
    )
    if bstr_size > 0:
        action_id = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
        task_action.add("action_id", value(action_id))

    cursor += 4 + bstr_size
    # if action type = command
    if data[:0x2] == b"\x66\x66":
        task_action.add("action_type", value("Exec"))
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            exec_command = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("exec_command", value(exec_command))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            exec_arguments = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                "utf-16-le"
            )
            task_action.add("exec_arguments", value(exec_arguments))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            exec_working_dir = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                "utf-16-le"
            )
            task_action.add("exec_working_dir", value(exec_working_dir))

    # else if action type = comhandler
    elif data[:0x2] == b"\x77\x77":
        task_action.add("action_type", value("ComHandler"))
        # handle com_classid
        byte_task = data[cursor : cursor + 0x10]
        com_classid = str(UUID(bytes_le=byte_task))
        task_action.add("com_classid", value(com_classid))

        cursor += 0x10
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            com_data = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("com_data", value(com_data))

    # else if action type = email
    elif data[:0x2] == b"\x88\x88":
        task_action.add("action_type", value("SendEmail"))
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_from = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_from", value(email_from))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_to = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_to", value(email_to))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_cc = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_cc", value(email_cc))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_bcc = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_bcc", value(email_bcc))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_replyto = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                "utf-16-le"
            )
            task_action.add("email_replyto", value(email_replyto))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_server = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_server", value(email_server))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_subject = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                "utf-16-le"
            )
            task_action.add("email_subject", value(email_subject))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            email_body = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("email_body", value(email_body))

        cursor += 4 + bstr_size
        num_attachments = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        cursor += 4
        email_attachments = []
        for _ in range(num_attachments):
            bstr_size = int.from_bytes(
                data[cursor : cursor + 4], byteorder="little", signed=False
            )
            if bstr_size > 0:
                attachment = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                    "utf-16-le"
                )
                email_attachments.append(value(attachment))
            cursor += 4 + bstr_size

        if email_attachments:
            task_action.add("email_attachments", Value.Array(email_attachments))

    # else if action type = messagebox
    elif data[:0x2] == b"\x99\x99":
        task_action.add("action_type", value("ShowMessage"))

        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            message_body = data[cursor + 4 : cursor + 4 + bstr_size].decode("utf-16-le")
            task_action.add("message_body", value(message_body))

        cursor += 4 + bstr_size
        bstr_size = int.from_bytes(
            data[cursor : cursor + 4], byteorder="little", signed=False
        )
        if bstr_size > 0:
            message_title = data[cursor + 4 : cursor + 4 + bstr_size].decode(
                "utf-16-le"
            )
            task_action.add("message_title", value(message_title))
    return task_action


def process_dyninfo(reg_value: RegValue, record: Record):
    """Dispatch the content of the DynamicInfo key"""
    dyninfo = reg_value.data()
    creation_date = int.from_bytes(dyninfo[0x4:0xC], byteorder="little", signed=False)
    if creation_date:
        record.add("creation_date", Value.Date(filetime_to_utc(creation_date)))

    last_run_launch_date = int.from_bytes(
        dyninfo[0xC:0x14], byteorder="little", signed=False
    )
    if last_run_launch_date:
        record.add(
            "last_run_launch_date", Value.Date(filetime_to_utc(last_run_launch_date))
        )
    # version = NT6.0 ou NT6.1
    if len(dyninfo) == 0x1C:
        last_run_exit_code = int.from_bytes(
            dyninfo[0x14:0x18], byteorder="little", signed=False
        )
        record.add("last_run_exit_code", Value.Int(last_run_exit_code))
    # version > NT6.1
    if len(dyninfo) == 0x24:
        last_run_exit_date = int.from_bytes(
            dyninfo[0x1C:0x24], byteorder="little", signed=False
        )
        if last_run_exit_date:
            record.add(
                "last_run_exit_date", Value.Date(filetime_to_utc(last_run_exit_date))
            )

        last_run_exit_code = int.from_bytes(
            dyninfo[0x18:0x1C], byteorder="little", signed=False
        )
        record.add("last_run_exit_code", Value.Int(last_run_exit_code))
