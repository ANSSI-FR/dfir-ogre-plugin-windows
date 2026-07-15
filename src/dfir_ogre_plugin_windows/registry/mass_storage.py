import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from dfir_ogre_common import (
    Metadata,
    OgrePlugin,
    Output,
    PluginConfiguration,
    PluginDescription,
    Record,
    Registry,
    RegKey,
    RunConfiguration,
    RunReport,
    Value,
)

from dfir_ogre_plugin_windows.common import filetime_to_utc, value

logger = logging.getLogger(__name__)


GUID_DEVINTERFACE_DISK = "{53f56307-b6bf-11d0-94f2-00a0c91efb8b}"
GUID_DEVINTERFACE_VOLUME = "{53f5630d-b6bf-11d0-94f2-00a0c91efb8b}"
GUID_PROPERTIES_TIME = "{83da6326-97a6-4088-9453-a1923f573b29}"
# DEVPROPKEY_Device activity property IDs 0x64 through 0x67. Both registry
# layouts use the same IDs with different zero-padding.
_USBSTOR_DATE_PROPERTIES = {
    "0064": "usbstor_install",
    "0065": "usbstor_first_install",
    "0066": "usbstor_last_arrival",
    "0067": "usbstor_last_removal",
    "00000064": "usbstor_install",
    "00000065": "usbstor_first_install",
    "00000066": "usbstor_last_arrival",
    "00000067": "usbstor_last_removal",
}
_SAMPLE_TYPE_SYS_HIVE = 0
_SAMPLE_TYPE_SETUPAPI = 1


