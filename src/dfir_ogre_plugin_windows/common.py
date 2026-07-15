import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dfir_ogre_common import AbstractParser, FieldName, Record, Value


AMCACHE_SHA1_PATTERN = re.compile(r"(?:0000)?([0-9a-fA-F]{40})")


def normalize_amcache_sha1(identifier: object) -> str | None:
    """Extract a normalized SHA-1 digest from an Amcache identifier."""
    if not isinstance(identifier, str):
        return None

    match = AMCACHE_SHA1_PATTERN.fullmatch(identifier)
    if match is None:
        return None

    return match.group(1).lower()


def value(
    val: str | int | float | bool | datetime | bytes | bytearray | list[object] | None,
) -> Value:
    """
    Convert data into a Value object
    """
    if isinstance(val, str):
        return Value.String(val)
    elif isinstance(val, bool):
        return Value.Bool(val)
    elif isinstance(val, float):
        return Value.Float(val)
    elif isinstance(val, int):
        return Value.Int(val)
    elif isinstance(val, datetime):
        return Value.Date(val)
    elif isinstance(val, bytes):
        return Value.String(f"0x{val.hex()}")
    elif isinstance(val, bytearray):
        return Value.String(f"0x{val.hex()}")
    elif isinstance(val, list):
        return Value.String("".join(str(val)))
    return Value.Null()


