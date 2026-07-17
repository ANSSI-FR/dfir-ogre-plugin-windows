import re
from typing import List

from dfir_ogre_common import Record, Value

from dfir_ogre_plugin_windows.common import normalize_guid

ACE_TYPE = {
    "A": "ACCESS_ALLOWED_ACE_TYPE",
    "D": "ACCESS_DENIED_ACE_TYPE",
    "OA": "ACCESS_ALLOWED_OBJECT_ACE_TYPE",
    "OD": "ACCESS_DENIED_OBJECT_ACE_TYPE",
    "AU": "SYSTEM_AUDIT_ACE_TYPE",
    "AL": "SYSTEM_ALARM_ACE_TYPE",
    "OU": "SYSTEM_AUDIT_OBJECT_ACE_TYPE",
    "OL": "SYSTEM_ALARM_OBJECT_ACE_TYPE",
    "ML": "SYSTEM_MANDATORY_LABEL_ACE_TYPE",
    "XA": "ACCESS_ALLOWED_CALLBACK_ACE_TYPE",
    "XD": "ACCESS_DENIED_CALLBACK_ACE_TYPE",
    "RA": "SYSTEM_RESOURCE_ATTRIBUTE_ACE_TYPE",
    "SP": "SYSTEM_SCOPED_POLICY_ID_ACE_TYPE",
    "XU": "SYSTEM_AUDIT_CALLBACK_ACE_TYPE",
    "ZA": "ACCESS_ALLOWED_CALLBACK_ACE_TYPE",
    "TL": "SYSTEM_PROCESS_TRUST_LABEL_ACE_TYPE",
    "FL": "SYSTEM_ACCESS_FILTER_ACE_TYPE",
}

ACE_BTYPE = {
    0x00: "ACCESS_ALLOWED_ACE_TYPE",
    0x01: "ACCESS_DENIED_ACE_TYPE",
    0x02: "SYSTEM_AUDIT_ACE_TYPE",
    0x03: "SYSTEM_ALARM_ACE_TYPE",
    0x04: "ACCESS_ALLOWED_COMPOUND_ACE_TYPE",
    0x05: "ACCESS_ALLOWED_OBJECT_ACE_TYPE",
    0x06: "ACCESS_DENIED_OBJECT_ACE_TYPE",
    0x07: "SYSTEM_AUDIT_OBJECT_ACE_TYPE",
    0x08: "SYSTEM_ALARM_OBJECT_ACE_TYPE",
    0x09: "ACCESS_ALLOWED_CALLBACK_ACE_TYPE",
    0x0A: "ACCESS_DENIED_CALLBACK_ACE_TYPE",
    0x0B: "ACCESS_ALLOWED_CALLBACK_OBJECT_ACE_TYPE",
    0x0C: "ACCESS_DENIED_CALLBACK_OBJECT_ACE_TYPE",
    0x0D: "SYSTEM_AUDIT_CALLBACK_ACE_TYPE",
    0x0E: "SYSTEM_ALARM_CALLBACK_ACE_TYPE",
    0x0F: "SYSTEM_AUDIT_CALLBACK_OBJECT_ACE_TYPE",
    0x10: "SYSTEM_ALARM_CALLBACK_OBJECT_ACE_TYPE",
    0x11: "SYSTEM_MANDATORY_LABEL_ACE_TYPE",
}

ACE_FLAGS = {
    "CI": "CONTAINER_INHERIT_ACE",
    "OI": "OBJECT_INHERIT_ACE",
    "NP": "NO_PROPAGATE_INHERIT_ACE",
    "IO": "INHERIT_ONLY_ACE",
    "ID": "INHERITED_ACE",
    "SA": "SUCCESSFUL_ACCESS_ACE_FLAG",
    "FA": "FAILED_ACCESS_ACE_FLAG",
    "TP": "TRUST_PROTECTED_FILTER_ACE_FLAG",
    "CR": "CRITICAL_ACE_FLAG",
}

ACE_BFLAGS = {
    0x01: "OBJECT_INHERIT_ACE",
    0x02: "CONTAINER_INHERIT_ACE",
    0x04: "NO_PROPAGATE_INHERIT_ACE",
    0x08: "INHERIT_ONLY_ACE",
    0x40: "SUCCESSFUL_ACCESS_ACE_FLAG",
    0x80: "FAILED_ACCESS_ACE_FLAG",
}