class RegMassStorageSystem(OgrePlugin):
    def description(self) -> PluginDescription:
        return PluginDescription(
            "RegMassStorageSystem",
            "List every mass storage devices (USB keys, ...) ever connected, using the System hive",
        )

    def parse(
        self,
        input_file: str,
        plugin_file: str,
        run_config: RunConfiguration,
        metadata: Metadata,
    ) -> RunReport:
        plugin_config = PluginConfiguration.load(plugin_file)
        report = RunReport()
        try:
            reg = Registry.load(input_file, "\\HKLM\\SYSTEM")
        except Exception as e:
            report.add_error(f"{e}")
            return report

        device_dict = DeviceDictionary()

        with Output(run_config, plugin_config, metadata) as output:
            # Start with the USBSTOR key since this it provides the most information
            self.parse_usb_storage(reg, device_dict, report)
            self.parse_device_classes(reg, device_dict, report)
            self.parse_usb(reg, device_dict, report)
            self.parse_mounted_devices(reg, device_dict, report)
            # write all devices
            for list in device_dict.devices.values():
                for device in list:
                    try:
                        output.write(device.to_record())
                    except Exception as e:
                        report.add_error(f"{e}")

            report.add_output_report(output.get_report())

        return report

    def parse_usb_storage(
        self, reg: Registry, device_dict: "DeviceDictionary", report: RunReport
    ):
        try:
            keys = reg.glob_keys("\\HKLM\\SYSTEM\\*ControlSet*\\Enum\\USBSTOR\\*")

            for key in keys:
                try:
                    self.parse_usb_storage_key(key, device_dict, report)
                except Exception as e:
                    report.add_error(f"{e}")

        except Exception as e:
            report.add_error(f"{e}")

    def parse_usb_storage_key(
        self, key: RegKey, device_dict: "DeviceDictionary", report: RunReport
    ):
        controlset = control_set(key.path)
        match = REGEX_CLASS_ID.match(key.name)
        if not match:
            raise Exception(f"Invalid ClassId {key.name}")

        for instance in key.sub_keys():
            try:
                device = UsbDevice(controlset)
                device.class_id = match.group("classid")
                device.type = match.group("type")
                device.vendor = match.group("vendor")
                device.product = match.group("product")
                device.revision = match.group("revision")
                device.silo = match.group("silo")

                instance_id_res = REGEX_INSTANCE_ID.match(instance.name)
                if instance_id_res:
                    device.instance_id = instance_id_res.group("id")
                    if not device.instance_id:
                        raise Exception(f"Invalid InstanceId {instance.name}")

                device.usbstor_last_modified = instance.mtime

                device.parent_id = instance.value_data("ParentIdPrefix")

                friendly_name = instance.value_data("FriendlyName")
                if friendly_name:
                    device.friendly_names.append(friendly_name)

                device.registry_path.append(instance.path)
                device.users.append(instance.security_descriptor.owner_sid)

                for sub_key in instance.sub_glob(
                    f"Properties\\{GUID_PROPERTIES_TIME}\\*"
                ):
                    field_name = _USBSTOR_DATE_PROPERTIES.get(sub_key.name)
                    if not field_name:
                        continue

                    # Windows Vista/7 store timestamps in a 'Data' value under
                    # the property key's '00000000' subkey.
                    if len(sub_key.name) == 8:
                        date_key = sub_key.sub_key("00000000")
                        date = date_key.value_data("data") if date_key else None
                    # Windows 8+ store timestamps in the property key's
                    # default value.
                    else:
                        date = sub_key.value_data("(default)")

                    if date:
                        filetime = int.from_bytes(date, byteorder="little")
                        setattr(device, field_name, filetime_to_utc(filetime))

                device_dict.add(device)
            except Exception as e:
                report.add_error(f"{e}")

    def parse_device_classes(
        self, reg: Registry, device_dict: "DeviceDictionary", report: RunReport
    ):
        base_class = "\\HKLM\\SYSTEM\\*ControlSet*\\Control\\DeviceClasses\\"

        key_paths = []
        key_paths.append(f"{base_class}{GUID_DEVINTERFACE_DISK}\\*")
        key_paths.append(f"{base_class}{GUID_DEVINTERFACE_VOLUME}\\*")

        for key_path in key_paths:
            try:
                keys = reg.glob_keys(key_path)

                for key in keys:
                    try:
                        self.parse_device_classes_key(key, device_dict, report)
                    except Exception as e:
                        report.add_error(f"{e}")

            except Exception as e:
                report.add_error(f"{e}")
        ...

    def parse_device_classes_key(
        self, key: RegKey, device_dict: "DeviceDictionary", report: RunReport
    ):
        controlset = control_set(key.path)
        if "USBSTOR" in key.name.upper():
            match = REGEX_DEVICE_CLASSES_USBSTOR.match(key.name)
            if not match:
                raise Exception(f"Invalid DeviceClasses key name {key.name}")
            device = UsbDevice(controlset)
            device.device_classes_last_modified = key.mtime
            device.driver = match.group("driver")
            device.class_id = match.group("classid")
            device.type = match.group("type")
            device.vendor = match.group("vendor")
            device.product = match.group("product")
            device.revision = match.group("revision")
            device.silo = match.group("silo")
            device.instance_id = match.group("id")
            device.registry_path.append(key.path)
            device.users.append(key.security_descriptor.owner_sid)

            device_dict.add(device)
        elif "REMOVABLEMEDIA" in key.name.upper():
            matched = REGEX_NT5_DEVICE.search(key.name)
            if matched:
                device = UsbDevice(controlset)
                device.parent_id = matched.group("parentid")
                device.device_classes_last_modified = key.mtime
                device.registry_path.append(key.path)
                device.users.append(key.security_descriptor.owner_sid)
                found = False
                if device.parent_id:
                    for existing in device_dict.devices.get(controlset, []):
                        if existing.parent_id == device.parent_id:
                            existing.merge(device)
                            found = True
                            break
                if not found:
                    device_dict.add(device)

    def parse_usb(
        self, reg: Registry, device_dict: "DeviceDictionary", report: RunReport
    ):
        try:
            keys = reg.glob_keys("\\HKLM\\SYSTEM\\*ControlSet*\\Enum\\USB\\VID*")

            for key in keys:
                try:
                    self.parse_usb_key(key, device_dict, report)
                except Exception as e:
                    report.add_error(f"{e}")

        except Exception as e:
            report.add_error(f"{e}")

    def parse_usb_key(
        self, key: RegKey, device_dict: "DeviceDictionary", report: RunReport
    ):
        controlset = control_set(key.path)
        hardware_id = key.name
        for instance in key.sub_keys():
            service = instance.value_data("Service")
            if service in (
                "DISK",
                "USBSTOR",
                "USTOR2K",
            ):
                device = UsbDevice(controlset)
                device.registry_path.append(key.path)
                device.users.append(key.security_descriptor.owner_sid)
                device.usb_last_modified = instance.mtime
                matched = REGEX_INSTANCE_ID.match(instance.name)
                if matched:
                    device.instance_id = matched.group("id")

                hardware_id_array = instance.value_data("HardwareID")
                parsed = False

                if (
                    hardware_id_array
                    and isinstance(hardware_id_array, list)
                    and len(hardware_id_array) > 0
                ):
                    hardware_id = hardware_id_array[0]
                    reg_result = REGEX_HARDWARE_ID.match(hardware_id)
                    if reg_result:
                        vendorid, productid, revision = reg_result.groups()
                        device.vendor_id = vendorid
                        device.product_id = productid
                        device.revision = revision
                        parsed = True

                # fallback to parsing the parent key name
                if not parsed:
                    reg_result = REGEX_HARDWARE_ID.match(hardware_id)
                    if reg_result:
                        vendorid, productid, revision = reg_result.groups()
                        device.vendor_id = vendorid
                        device.product_id = productid
                        device.revision = revision

                merged = False

                for existing in device_dict.devices.get(controlset, []):
                    instanceid = existing.instance_id
                    if instanceid is not None:
                        instanceid = instanceid.split("&")[0]

                    if instanceid == device.instance_id:
                        existing.merge(device)
                        merged = True
                        # Most of the time, due to the weak way of comparing instanceid between
                        # ENUM\\USB and ENUM\\USBSTOR, there will be several legitimate matches to
                        # update, hence not breaking after the first match. However, there are some
                        # rare cases where an instanceid is shared between different devices on the same
                        # host. Unfortunately, in this case there is no known way to know which
                        # ENUM\\USB subkey corresponds to each one. So in this specific case, the
                        # pieces of information coming from the ENUM\\USB subkey will be right for one
                        # device only.

                if not merged:
                    device_dict.add(device)

    def parse_mounted_devices(
        self, reg: Registry, device_dict: "DeviceDictionary", report: RunReport
    ):
        try:
            keys = reg.glob_keys("\\HKLM\\SYSTEM\\MountedDevices")

            for key in keys:
                try:
                    self.parse_mounted_devices_key(key, device_dict, report)
                except Exception as e:
                    report.add_error(f"{e}")

        except Exception as e:
            report.add_error(f"{e}")

    def parse_mounted_devices_key(
        self, key: RegKey, device_dict: "DeviceDictionary", report: RunReport
    ):
        for val in key.values():
            try:
                device = UsbDevice(None)
                matched = REGEX_VOLUME_PATH.match(val.name())
                if not matched:
                    raise Exception(f"invalid value name {val.name()}")

                guid, volume_letter = matched.groups()
                device.volume_letter = volume_letter
                device.volume_guid = guid
                device.registry_path.append(key.path)
                device.users.append(key.security_descriptor.owner_sid)
                device.usbstor_last_modified = key.mtime

                str_val = try_decode_data(val.data())
                if not str_val:
                    return

                if "USBSTOR" in str_val:
                    matched = REGEX_DEVICE_CLASSES_USBSTOR.match(str_val)
                    if not matched:
                        raise Exception(f"invalid data for NT6 value {str_val}")

                    device.driver = matched.group("driver")
                    device.class_id = matched.group("classid").replace("#", "/")
                    device.type = matched.group("type")
                    device.vendor = matched.group("vendor").replace("#", "/")
                    device.product = matched.group("product").replace("#", "/")
                    device.revision = matched.group("revision")
                    device.silo = matched.group("silo")
                    device.instance_id = matched.group("id")

                    # MountedDevices is not bound to a specific Control Set: the pieces of information it holds will
                    # therefore update every matching devices across all Control Sets
                    found = False
                    for device_list in device_dict.devices.values():
                        for existing in device_list:
                            if existing == device:
                                existing.merge(device)
                                found = True
                    if not found:
                        device_dict.add(device)

                elif "STORAGE" in str_val:
                    matched = REGEX_NT5_DEVICE.search(str_val)
                    found = False
                    if matched:
                        device.parent_id = matched.group("parentid")
                    for device_list in device_dict.devices.values():
                        for existing in device_list:
                            if (
                                device.parent_id
                                and existing.parent_id == device.parent_id
                            ):
                                existing.merge(device)
                                found = True
                    if not found:
                        device_dict.add(device)

            except Exception as e:
                report.add_error(f"{e}")


