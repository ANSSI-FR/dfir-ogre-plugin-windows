import json
from unittest import TestCase

from dfir_ogre_plugin_windows.security_descriptor import ACE


class SecurityDescriptorTest(TestCase):
    def test_object_ace_guids_are_lowercase(self):
        ace = ACE()
        ace.from_string(
            "OA;;RP;F20DA720-C02F-11CE-927B-0800095AE340;"
            "D27CDB6E-AE6D-11CF-96B8-444553540000;SY"
        )

        record = json.loads(ace.to_record().to_string())

        self.assertEqual(
            record["object_guid"],
            "f20da720-c02f-11ce-927b-0800095ae340",
        )
        self.assertEqual(
            record["inherit_object_guid"],
            "d27cdb6e-ae6d-11cf-96b8-444553540000",
        )
