import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import TestCase

import dfir_ogre_plugin_windows  # noqa: F401
from dfir_ogre_common import OgreBatchedPlugin, OgrePlugin

from . import CONF_FOLDER


class ConfigurationTest(TestCase):
    def test_all_configuration_parsers_are_registered(self):
        registered = {
            parser().description().get_command()
            for parser in OgrePlugin.__subclasses__()
        }
        registered.update(
            parser().description().get_command()
            for parser in OgreBatchedPlugin.__subclasses__()
        )

        unknown = []
        for plugin_file in sorted(Path(CONF_FOLDER).rglob("*.xml")):
            parser = ET.parse(plugin_file).getroot().attrib.get("parser")
            if parser not in registered:
                unknown.append(f"{plugin_file}: {parser}")

        self.assertEqual([], unknown)

    def test_timeline_output_names_reference_declared_fields(self):
        unresolved = []
        for plugin_file in sorted(Path(CONF_FOLDER).rglob("*.xml")):
            root = ET.parse(plugin_file).getroot()
            for mapping in root.findall("mapping"):
                fields_element = mapping.find("fields")
                timeline = mapping.find("timeline")
                if fields_element is None or timeline is None:
                    continue

                fields, objects, dynamic_objects = collect_output_paths(fields_element)
                declared = fields | objects
                for output_name in timeline.findall(".//output_name"):
                    reference = output_name.attrib.get("value")
                    if not reference:
                        continue
                    if reference in declared:
                        continue
                    if any(
                        reference.startswith(f"{dynamic_object}.")
                        for dynamic_object in dynamic_objects
                    ):
                        continue
                    unresolved.append(f"{plugin_file}: {reference}")

        self.assertEqual([], unresolved)


def collect_output_paths(element, prefix=""):
    fields = set()
    objects = set()
    dynamic_objects = set()

    for child in list(element):
        if child.tag == "array":
            child_fields, child_objects, child_dynamic = collect_output_paths(
                child, prefix
            )
            fields.update(child_fields)
            objects.update(child_objects)
            dynamic_objects.update(child_dynamic)
            continue

        name = child.attrib.get("output") or child.attrib.get("input")
        if not name:
            continue

        path = f"{prefix}.{name}" if prefix else name
        if child.tag in {"field", "multi_input"}:
            if child.attrib.get("parser") == "Extension":
                child_fields, child_objects, child_dynamic = collect_output_paths(
                    child, prefix
                )
                fields.update(child_fields)
                objects.update(child_objects)
                dynamic_objects.update(child_dynamic)
            else:
                fields.add(path)
        elif child.tag == "object":
            objects.add(path)
            if list(child):
                child_fields, child_objects, child_dynamic = collect_output_paths(
                    child, path
                )
                fields.update(child_fields)
                objects.update(child_objects)
                dynamic_objects.update(child_dynamic)
            if not list(child) or child.attrib.get("dynamic") == "true":
                dynamic_objects.add(path)

    return fields, objects, dynamic_objects