def control_set(path: str) -> str | None:
    pathes = path.split("\\")
    for p in pathes:
        if "controlset" in p.lower():
            return p
    return None


def try_decode_data(data):
    if not data:
        return
    try:
        str_val = data.decode("utf-16le")
        return str_val
    except Exception:
        ...

    try:
        str_val = data.decode("utf-8")
        return str_val
    except Exception:
        ...

    return str(data)


class DeviceDictionary:
    devices: Dict[str | None, List["UsbDevice"]]

    def __init__(self):
        self.devices = {}

    def add(self, device: "UsbDevice"):
        existing_list = self.devices.get(device.controlset, [])
        merged = False
        for existing in existing_list:
            if existing == device:
                existing.merge(device)
                merged = True
                break
        if not merged:
            existing_list.append(device)

        self.devices[device.controlset] = existing_list


class UsbDevice:
    class_id: Optional[str]
    instance_id: Optional[str]
    controlset: Optional[str]
    parent_id: Optional[str]
    volume_guid: Optional[str]
    driver: Optional[str]
    type: Optional[str]
    vendor: Optional[str]
    product: Optional[str]
    revision: Optional[str]
    silo: Optional[str]
    vendor_id: Optional[str]
    product_id: Optional[str]
    volume_letter: Optional[str]
    volume_label: Optional[str]
    volume_sn: Optional[str]
    capacity: Optional[str]
    attributes1: Optional[str]
    attributes2: Optional[str]
    attributes3: Optional[str]
    reason: Optional[str]
    setupapi_first_seen: Optional[str]
    setupapi_last_seen: Optional[str]
    usbstor_last_modified: Optional[datetime]
    device_classes_last_modified: Optional[datetime]
    usb_last_modified: Optional[datetime]
    emdmgmt_last_modified: Optional[datetime]
    usbstor_first_install: Optional[datetime]
    usbstor_install: Optional[datetime]
    usbstor_last_arrival: Optional[datetime]
    usbstor_last_removal: Optional[datetime]
    registry_path: List[str]
    friendly_names: List[str]
    users: List[str]

    def __init__(self, controlset: str | None):
        self.controlset = controlset
        self.class_id = None
        self.instance_id = None
        self.parent_id = None
        self.volume_guid = None
        self.driver = None
        self.type = None
        self.vendor = None
        self.product = None
        self.revision = None
        self.silo = None
        self.vendor_id = None
        self.product_id = None
        self.volume_letter = None
        self.volume_label = None
        self.volume_sn = None
        self.capacity = None
        self.attributes1 = None
        self.attributes2 = None
        self.attributes3 = None
        self.reason = None
        self.setupapi_first_seen = None
        self.setupapi_last_seen = None
        self.usbstor_last_modified = None
        self.device_classes_last_modified = None
        self.usb_last_modified = None
        self.emdmgmt_last_modified = None
        self.usbstor_first_install = None
        self.usbstor_install = None
        self.usbstor_last_arrival = None
        self.usbstor_last_removal = None
        self.registry_path = []
        self.friendly_names = []
        self.users = []

    def __str__(self):
        return str(self.__dict__)

    def __eq__(self, other):
        if not isinstance(other, UsbDevice):
            return False
        try:
            if self.class_id is not None and self.instance_id is not None:
                other_class_id = None
                if other.class_id:
                    other_class_id = other.class_id.upper()
                other_instance_id = None
                if other.instance_id:
                    other_instance_id = other.instance_id.upper()
                return (
                    self.class_id.upper() == other_class_id
                    and self.instance_id.upper() == other_instance_id
                )
            elif (
                self.vendor_id is not None
                and self.product_id is not None
                and self.instance_id is not None
            ):
                return (
                    self.vendor_id.upper() == getattr(other, "vendor_id", "").upper()
                    and self.product_id.upper()
                    == getattr(other, "product_id", "").upper()
                    and self.instance_id.upper()
                    == getattr(other, "instance_id", "").upper()
                    and (
                        self.revision is None
                        and other.revision is None
                        or self.revision == other.revision
                    )
                )
            else:
                logger.debug(
                    "Weak comparison is being performed due to insufficient discriminating info: %s",
                    str(self),
                )
                return False
        except AttributeError:
            return False

    def merge(self, other: "UsbDevice"):
        """
            This method merges two instances. It does so by updating every null values of the calling instance with
            non-null values of the one passed as argument.
            The list of users and friendly names of the two instances are also merged even if the calling instance's
            one is not null

        Args:
            other: UsbDevice instance

        Returns: nothing

        """

        if sorted(self.users) != sorted(other.users):
            self.users += other.users

        if sorted(self.friendly_names) != sorted(other.friendly_names):
            self.friendly_names += other.friendly_names

        if sorted(self.registry_path) != sorted(other.registry_path):
            self.registry_path += other.registry_path

        for k, v in other.__dict__.items():
            if (
                v is not None
                and getattr(self, k, None) is None
                and k
                not in [
                    "_logger",
                ]
            ):
                logger.debug("Need to update null %s with value %s", k, v)
                setattr(self, k, v)

    def to_record(self) -> Record:
        tup = Record()
        tup.add("class_id", value(self.class_id))
        tup.add("instance_id", value(self.instance_id))
        tup.add("controlset", value(self.controlset))
        tup.add("parent_id", value(self.parent_id))
        tup.add("volume_guid", value(self.volume_guid))
        tup.add("driver", value(self.driver))
        tup.add("type", value(self.type))
        tup.add("vendor", value(self.vendor))
        tup.add("product", value(self.product))
        tup.add("revision", value(self.revision))
        tup.add("silo", value(self.silo))
        tup.add("vendor_id", value(self.vendor_id))
        tup.add("product_id", value(self.product_id))
        tup.add("volume_letter", value(self.volume_letter))
        tup.add("volume_label", value(self.volume_label))
        tup.add("volume_sn", value(self.volume_sn))
        tup.add("capacity", value(self.capacity))
        tup.add("attributes1", value(self.attributes1))
        tup.add("attributes2", value(self.attributes2))
        tup.add("attributes3", value(self.attributes3))
        tup.add("reason", value(self.reason))
        tup.add("setupapi_first_seen", value(self.setupapi_first_seen))
        tup.add("setupapi_last_seen", value(self.setupapi_last_seen))
        tup.add("usbstor_last_modified", value(self.usbstor_last_modified))
        tup.add(
            "device_classes_last_modified", value(self.device_classes_last_modified)
        )
        tup.add("usb_last_modified", value(self.usb_last_modified))
        tup.add("emdmgmt_last_modified", value(self.emdmgmt_last_modified))
        tup.add("usbstor_first_install", value(self.usbstor_first_install))
        tup.add("usbstor_install", value(self.usbstor_install))
        tup.add("usbstor_last_arrival", value(self.usbstor_last_arrival))
        tup.add("usbstor_last_removal", value(self.usbstor_last_removal))

        registry_path = []
        for v in self.registry_path:
            registry_path.append(value(v))
        tup.add("registry_path", Value.Array(registry_path))

        friendly_names = []
        for v in self.friendly_names:
            friendly_names.append(value(v))
        tup.add("friendly_names", Value.Array(friendly_names))

        users = []
        for v in self.users:
            users.append(value(v))
        tup.add("users", Value.Array(users))

        return tup

