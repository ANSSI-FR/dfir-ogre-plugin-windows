import json
import os
from unittest import TestCase

from dfir_ogre_common import Metadata, OutputConfiguration, RunConfiguration

from dfir_ogre_plugin_windows import ChromeExtension

from . import BASE_TEMP_FOLDER

DATA_FOLDER = os.path.join("tests", "data")
CONF_FOLDER = os.path.join("configuration")
TEMP_FOLDER = os.path.join(BASE_TEMP_FOLDER, "browser_extension")
os.makedirs(TEMP_FOLDER, exist_ok=True)


class TestChromeExtension(TestCase):
    def parse_manifest(self, input_file, base_output_name):
        plugin_file = os.path.join(CONF_FOLDER, "chrome_extension.xml")
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".chrome_extension.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=False,
            include_empty=False,
        )

        parser = ChromeExtension()
        self.assertEqual(
            "ChromeExtension",
            parser.description().command,  # type: ignore
        )

        report = parser.parse(
            input_file,
            plugin_file,
            RunConfiguration([output_config]),
            Metadata("test"),
        )
        self.assertEqual(None, report.last_error)
        self.assertEqual(report.output_reports[0].file_reports[0].num_lines, 1)
        self.assertEqual(
            report.output_reports[0].file_reports[0].file_name,
            output_file,
        )

        with open(output_file) as fp:
            records = [json.loads(line) for line in fp]
        self.assertEqual(len(records), 1)
        return records[0]

    # python -m unittest tests.test_chrome_extension.TestChromeExtension.test_chrome -v
    def test_chrome(self):
        input_file = os.path.join(
            DATA_FOLDER, "browser_extension", "chrome_manifest.json"
        )

        extension = self.parse_manifest(input_file, "chrome")

        self.assertEqual(extension["browser"], "chrome")
        self.assertEqual(extension["extension_type"], "extension")
        self.assertEqual(extension["manifest_version"], 3)
        self.assertEqual(extension["name"], "Dark Reader")
        self.assertEqual(extension["version"], "4.9.112")
        self.assertEqual(extension["author"], "Alexander Shutau")
        self.assertEqual(extension["minimum_chrome_version"], "106.0.0.0")
        self.assertEqual(
            extension["update_url"],
            "https://clients2.google.com/service/update2/crx",
        )
        self.assertEqual(
            extension["manifest_sha256"],
            "417aa37cc8f5ac51caff566fdb56c48384a3dbd78005cc109082198a2d99e90b",
        )
        self.assertEqual(
            extension["permissions"],
            ["alarms", "fontSettings", "scripting", "storage"],
        )
        self.assertEqual(extension["host_permissions"], ["*://*/*"])
        self.assertEqual(extension["optional_permissions"], ["contextMenus"])
        self.assertEqual(
            extension["background_service_worker"],
            "background/index.js",
        )
        self.assertEqual(extension["content_script_matches"], ["<all_urls>"])
        self.assertEqual(
            extension["content_script_javascript"],
            [
                "inject/proxy.js",
                "inject/fallback.js",
                "inject/index.js",
                "inject/color-scheme-watcher.js",
            ],
        )
        self.assertEqual(
            extension["extension_pages"],
            (
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src * data:; connect-src *; navigate-to 'self' "
                "https://darkreader.org/* "
                "https://github.com/darkreader/darkreader/blob/main/CONTRIBUTING.md "
                "https://github.com/darkreader/darkreader "
                "https://twitter.com/darkreaderapp; media-src 'none'; "
                "child-src 'none'; worker-src 'none'; object-src 'none'"
            ),
        )

    def test_chrome_manifest_v2(self):
        input_file = os.path.join(
            DATA_FOLDER,
            "browser_extension",
            "Extensions",
            "abcdefghijklmnopabcdefghijklmnop",
            "2.4.1_0",
            "manifest.json",
        )

        extension = self.parse_manifest(input_file, "chrome_v2")

        self.assertEqual(
            extension["extension_id"],
            "abcdefghijklmnopabcdefghijklmnop",
        )
        self.assertEqual(extension["version_directory"], "2.4.1_0")
        self.assertEqual(extension["manifest_version"], 2)
        self.assertEqual(extension["name"], "Legacy Audit Extension")
        self.assertEqual(
            extension["description"],
            "Historical Manifest V2 test extension",
        )
        self.assertEqual(extension["version"], "2.4.1")
        self.assertEqual(extension["version_name"], "2.4.1 legacy")
        self.assertEqual(extension["author"], "Forensic Labs")
        self.assertEqual(
            extension["homepage_url"],
            "https://legacy.example/extensions/audit",
        )
        self.assertEqual(extension["incognito"], "split")
        self.assertTrue(extension["offline_enabled"])
        self.assertEqual(
            extension["manifest_sha256"],
            "5056b64dfde0d2c09224d15e64feb045810d636f1a9ea8ff6b4760696f4376f2",
        )
        self.assertEqual(
            extension["extension_pages"],
            "default-src 'self' https://extension.resource.example",
        )
        self.assertEqual(
            extension["permissions"],
            ["tabs", "storage", "https://*.example.com/*", "<all_urls>"],
        )
        self.assertEqual(
            extension["host_permissions"],
            ["https://*.example.com/*", "<all_urls>"],
        )
        self.assertEqual(
            extension["optional_host_permissions"],
            ["https://optional.example/*"],
        )
        self.assertEqual(
            extension["background_scripts"],
            ["background.js", "telemetry.js"],
        )
        self.assertEqual(extension["background_page"], "background.html")
        self.assertTrue(extension["background_persistent"])
        self.assertEqual(
            extension["content_script_matches"],
            ["https://*.example.com/*"],
        )
        self.assertEqual(
            extension["content_script_exclude_matches"],
            ["https://safe.example.com/*"],
        )
        self.assertEqual(extension["content_script_javascript"], ["inject.js"])
        self.assertEqual(extension["content_script_stylesheets"], ["inject.css"])
        self.assertEqual(
            extension["externally_connectable_matches"],
            ["https://trusted.example/*"],
        )
        self.assertEqual(
            extension["web_accessible_resources"],
            ["images/*.png", "scripts/bridge.js"],
        )