RIGHTS = {
    "GA": "GENERIC_ALL",
    "GR": "GENERIC_READ",
    "GW": "GENERIC_WRITE",
    "GX": "GENERIC_EXECUTE",
    "RC": "READ_CONTROL",
    "SD": "DELETE",
    "WD": "WRITE_DAC",
    "WO": "WRITE_OWNER",
    "RP": "ADS_RIGHT_DS_READ_PROP",
    "WP": "ADS_RIGHT_DS_WRITE_PROP",
    "CC": "ADS_RIGHT_DS_CREATE_CHILD",
    "DC": "ADS_RIGHT_DS_DELETE_CHILD",
    "LC": "ADS_RIGHT_ACTRL_DS_LIST",
    "SW": "ADS_RIGHT_DS_SELF",
    "LO": "ADS_RIGHT_DS_LIST_OBJECT",
    "DT": "ADS_RIGHT_DS_DELETE_TREE",
    "CR": "ADS_RIGHT_DS_CONTROL_ACCESS",
    "FA": "FILE_GENERIC_ALL",
    "FR": "FILE_GENERIC_READ",
    "FW": "FILE_GENERIC_WRITE",
    "FX": "FILE_GENERIC_EXECUTE",
    "KA": "KEY_ALL_ACCESS",
    "KR": "KEY_READ",
    "KW": "KEY_WRITE",
    "KX": "KEY_EXECUTE",
    "NR": "SYSTEM_MANDATORY_LABEL_NO_READ_UP",
    "NW": "SYSTEM_MANDATORY_LABEL_NO_WRITE_UP",
    "NX": "SYSTEM_MANDATORY_LABEL_NO_EXECUTE_UP",
}

BRIGHTS = {
    0x000F003F: "KEY_ALL_ACCESS",
    0x00000020: "KEY_CREATE_LINK",
    0x00000004: "KEY_CREATE_SUB_KEY",
    0x00000008: "KEY_ENUMERATE_SUB_KEYS",
    0x00000010: "KEY_NOTIFY",
    0x00000001: "KEY_QUERY_VALUE",
    0x00020019: "KEY_READ",
    0x00000002: "KEY_SET_VALUE",
    0x00000200: "KEY_WOW64_32KEY",
    0x00000100: "KEY_WOW64_64KEY",
    0x00020006: "KEY_WRITE",
    0x01000000: "ACCESS_SYSTEM_SECURITY",
    0x02000000: "MAXIMUM_ALLOWED",
    0x10000000: "GENERIC_ALL",
    0x20000000: "GENERIC_EXECUTE",
    0x40000000: "GENERIC_WRITE",
    0x80000000: "GENERIC_READ",
}