def filetime_to_utc(filetime: int) -> datetime:
    """
    Converts a Windows filetime number to a Python datetime. The new
    datetime object is timezone-naive but is equivalent to tzinfo=utc.
    """
    EPOCH_AS_FILETIME = 116444736000000000
    HUNDREDS_OF_NS = 10000000

    s, ns100 = divmod(filetime - EPOCH_AS_FILETIME, HUNDREDS_OF_NS)

    return datetime.fromtimestamp(s, tz=timezone.utc).replace(microsecond=(ns100 // 10))


def fat_datetime_to_utc(fat_datetime: int) -> Optional[datetime]:
    try:
        date = (fat_datetime >> 16) & 0xFFFF
        time = fat_datetime & 0xFFFF

        day_of_month = date & 0x1F
        month = (date >> 5) & 0x0F
        year = (date >> 9) & 0x7F
        year += 1980

        seconds = (time & 0x1F) * 2
        minutes = (time >> 5) & 0x3F
        hours = (time >> 11) & 0x1F

        return datetime(
            year, month, day_of_month, hours, minutes, seconds, tzinfo=timezone.utc
        )
    except Exception:
        return None




class FileAttributesParser(AbstractParser):
    """Transform the flags in Attributes into a list of boolean fields"""

    DEFAULT_FIELD = FieldName("file_attribute_raw")
    FILE_ATTRIBUTES: Dict[str, FieldName] = {
        "A": FieldName("file_attributes_archive"),
        "B": FieldName("file_attributes_no_scrub_data"),
        "C": FieldName("file_attributes_compressed"),
        "D": FieldName("file_attributes_directory"),
        "E": FieldName("file_attributes_encrypted"),
        "H": FieldName("file_attributes_hidden"),
        "I": FieldName("file_attributes_not_content_indexed"),
        "L": FieldName("file_attributes_reparse_point"),
        "N": FieldName("file_attributes_normal"),
        "O": FieldName("file_attributes_offline"),
        "P": FieldName("file_attributes_sparse_file"),
        "R": FieldName("file_attributes_readonly"),
        "S": FieldName("file_attributes_system"),
        "T": FieldName("file_attributes_temporary"),
        "V": FieldName("file_attributes_virtual"),
        "a": FieldName("file_attributes_recall_on_data_access"),
        "d": FieldName("file_attributes_device"),
        "e": FieldName("file_attributes_ea"),
        "o": FieldName("file_attributes_recall_on_open"),
        "p": FieldName("file_attributes_pinned"),
        "s": FieldName("file_attributes_integrity_stream"),
        "u": FieldName("file_attributes_unpinned"),
    }
    data: Dict[str, bool]

    def __init__(self):
        super().__init__()
        data = {}
        for field_name in self.FILE_ATTRIBUTES.values():
            data[field_name.input_name()] = False
        self.data = data

    def parse(
        self,
        input: str,
        output_name: str,
    ) -> Record:
        record = Record()
        if not input:
            return record

        if input.startswith("0x") or input.startswith("-0x"):
            record.add(self.DEFAULT_FIELD.output_name(), Value.String(input))
        else:
            row_data = self.data.copy()
            for flag in input:
                if flag != ".":
                    field = self.FILE_ATTRIBUTES.get(flag, None)
                    if field:
                        row_data[field.input_name()] = True

            for key, value in row_data.items():
                record.add(key, Value.Bool(value))
        return record

    def output_fields_names(self) -> List[FieldName]:
        fields = [val for val in self.FILE_ATTRIBUTES.values()]
        fields.append(self.DEFAULT_FIELD)
        return fields


class FRNParser(AbstractParser):
    """Dispatch the content of the frn field on the 'sequence' and 'record' fields."""

    sequence: FieldName
    record: FieldName

    def __init__(self):
        super().__init__()
        self.sequence = FieldName("sequence_number")
        self.record = FieldName("record_number")

    @classmethod
    def build(cls, suffix: str) -> "FRNParser":
        parser = cls()
        parser.sequence = FieldName(f"{suffix}sequence_number")
        parser.record = FieldName(f"{suffix}record_number")
        return parser

    def parse(self, input: str, output_name: str) -> Record:
        record = Record()
        if not input:
            return record

        seq = int(input[2:6], base=16)
        rec = int(input[6:], base=16)

        record.add(self.sequence.output_name(), Value.Int(seq))
        record.add(self.record.output_name(), Value.Int(rec))
        return record

    def output_fields_names(self) -> List[FieldName]:
        return [self.sequence, self.record]

win_tz_to_iana = {
    "AUS Central Standard Time": "Australia/Darwin",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Afghanistan Standard Time": "Asia/Kabul",
    "Alaskan Standard Time": "America/Anchorage",
    "Aleutian Standard Time": "America/Adak",
    "Altai Standard Time": "Asia/Barnaul",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Arabic Standard Time": "Asia/Baghdad",
    "Argentina Standard Time": "America/Buenos_Aires",
    "Astrakhan Standard Time": "Europe/Astrakhan",
    "Atlantic Standard Time": "America/Halifax",
    "Aus Central W. Standard Time": "Australia/Eucla",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Azores Standard Time": "Atlantic/Azores",
    "Bahia Standard Time": "America/Bahia",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Belarus Standard Time": "Europe/Minsk",
    "Bougainville Standard Time": "Pacific/Bougainville",
    "Canada Central Standard Time": "America/Regina",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "Caucasus Standard Time": "Asia/Yerevan",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "Central America Standard Time": "America/Guatemala",
    "Central Asia Standard Time": "Asia/Almaty",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Central Standard Time": "America/Chicago",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Chatham Islands Standard Time": "Pacific/Chatham",
    "China Standard Time": "Asia/Shanghai",
    "Cuba Standard Time": "America/Havana",
    "Dateline Standard Time": "Etc/GMT+12",
    "E. Africa Standard Time": "Africa/Nairobi",
    "E. Australia Standard Time": "Australia/Brisbane",
    "E. Europe Standard Time": "Europe/Chisinau",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Easter Island Standard Time": "Pacific/Easter",
    "Eastern Standard Time": "America/New_York",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "Egypt Standard Time": "Africa/Cairo",
    "Ekaterinburg Standard Time": "Asia/Yekaterinburg",
    "FLE Standard Time": "Europe/Kiev",
    "Fiji Standard Time": "Pacific/Fiji",
    "GMT Standard Time": "Europe/London",
    "GTB Standard Time": "Europe/Bucharest",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Greenland Standard Time": "America/Godthab",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Haiti Standard Time": "America/Port-au-Prince",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "India Standard Time": "Asia/Calcutta",
    "Iran Standard Time": "Asia/Tehran",
    "Israel Standard Time": "Asia/Jerusalem",
    "Jordan Standard Time": "Asia/Amman",
    "Kaliningrad Standard Time": "Europe/Kaliningrad",
    "Korea Standard Time": "Asia/Seoul",
    "Libya Standard Time": "Africa/Tripoli",
    "Line Islands Standard Time": "Pacific/Kiritimati",
    "Lord Howe Standard Time": "Australia/Lord_Howe",
    "Magadan Standard Time": "Asia/Magadan",
    "Magallanes Standard Time": "America/Punta_Arenas",
    "Marquesas Standard Time": "Pacific/Marquesas",
    "Mauritius Standard Time": "Indian/Mauritius",
    "Middle East Standard Time": "Asia/Beirut",
    "Montevideo Standard Time": "America/Montevideo",
    "Morocco Standard Time": "Africa/Casablanca",
    "Mountain Standard Time": "America/Denver",
    "Mountain Standard Time (Mexico)": "America/Mazatlan",
    "Myanmar Standard Time": "Asia/Rangoon",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Namibia Standard Time": "Africa/Windhoek",
    "Nepal Standard Time": "Asia/Katmandu",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Newfoundland Standard Time": "America/St_Johns",
    "Norfolk Standard Time": "Pacific/Norfolk",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "North Korea Standard Time": "Asia/Pyongyang",
    "Omsk Standard Time": "Asia/Omsk",
    "Pacific SA Standard Time": "America/Santiago",
    "Pacific Standard Time": "America/Los_Angeles",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "Pakistan Standard Time": "Asia/Karachi",
    "Paraguay Standard Time": "America/Asuncion",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "Romance Standard Time": "Europe/Paris",
    "Russia Time Zone 10": "Asia/Srednekolymsk",
    "Russia Time Zone 11": "Asia/Kamchatka",
    "Russia Time Zone 3": "Europe/Samara",
    "Russian Standard Time": "Europe/Moscow",
    "SA Eastern Standard Time": "America/Cayenne",
    "SA Pacific Standard Time": "America/Bogota",
    "SA Western Standard Time": "America/La_Paz",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Saint Pierre Standard Time": "America/Miquelon",
    "Sakhalin Standard Time": "Asia/Sakhalin",
    "Samoa Standard Time": "Pacific/Apia",
    "Sao Tome Standard Time": "Africa/Sao_Tome",
    "Saratov Standard Time": "Europe/Saratov",
    "Singapore Standard Time": "Asia/Singapore",
    "South Africa Standard Time": "Africa/Johannesburg",
    "South Sudan Standard Time": "Africa/Juba",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Sudan Standard Time": "Africa/Khartoum",
    "Syria Standard Time": "Asia/Damascus",
    "Taipei Standard Time": "Asia/Taipei",
    "Tasmania Standard Time": "Australia/Hobart",
    "Tocantins Standard Time": "America/Araguaina",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Tomsk Standard Time": "Asia/Tomsk",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Transbaikal Standard Time": "Asia/Chita",
    "Turkey Standard Time": "Europe/Istanbul",
    "Turks And Caicos Standard Time": "America/Grand_Turk",
    "US Eastern Standard Time": "America/Indianapolis",
    "US Mountain Standard Time": "America/Phoenix",
    "UTC": "Etc/UTC",
    "UTC+12": "Etc/GMT-12",
    "UTC+13": "Etc/GMT-13",
    "UTC-02": "Etc/GMT+2",
    "UTC-08": "Etc/GMT+8",
    "UTC-09": "Etc/GMT+9",
    "UTC-11": "Etc/GMT+11",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Venezuela Standard Time": "America/Caracas",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "Volgograd Standard Time": "Europe/Volgograd",
    "W. Australia Standard Time": "Australia/Perth",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "W. Europe Standard Time": "Europe/Berlin",
    "W. Mongolia Standard Time": "Asia/Hovd",
    "West Asia Standard Time": "Asia/Tashkent",
    "West Bank Standard Time": "Asia/Hebron",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Yukon Standard Time": "America/Whitehorse",
}