# _??_USBSTOR#Disk&Ven_&Prod_USB_DISK_2.0&Rev_PMAP#0710C21515CF8EF8&0#{53f56307-b6bf-11d0-94f2-00a0c91efb8b}
# ##?#STORAGE#Volume#_??_USBSTOR#Disk&Ven_JetFlash&Prod_Transcend_16GB&Rev_1100#23NPMBDVM3GMSLXI&0#{53f56307-b6bf-11d0-94f2-00a0c91efb8b}#{53f5630d-b6bf-11d0-94f2-00a0c91efb8b}
PATTERN_CLASS = r"(?P<classid>(?P<type>.*)&Ven_(?P<vendor>.*)&Prod_(?P<product>.*)(?:&Rev_(?P<revision>.*))?(?:&Silo_(?P<silo>.*))?)"
PATTERN_CLASS = r"(?P<classid>(?P<type>[^&#]+)&Ven_(?P<vendor>[^&]*)&Prod_(?P<product>[^&#]+)(?:&Rev_(?P<revision>[^&#]+))?(?:&Silo_(?P<silo>[^&#]+))?)"
PATTERN_HW = r"(?:USB\\)?VID_(?P<vid>.*?)&PID_(?P<pid>(?:[^&]|&(?!(?:REV_)|(?:MI_)))*)(?:(?:&REV_(?P<rev>.{,4}))|(?:&MI_.{,2}))?"
PATTERN_INSTANCE = r"(?P<id>[^#]+)"
PATTERN_FULL = (
    r"^(?P<driver>.*)USBSTOR#"
    + PATTERN_CLASS
    + r"#"
    + PATTERN_INSTANCE
    + r"#(?:(?:"
    + GUID_DEVINTERFACE_DISK
    + r")|(?:"
    + GUID_DEVINTERFACE_VOLUME
    + r"))"
)
REGEX_CLASS_ID = re.compile(r"^" + PATTERN_CLASS + "$", re.IGNORECASE)
REGEX_INSTANCE_ID = re.compile(r"^" + PATTERN_INSTANCE + r"$", re.IGNORECASE)
REGEX_EMD_KEY = re.compile(
    r"^" + PATTERN_FULL + r"(?P<label>.*)_(?P<vsn>\d+)", re.IGNORECASE
)
REGEX_DEVICE_CLASSES_USBSTOR = re.compile(
    r"^(?P<driver>.*)USBSTOR#" + PATTERN_CLASS + "#" + PATTERN_INSTANCE, re.IGNORECASE
)
REGEX_NT5_DEVICE = re.compile(
    r"#RemovableMedia#(?P<parentid>.+)&RM#" + GUID_DEVINTERFACE_VOLUME,
    re.IGNORECASE,
)
REGEX_HARDWARE_ID = re.compile(r"^" + PATTERN_HW + r"$", re.IGNORECASE)
REGEX_VOLUME_PATH = re.compile(
    r"(?:#|(?:\\\?\?\\Volume(?P<guid>{.+}))|\\DosDevices\\(?P<letter>[a-z]):)$",
    re.IGNORECASE,
)
REGEX_DEVICE_INSTALL = re.compile(
    r"^>>>  \[Device Install \((?P<reason>.*?)\) - "
    r"(?:(?:"
    r"(?P<usbstor>"
    r"(?:USBSTOR\\)|"
    r"(?:SWD\\WPDBUSENUM\\_\?\?_USBSTOR#)|"
    r"(?:STORAGE\\Volume\\.*_\?\?_USBSTOR#)|"
    r"(?:WpdBusEnumRoot\\UMB\\.*?#VOLUME#.*_\?\?_USBSTOR#)"
    r")" + PATTERN_CLASS + r")|(?:" + PATTERN_HW + r"))"
    r"(?:\\|#)" + PATTERN_INSTANCE + r".*?\]\r\n?|\n",
    re.IGNORECASE,
)