SID_STRING = {
    "AA": "DOMAIN_ALIAS_RID_ACCESS_CONTROL_ASSISTANCE_OPS",
    "AC": "SECURITY_BUILTIN_PACKAGE_ANY_PACKAGE",
    "AN": "SECURITY_ANONYMOUS_LOGON_RID",
    "AO": "DOMAIN_ALIAS_RID_ACCOUNT_OPS",
    "AP": "DOMAIN_GROUP_RID_PROTECTED_USERS",
    "AU": "SECURITY_AUTHENTICATED_USER_RID",
    "BA": "DOMAIN_ALIAS_RID_ADMINS",
    "BG": "DOMAIN_ALIAS_RID_GUESTS",
    "BO": "DOMAIN_ALIAS_RID_BACKUP_OPS",
    "BU": "DOMAIN_ALIAS_RID_USERS",
    "CA": "DOMAIN_GROUP_RID_CERT_ADMINS",
    "CD": "DOMAIN_ALIAS_RID_CERTSVC_DCOM_ACCESS_GROUP",
    "CG": "SECURITY_CREATOR_GROUP_RID",
    "CN": "DOMAIN_GROUP_RID_CLONEABLE_CONTROLLERS",
    "CO": "SECURITY_CREATOR_OWNER_RID",
    "CY": "DOMAIN_ALIAS_RID_CRYPTO_OPERATORS",
    "DA": "DOMAIN_GROUP_RID_ADMINS",
    "DC": "DOMAIN_GROUP_RID_COMPUTERS",
    "DD": "DOMAIN_GROUP_RID_CONTROLLERS",
    "DG": "DOMAIN_GROUP_RID_GUESTS",
    "DU": "DOMAIN_GROUP_RID_USERS",
    "EA": "DOMAIN_GROUP_RID_ENTERPRISE_ADMINS",
    "ED": "SECURITY_SERVER_LOGON_RID",
    "EK": "DOMAIN_GROUP_RID_ENTERPRISE_KEY_ADMINS",
    "ER": "DOMAIN_ALIAS_RID_EVENT_LOG_READERS_GROUP",
    "ES": "DOMAIN_ALIAS_RID_RDS_ENDPOINT_SERVERS",
    "HA": "DOMAIN_ALIAS_RID_HYPER_V_ADMINS",
    "HI": "SECURITY_MANDATORY_HIGH_RID",
    "IS": "DOMAIN_ALIAS_RID_IUSERS",
    "IU": "SECURITY_INTERACTIVE_RID",
    "KA": "DOMAIN_GROUP_RID_KEY_ADMINS",
    "LA": "DOMAIN_USER_RID_ADMIN",
    "LG": "DOMAIN_USER_RID_GUEST",
    "LS": "SECURITY_LOCAL_SERVICE_RID",
    "LU": "DOMAIN_ALIAS_RID_LOGGING_USERS",
    "LW": "SECURITY_MANDATORY_LOW_RID",
    "ME": "SECURITY_MANDATORY_MEDIUM_RID",
    "MP": "SECURITY_MANDATORY_MEDIUM_PLUS_RID",
    "MU": "DOMAIN_ALIAS_RID_MONITORING_USERS",
    "NO": "DOMAIN_ALIAS_RID_NETWORK_CONFIGURATION_OPS",
    "NS": "SECURITY_NETWORK_SERVICE_RID",
    "NU": "SECURITY_NETWORK_RID",
    "OW": "SECURITY_CREATOR_OWNER_RIGHTS_RID",
    "PA": "DOMAIN_GROUP_RID_POLICY_ADMINS",
    "PO": "DOMAIN_ALIAS_RID_PRINT_OPS",
    "PS": "SECURITY_PRINCIPAL_SELF_RID",
    "PU": "DOMAIN_ALIAS_RID_POWER_USERS",
    "RA": "DOMAIN_ALIAS_RID_RDS_REMOTE_ACCESS_SERVERS",
    "RC": "SECURITY_RESTRICTED_CODE_RID",
    "RD": "DOMAIN_ALIAS_RID_REMOTE_DESKTOP_USERS",
    "RE": "DOMAIN_ALIAS_RID_REPLICATOR",
    "RM": "SDDL_RMS__SERVICE_OPERATORS",
    "RO": "DOMAIN_GROUP_RID_ENTERPRISE_READONLY_DOMAIN_CONTROLLERS",
    "RS": "DOMAIN_ALIAS_RID_RAS_SERVERS",
    "RU": "DOMAIN_ALIAS_RID_PREW2KCOMPACCESS",
    "SA": "DOMAIN_GROUP_RID_SCHEMA_ADMINS",
    "SI": "SECURITY_MANDATORY_SYSTEM_RID",
    "SO": "DOMAIN_ALIAS_RID_SYSTEM_OPS",
    "SS": "SECURITY_AUTHENTICATION_SERVICE_ASSERTED_RID",
    "SU": "SECURITY_SERVICE_RID",
    "SY": "SECURITY_LOCAL_SYSTEM_RID",
    "UD": "SECURITY_USERMODEDRIVERHOST_ID_BASE_RID",
    "WD": "SECURITY_WORLD_RID",
    "WR": "SECURITY_WRITE_RESTRICTED_CODE_RID",
}

DACL_FLAGS = {
    "P": "SDDL_PROTECTED",
    "AR": "SDDL_AUTO_INHERIT_REQ",
    "AI": "SDDL_AUTO_INHERITED",
    "NO_ACCESS_CONTROL": "SDDL_NULL_ACL",
}

SD_BFLAGS = {
    0x0001: "SE_OWNER_DEFAULTED",
    0x0002: "SE_GROUP_DEFAULTED",
    0x0004: "SE_DACL_PRESENT",
    0x0008: "SE_DACL_DEFAULTED",
    0x0010: "SE_SACL_PRESENT",
    0x0020: "SE_SACL_DEFAULTED",
    0x0100: "SE_DACL_AUTO_INHERIT_REQ",
    0x0200: "SE_SACL_AUTO_INHERIT_REQ",
    0x0400: "SE_DACL_AUTO_INHERITED",
    0x0800: "SE_SACL_AUTO_INHERITED",
    0x1000: "SE_DACL_PROTECTED",
    0x2000: "SE_SACL_PROTECTED",
    0x4000: "SE_RM_CONTROL_VALID",
    0x8000: "SE_SELF_RELATIVE",
}


