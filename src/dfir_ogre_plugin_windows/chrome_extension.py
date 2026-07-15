import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
from typing_extensions import override

logger = logging.getLogger(__name__)


_EXTENSION_ID = re.compile(r"^[a-p]{32}$")
_LOCALE_NAME = re.compile(r"^[A-Za-z0-9_@-]+$")
_LOCALIZED_MESSAGE = re.compile(r"^__MSG_(?P<key>.+)__$", re.IGNORECASE)


class ChromeExtension(OgrePlugin):
    @override
    def description(self) -> PluginDescription:
        return PluginDescription(
            "ChromeExtension",
            "Get Chrome based browser extensions",
        )

    @override
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
            try:
                manifest_path = Path(input_file)
                manifest_bytes = manifest_path.read_bytes()
                extension = json.loads(manifest_bytes)
                if not isinstance(extension, dict):
                    raise ValueError("Chrome extension manifest must be a JSON object")

                record = self._manifest_record(
                    extension,
                    manifest_path,
                    hashlib.sha256(manifest_bytes).hexdigest(),
                )
                output.write(record)
            except Exception as e:
                logger.error(
                    "Failed to parse Chrome extension manifest %s: %s",
                    input_file,
                    e,
                )
                report.add_error(f"{e}")  # pyright: ignore[reportUnknownMemberType]

            report.add_output_report(output.get_report())

        return report

    def _manifest_record(
        self,
        extension: Dict[str, object],
        manifest_path: Path,
        manifest_sha256: str,
    ) -> Record:
        record = Record()

        extension_id, version_directory = self._extension_location(manifest_path)
        manifest_version = self._integer(extension.get("manifest_version"))
        default_locale = self._string(extension.get("default_locale"))
        messages = self._locale_messages(manifest_path, default_locale)

        name = self._localized_string(extension.get("name"), messages)
        if not name or _LOCALIZED_MESSAGE.match(name):
            action_title = self._action_title(extension)
            if action_title:
                name = self._localized_string(action_title, messages)

        description = self._localized_string(extension.get("description"), messages)

        record.add("browser", value("chrome"))
        record.add("extension_id", value(extension_id))
        record.add("manifest_path", value(str(manifest_path)))
        record.add("manifest_sha256", value(manifest_sha256))
        record.add("version_directory", value(version_directory))
        record.add("manifest_version", value(manifest_version))
        record.add("extension_type", value(self._extension_type(extension)))
        record.add("default_locale", value(default_locale))
        record.add("name", value(name))
        record.add(
            "short_name",
            value(self._localized_string(extension.get("short_name"), messages)),
        )
        record.add("version", value(self._string(extension.get("version"))))
        record.add("version_name", value(self._string(extension.get("version_name"))))
        record.add("description", value(description))
        record.add("author", value(self._string(extension.get("author"))))
        record.add("homepage_url", value(self._string(extension.get("homepage_url"))))
        record.add("update_url", value(self._string(extension.get("update_url"))))
        record.add(
            "minimum_chrome_version",
            value(self._string(extension.get("minimum_chrome_version"))),
        )
        record.add("incognito", value(self._string(extension.get("incognito"))))
        record.add(
            "offline_enabled",
            value(self._boolean(extension.get("offline_enabled"))),
        )

        extension_pages, sandbox_pages = self._content_security_policies(extension)
        record.add("extension_pages", value(extension_pages))
        record.add("sandbox_pages", value(sandbox_pages))

        permissions = self._strings(extension.get("permissions"))
        host_permissions = self._unique(
            self._strings(extension.get("host_permissions"))
            + [permission for permission in permissions if self._is_host(permission)]
        )
        optional_permissions = self._strings(extension.get("optional_permissions"))
        optional_host_permissions = self._unique(
            self._strings(extension.get("optional_host_permissions"))
            + [
                permission
                for permission in optional_permissions
                if self._is_host(permission)
            ]
        )

        record.add("permissions", self._array(permissions))
        record.add("host_permissions", self._array(host_permissions))
        record.add("optional_permissions", self._array(optional_permissions))
        record.add(
            "optional_host_permissions",
            self._array(optional_host_permissions),
        )

        background = extension.get("background")
        if not isinstance(background, dict):
            background = {}
        record.add(
            "background_service_worker",
            value(self._string(background.get("service_worker"))),
        )
        record.add("background_page", value(self._string(background.get("page"))))
        record.add(
            "background_persistent",
            value(self._boolean(background.get("persistent"))),
        )
        record.add(
            "background_scripts",
            self._array(self._strings(background.get("scripts"))),
        )

        content_script_fields = {
            "content_script_matches": "matches",
            "content_script_exclude_matches": "exclude_matches",
            "content_script_javascript": "js",
            "content_script_stylesheets": "css",
        }
        for output_name, manifest_name in content_script_fields.items():
            record.add(
                output_name,
                self._array(self._content_script_values(extension, manifest_name)),
            )

        externally_connectable = extension.get("externally_connectable")
        if not isinstance(externally_connectable, dict):
            externally_connectable = {}
        record.add(
            "externally_connectable_matches",
            self._array(self._strings(externally_connectable.get("matches"))),
        )
        record.add(
            "externally_connectable_ids",
            self._array(self._strings(externally_connectable.get("ids"))),
        )

        resources, resource_matches, resource_extension_ids = (
            self._web_accessible_resources(extension)
        )
        record.add("web_accessible_resources", self._array(resources))
        record.add("web_accessible_matches", self._array(resource_matches))
        record.add(
            "web_accessible_extension_ids",
            self._array(resource_extension_ids),
        )

        return record

    @staticmethod
    def _content_security_policies(
        extension: Dict[str, object],
    ) -> Tuple[Optional[str], Optional[str]]:
        content_security_policy = extension.get("content_security_policy")
        if isinstance(content_security_policy, str):
            # Manifest V2 uses one policy string for extension pages.
            return content_security_policy, None
        if isinstance(content_security_policy, dict):
            # Manifest V3 separates extension and sandbox page policies.
            extension_pages = ChromeExtension._string(
                content_security_policy.get("extension_pages")
            )
            sandbox_pages = ChromeExtension._string(
                content_security_policy.get("sandbox")
            )
            return extension_pages, sandbox_pages
        return None, None

    @staticmethod
    def _extension_location(manifest_path: Path) -> Tuple[Optional[str], Optional[str]]:
        extension_id = manifest_path.parent.parent.name
        extensions_directory = manifest_path.parent.parent.parent.name
        if (
            extensions_directory.casefold() != "extensions"
            or not _EXTENSION_ID.fullmatch(extension_id)
        ):
            return None, None
        return extension_id, manifest_path.parent.name

    @staticmethod
    def _extension_type(extension: Dict[str, object]) -> str:
        if isinstance(extension.get("theme"), dict):
            return "theme"
        if isinstance(extension.get("app"), dict):
            return "app"
        return "extension"

    @staticmethod
    def _action_title(extension: Dict[str, object]) -> Optional[str]:
        for action_name in ("action", "browser_action", "page_action"):
            action = extension.get(action_name)
            if isinstance(action, dict):
                title = ChromeExtension._string(action.get("default_title"))
                if title:
                    return title
        return None

    @staticmethod
    def _locale_messages(
        manifest_path: Path, default_locale: Optional[str]
    ) -> Dict[str, str]:
        if not default_locale or not _LOCALE_NAME.fullmatch(default_locale):
            return {}

        messages_path = (
            manifest_path.parent / "_locales" / default_locale / "messages.json"
        )
        try:
            messages_json = json.loads(messages_path.read_bytes())
        except (OSError, ValueError):
            return {}
        if not isinstance(messages_json, dict):
            return {}

        messages: Dict[str, str] = {}
        for key, entry in messages_json.items():
            if not isinstance(key, str) or not isinstance(entry, dict):
                continue
            message = entry.get("message")
            if isinstance(message, str):
                messages[key.casefold()] = message
        return messages

    @staticmethod
    def _localized_string(raw_value: object, messages: Dict[str, str]) -> Optional[str]:
        string_value = ChromeExtension._string(raw_value)
        if not string_value:
            return string_value
        matched = _LOCALIZED_MESSAGE.match(string_value)
        if not matched:
            return string_value
        return messages.get(matched.group("key").casefold(), string_value)

    @staticmethod
    def _content_script_values(
        extension: Dict[str, object], field_name: str
    ) -> List[str]:
        content_scripts = extension.get("content_scripts")
        if not isinstance(content_scripts, list):
            return []

        values: List[str] = []
        for content_script in content_scripts:
            if isinstance(content_script, dict):
                values.extend(ChromeExtension._strings(content_script.get(field_name)))
        return ChromeExtension._unique(values)

    @staticmethod
    def _web_accessible_resources(
        extension: Dict[str, object],
    ) -> Tuple[List[str], List[str], List[str]]:
        manifest_resources = extension.get("web_accessible_resources")
        if not isinstance(manifest_resources, list):
            return [], [], []

        resources: List[str] = []
        matches: List[str] = []
        extension_ids: List[str] = []
        for entry in manifest_resources:
            if isinstance(entry, str):
                # Manifest V2 is an array of resource paths.
                resources.append(entry)
            elif isinstance(entry, dict):
                # Manifest V3 groups resources with their allowed callers.
                resources.extend(ChromeExtension._strings(entry.get("resources")))
                matches.extend(ChromeExtension._strings(entry.get("matches")))
                extension_ids.extend(
                    ChromeExtension._strings(entry.get("extension_ids"))
                )
        return (
            ChromeExtension._unique(resources),
            ChromeExtension._unique(matches),
            ChromeExtension._unique(extension_ids),
        )

    @staticmethod
    def _is_host(permission: str) -> bool:
        return permission == "<all_urls>" or "://" in permission

    @staticmethod
    def _string(raw_value: object) -> Optional[str]:
        return raw_value if isinstance(raw_value, str) else None

    @staticmethod
    def _integer(raw_value: object) -> Optional[int]:
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return raw_value
        return None

    @staticmethod
    def _boolean(raw_value: object) -> Optional[bool]:
        return raw_value if isinstance(raw_value, bool) else None

    @staticmethod
    def _strings(raw_value: object) -> List[str]:
        if not isinstance(raw_value, list):
            return []
        return [item for item in raw_value if isinstance(item, str)]

    @staticmethod
    def _unique(values: List[str]) -> List[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _array(values: List[str]) -> Value:
        return Value.Array([Value.String(item) for item in values])
