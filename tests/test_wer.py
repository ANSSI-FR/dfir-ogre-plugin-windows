import json
import os
from unittest import TestCase
from unittest.mock import patch

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import Wer
from dfir_ogre_plugin_windows.wer import (
    InvalidWerReportError,
    decode_wer_report,
)

from . import BASE_TEMP_FOLDER, CONF_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "wer")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class WerDecoderTest(TestCase):
    valid_text = "Version=1\nEventType=EncodingTest\n"

    def test_decode_wer_report_supports_declared_encodings(self):
        encoded_reports = {
            "utf16le_bom": (
                b"\xff\xfe" + self.valid_text.encode("utf-16-le")
            ),
            "utf16le_without_bom": self.valid_text.encode("utf-16-le"),
            "utf8_bom": b"\xef\xbb\xbf" + self.valid_text.encode("utf-8"),
            "utf8_without_bom": self.valid_text.encode("utf-8"),
        }

        for label, payload in encoded_reports.items():
            with self.subTest(label=label):
                self.assertEqual(
                    decode_wer_report(payload),
                    self.valid_text,
                )

    def test_decode_wer_report_rejects_utf16be(self):
        payload = b"\xfe\xff" + self.valid_text.encode("utf-16-be")

        with self.assertRaisesRegex(
            InvalidWerReportError,
            "unsupported UTF-16BE",
        ):
            decode_wer_report(payload)

    def test_decode_wer_report_accepts_report_description_marker(self):
        text = "Version=1\nReportDescription=alpha=beta=gamma\n"

        self.assertEqual(
            decode_wer_report(text.encode("utf-16-le")),
            text,
        )

    def test_decode_wer_report_rejects_non_wer_payloads(self):
        payloads = {
            "text_without_wer_marker": (
                b"Version=1\nProduct=SharePoint\n"
            ),
            "binary_like_wer_utf8_1": b"\xbe\xc6\x97\x00\xff\x81",
            "text_and_binary_like_wer_utf8_2": (
                b"FarmId\tRequestUsage\n" + b"\x00\x00\xff\x81"
            ),
        }

        for label, payload in payloads.items():
            with self.subTest(label=label):
                with self.assertRaises(InvalidWerReportError):
                    decode_wer_report(payload)