class ACE:
    """ACE"""

    ace_type: str | None = None
    ace_flags: List[str | None] = []
    rights: List[str | None] = []
    object_guid: str | None = None
    inherit_object_guid: str | None = None
    account_sid: str | None = None
    resource_attribute: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.ace_flags = []
        self.rights = []

    def from_string(self, ace_str: str):
        if ace_str.startswith("("):
            ace_str = ace_str[1:-1]
        # ace_type;ace_flags;rights;object_guid;inherit_object_guid;account_sid;(resource_attribute)
        ace = ace_str.split(";")
        self.ace_type = ACE_TYPE.get(ace[0], ace[0])
        self.ace_flags = []
        for i in range(0, len(ace[1]) // 2):
            self.ace_flags.append(
                ACE_FLAGS.get(ace[1][i * 2 : i * 2 + 2], ace[1][i * 2 : i * 2 + 2])
            )
        self.rights = []
        for i in range(0, len(ace[2]) // 2):
            self.rights.append(
                RIGHTS.get(ace[2][i * 2 : i * 2 + 2], ace[2][i * 2 : i * 2 + 2])
            )
        self.object_guid = ace[3]
        self.inherit_object_guid = ace[4]
        self.account_sid = SID_STRING.get(ace[5], ace[5])

    def to_record(self) -> Record:
        record = Record()
        if self.ace_type:
            record.add("ace_type", Value.String(self.ace_type))

        if self.object_guid:
            record.add("object_guid", Value.String(normalize_guid(self.object_guid)))

        if self.inherit_object_guid:
            record.add(
                "inherit_object_guid",
                Value.String(normalize_guid(self.inherit_object_guid)),
            )

        if self.account_sid:
            record.add("account_sid", Value.String(self.account_sid))

        if self.resource_attribute:
            record.add("account_sid", Value.String(self.resource_attribute))

        right_list = []
        for right in self.ace_flags:
            if right:
                right_list.append(Value.String(right))

        if right_list:
            record.add("ace_flags", Value.Array(right_list))

        right_list = []
        for right in self.rights:
            if right:
                right_list.append(Value.String(right))

        if right_list:
            record.add("rights", Value.Array(right_list))

        return record


class SecurityDescriptor:
    """Security Descriptor"""

    owner_sid: str | None = None
    group_sid: str | None = None
    dacl_flags: str | None = None
    control_flags: List[str | None] = []
    dacl_aces: List[ACE | None]
    sacl_flags: str | None = None
    sacl_aces: List[ACE | None] = []

    def from_string(self, sd_string):
        self.dacl_aces = []
        self.sacl_aces = []

        sd_pattern = re.compile(
            r"(O:(?P<osid>[\w-]+?))?(G:(?P<gsid>.+?))?(D:(?P<dacl_flags>[\w_]+?)?(?P<dacl>\(.+\)?))?(S:(?P<sacl_flags>[\w_]+?)?(?P<sacl>\(.+\)?))?$"
        )
        match = sd_pattern.match(sd_string)
        if match:
            self.owner_sid = match.group("osid")
            self.group_sid = match.group("gsid")
            self.dacl_flags = DACL_FLAGS.get(
                match.group("dacl_flags"), match.group("dacl_flags")
            )
            dacl = match.group("dacl")
            if dacl:
                for ace in list(filter(None, re.split(r"[(|)]", dacl))):
                    ace_obj = ACE()
                    ace_obj.from_string(ace)
                    self.dacl_aces.append(ace_obj)

            self.sacl_flags = match.group("sacl_flags")
            sacl = match.group("sacl")
            if sacl:
                for ace in list(filter(None, re.split(r"[(|)]", sacl))):
                    ace_obj = ACE()
                    ace_obj.from_string(ace)
                    self.sacl_aces.append(ace_obj)

    def to_record(self) -> Record:
        record = Record()
        if self.owner_sid:
            record.add("owner_sid", Value.String(self.owner_sid))

        if self.group_sid:
            record.add("group_sid", Value.String(self.group_sid))

        if self.dacl_flags:
            record.add("dacl_flags", Value.String(self.dacl_flags))

        if self.sacl_flags:
            record.add("sacl_flags", Value.String(self.sacl_flags))

        ace_list = []
        for dacl_ace in self.dacl_aces:
            if dacl_ace:
                ace_list.append(Value.Object(dacl_ace.to_record()))
        if ace_list:
            record.add("dacl_aces", Value.Array(ace_list))

        ace_list = []
        for sacl_ace in self.sacl_aces:
            if sacl_ace:
                ace_list.append(Value.Object(sacl_ace.to_record()))
        if ace_list:
            record.add("sacl_aces", Value.Array(ace_list))

        return record
