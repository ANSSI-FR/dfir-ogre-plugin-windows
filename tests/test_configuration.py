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

    def test_common_security_descriptor_mappings_use_plural_ace_arrays(self):
        required_fields = {
            "ace_type",
            "account_sid",
            "ace_size",
            "object_type_guid",
            "inherited_object_type_guid",
            "raw_hex",
        }
        required_array_fields = {"ace_flags", "rights"}
        errors = []
        mapping_count = 0

        for plugin_file in sorted(Path(CONF_FOLDER).rglob("*.xml")):
            root = ET.parse(plugin_file).getroot()
            for singular_name in ("sacl_ace", "dacl_ace"):
                if root.findall(f".//object[@input='{singular_name}']"):
                    errors.append(f"{plugin_file}: contains {singular_name}")

            descriptors = list(root.findall(".//object[@input='key_security']"))
            if plugin_file == Path(CONF_FOLDER, "hive.xml"):
                descriptors.extend(
                    root.findall(".//object[@input='security_descriptor']")
                )

            for descriptor in descriptors:
                mapping_count += 1
                descriptor_name = descriptor.attrib["input"]
                for acl_name in ("sacl_aces", "dacl_aces"):
                    ace_mappings = descriptor.findall(
                        f"./array/object[@input='{acl_name}']"
                    )
                    if len(ace_mappings) != 1:
                        errors.append(
                            f"{plugin_file}: {descriptor_name}.{acl_name} "
                            f"has {len(ace_mappings)} mappings"
                        )
                        continue

                    ace_mapping = ace_mappings[0]
                    direct_fields = {
                        field.attrib["input"]
                        for field in ace_mapping.findall("./field")
                    }
                    array_fields = {
                        field.attrib["input"]
                        for field in ace_mapping.findall("./array/field")
                    }
                    missing_fields = required_fields - direct_fields
                    missing_array_fields = required_array_fields - array_fields
                    if missing_fields:
                        errors.append(
                            f"{plugin_file}: {descriptor_name}.{acl_name} missing "
                            f"fields {sorted(missing_fields)}"
                        )
                    if missing_array_fields:
                        errors.append(
                            f"{plugin_file}: {descriptor_name}.{acl_name} missing "
                            f"array fields {sorted(missing_array_fields)}"
                        )

        self.assertEqual(29, mapping_count)
        self.assertEqual([], errors)


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
