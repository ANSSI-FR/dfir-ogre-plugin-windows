import json
from unittest import TestCase

from dfir_ogre_plugin_windows.security_descriptor import ACE, SecurityDescriptor


class SecurityDescriptorTest(TestCase):
    def test_security_descriptor_uses_plural_ace_arrays(self):
        dacl_descriptor = SecurityDescriptor()
        dacl_descriptor.from_string("O:SYG:BAD:(A;;KR;;;BU)")

        dacl_record = json.loads(dacl_descriptor.to_record().to_string())

        self.assertEqual(
            dacl_record["dacl_aces"],
            [
                {
                    "ace_type": "ACCESS_ALLOWED_ACE_TYPE",
                    "account_sid": "DOMAIN_ALIAS_RID_USERS",
                    "rights": ["KEY_READ"],
                }
            ],
        )
        self.assertNotIn("dacl_ace", dacl_record)

        sacl_descriptor = SecurityDescriptor()
        sacl_descriptor.from_string("S:(AU;SA;KR;;;WD)")

        sacl_record = json.loads(sacl_descriptor.to_record().to_string())

        self.assertEqual(
            sacl_record["sacl_aces"],
            [
                {
                    "ace_type": "SYSTEM_AUDIT_ACE_TYPE",
                    "account_sid": "SECURITY_WORLD_RID",
                    "ace_flags": ["SUCCESSFUL_ACCESS_ACE_FLAG"],
                    "rights": ["KEY_READ"],
                }
            ],
        )
        self.assertNotIn("sacl_ace", sacl_record)

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