class WerTest(TestCase):
    def parse_file(self, input_file: str, base_output_name: str):
        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".wer.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)
        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )
        report = Wer().parse(
            input_file,
            os.path.join(CONF_FOLDER, "wer.xml"),
            run_config,
            Metadata("test"),
        )
        return report, output_file

    def parse_payload(
        self,
        payload: bytes,
        base_output_name: str,
    ):
        input_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".input.wer",
        )
        with open(input_file, "wb") as fp:
            fp.write(payload)
        return self.parse_file(input_file, base_output_name)

    def test_wer_parses_utf8_with_and_without_bom(self):
        text = (
            "Version=1\n"
            "EventType=Utf8Report\n"
            "ReportDescription=café\n"
        )
        encodings = {
            "utf8_bom": b"\xef\xbb\xbf" + text.encode("utf-8"),
            "utf8_without_bom": text.encode("utf-8"),
        }

        for label, payload in encodings.items():
            with self.subTest(label=label):
                report, output_file = self.parse_payload(payload, label)
                self.assertEqual(
                    report.num_errors,
                    0,
                    report.last_error,
                )
                self.assertIsNone(report.last_error)
                self.assertEqual(len(report.output_reports), 1)
                with open(output_file, encoding="utf-8") as fp:
                    record = json.loads(fp.readline())
                self.assertEqual(record["version"], 1)
                self.assertEqual(record["event_type"], "Utf8Report")
                self.assertEqual(record["report_description"], "café")

    def test_wer_rejects_non_reports_before_output(self):
        payloads = {
            "invalid_binary_1": b"\xbe\xc6\x97\x00\xff\x81",
            "invalid_binary_2": (
                b"FarmId\tRequestUsage\n" + b"\x00\x00\xff\x81"
            ),
            "valid_utf8_without_wer_structure": (
                b"Version=1\nProduct=SharePoint\n"
            ),
            "utf16be": (
                b"\xfe\xff"
                + "Version=1\nEventType=WrongEndian\n".encode(
                    "utf-16-be"
                )
            ),
        }

        for label, payload in payloads.items():
            with self.subTest(label=label):
                report, output_file = self.parse_payload(payload, label)
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(
                    report.last_error.startswith(
                        "Invalid WER report:"
                    )
                )
                self.assertEqual(len(report.output_reports), 0)
                self.assertFalse(os.path.exists(output_file))

    def test_wer_counts_input_errors(self):
        missing_input = os.path.join(
            TEMP_FOLDER,
            "missing_wer_input.data",
        )
        if os.path.exists(missing_input):
            os.remove(missing_input)
        report, output_file = self.parse_file(
            missing_input,
            "missing_wer_input",
        )

        self.assertEqual(report.num_errors, 1)
        self.assertTrue(report.last_error.startswith("WER input:"))
        self.assertEqual(len(report.output_reports), 0)
        self.assertFalse(os.path.exists(output_file))

    def test_wer_counts_other_phase_exceptions(self):
        payload = b"Version=1\nEventType=ExceptionTest\n"
        failures = (
            (
                "configuration",
                "dfir_ogre_plugin_windows.wer.PluginConfiguration.load",
                "WER configuration:",
            ),
            (
                "record_construction",
                "dfir_ogre_plugin_windows.wer.build_wer_record",
                "WER parsing failed:",
            ),
            (
                "output",
                "dfir_ogre_plugin_windows.wer.Output",
                "WER output:",
            ),
        )

        for label, target, expected_prefix in failures:
            with self.subTest(label=label):
                with patch(
                    target,
                    side_effect=RuntimeError(f"forced {label} failure"),
                ):
                    report, output_file = self.parse_payload(
                        payload,
                        "wer_exception_" + label,
                    )
                self.assertEqual(report.num_errors, 1)
                self.assertTrue(
                    report.last_error.startswith(expected_prefix)
                )
                self.assertEqual(len(report.output_reports), 0)
                self.assertFalse(os.path.exists(output_file))

    def test_wer_normalizes_guid_fields_without_rewriting_embedded_text(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")
        input_file = os.path.join(TEMP_FOLDER, "report_uppercase_guids.wer")
        base_output_name = "wer_uppercase_guids"
        embedded = "Path-{F20DA720-C02F-11CE-927B-0800095AE340}"

        with open(input_file, "wb") as fp:
            fp.write(
                b"\xff\xfe"
                + (
                    "Version=1\n"
                    "ReportIdentifier=F20DA720-C02F-11CE-927B-0800095AE340\n"
                    "IntegratorReportIdentifier=D27CDB6E-AE6D-11CF-96B8-444553540000\n"
                    "AppSessionGuid=9C205A39-1250-487D-ABD7-E831C6290539\n"
                    f"ReportDescription={embedded}\n"
                ).encode("utf-16-le")
            )

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".wer.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)
        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )

        report = Wer().parse(
            input_file,
            plugin_file,
            run_config,
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        with open(output_file) as fp:
            record = json.loads(fp.readline())
        self.assertEqual(
            record["report_identifier"],
            "f20da720-c02f-11ce-927b-0800095ae340",
        )
        self.assertEqual(
            record["integrator_report_identifier"],
            "d27cdb6e-ae6d-11cf-96b8-444553540000",
        )
        self.assertEqual(
            record["app_session_guid"],
            "9c205a39-1250-487d-abd7-e831c6290539",
        )
        self.assertEqual(record["report_description"], embedded)

    def test_wer_preserves_first_key_without_bom(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")
        input_file = os.path.join(TEMP_FOLDER, "report_without_bom.wer")
        base_output_name = "wer_without_bom"

        with open(input_file, "wb") as fp:
            fp.write(
                ("Version=1\n" "EventType=BomlessReport\n").encode("utf-16-le")
            )

        output_file = os.path.join(
            TEMP_FOLDER,
            base_output_name + ".wer.jsonl",
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        run_config = RunConfiguration(
            [
                OutputConfiguration(
                    base_output_name,
                    TEMP_FOLDER,
                    with_timeline=False,
                    include_empty=False,
                )
            ]
        )

        report = Wer().parse(
            input_file,
            plugin_file,
            run_config,
            Metadata("test"),
        )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as fp:
            record = json.loads(fp.readline())
        self.assertEqual(record.get("version"), 1)
        self.assertEqual(record["event_type"], "BomlessReport")

    # python -m unittest tests.test_wer.WerTest.test_wer -v
    def test_wer(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")
        input_file = os.path.join(DATA_FOLDER, "wer", "report_1.wer")
        base_output_name = "wer_report_1"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".wer.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Wer()
        self.assertEqual("WER", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["sig"]["stack_version"],
                        "10.0.17763.1",
                    )
                    self.assertEqual(
                        jsoned["dynamic_sig"]["os_version"],
                        "10.0.17763.2.0.0.272.7",
                    )
                    self.assertEqual(len(jsoned["os_info"]), 33)
                    self.assertEqual(jsoned["os_info"]["vermaj"], "10")
                    self.assertEqual(
                        jsoned["os_info"]["edition"],
                        "ServerStandard",
                    )
                    self.assertEqual(
                        jsoned["loaded_module"][0],
                        "C:\\Windows\\System32\\profapi.dll",
                    )
                    self.assertEqual(
                        jsoned["files"][0]["CabName"],
                        "CBS.log",
                    )
                    self.assertEqual(len(jsoned["files"]), 7)
                    self.assertEqual(jsoned["files"][-1]["CabName"], "sysinfo.txt")

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_wer.WerTest.test_wer_preserves_equals_in_values -v
    def test_wer_preserves_equals_in_values(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")
        input_file = os.path.join(TEMP_FOLDER, "report_equals.wer")
        base_output_name = "wer_report_equals"

        with open(input_file, "wb") as fp:
            fp.write(
                b"\xff\xfe"
                + "Version=1\nReportDescription=alpha=beta=gamma\n".encode(
                    "utf-16-le"
                )
            )

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".wer.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Wer()

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        with open(output_file) as fp:
            jsoned = json.loads(fp.readline())
            self.assertEqual(jsoned["report_description"], "alpha=beta=gamma")

    # python -m unittest tests.test_wer.WerTest.test_wer_2 -v
    def test_wer_2(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")

        input_file = os.path.join(DATA_FOLDER, "wer", "report_2.wer")
        base_output_name = "wer_report_2"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".wer.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=False,
          include_empty=False,
        )

        run_plugin = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Wer()
        self.assertEqual("WER", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_plugin, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 1
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["sig"]["application_name"],
                        "praid:CortanaUI",
                    )
                    self.assertEqual(
                        jsoned["dynamic_sig"]["additional_hang_signature_1"],
                        "e333f15cda3f1bebe555d03ba97991d0",
                    )
                    self.assertEqual(len(jsoned["os_info"]), 37)
                    self.assertEqual(jsoned["os_info"]["vermaj"], "10")
                    self.assertEqual(
                        jsoned["os_info"]["edition"],
                        "Enterprise",
                    )
                    self.assertEqual(
                        jsoned["state"]["transport._done_stage1"],
                        "1",
                    )
                    self.assertEqual(
                        jsoned["loaded_module"][0],
                        "C:\\Windows\\SystemApps\\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\\SearchHost.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)

    # python -m unittest tests.test_wer.WerTest.test_wer_timeline -v
    def test_wer_timeline(self):
        plugin_file = os.path.join(CONF_FOLDER, "wer.xml")

        input_file = os.path.join(DATA_FOLDER, "wer", "report_2.wer")
        base_output_name = "wer_timeline"

        output_file = os.path.join(TEMP_FOLDER, base_output_name + ".wer.jsonl")
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
          base_output_name,
          TEMP_FOLDER,
          with_timeline=True,
          include_empty=False,
        )

        run_config = RunConfiguration([output_config], True)
        metadata = Metadata("test")
        parser = Wer()
        self.assertEqual("WER", parser.description().command)  # type: ignore

        report = parser.parse(input_file, plugin_file, run_config, metadata)
        self.assertEqual(None, report.last_error)

        expected_lines = 2
        lines = report.output_reports[0].file_reports[0].num_lines
        self.assertEqual(lines, expected_lines)

        filename = report.output_reports[0].file_reports[0].file_name

        self.assertEqual(filename, output_file)

        with open(output_file) as fp:
            i = 0
            for line in fp:
                jsoned = json.loads(line)
                if i == 0:
                    self.assertEqual(
                        jsoned["description"],
                        "app_path: C:\\Windows\\SystemApps\\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\\SearchHost.exe",
                    )
                    self.assertEqual(
                        jsoned["data"]["sig"]["application_name"],
                        "praid:CortanaUI",
                    )
                    self.assertEqual(
                        jsoned["data"]["dynamic_sig"]["additional_hang_signature_1"],
                        "e333f15cda3f1bebe555d03ba97991d0",
                    )
                    self.assertEqual(
                        jsoned["data"]["loaded_module"][0],
                        "C:\\Windows\\SystemApps\\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\\SearchHost.exe",
                    )

                i += 1
            self.assertEqual(i, expected_lines)
