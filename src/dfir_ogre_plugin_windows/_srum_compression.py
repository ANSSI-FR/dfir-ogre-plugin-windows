"""Decode the compressed binary values hidden by libesedb's typed C accessor.

pyesedb exposes only the raw binary accessor. ESE's binary decompression uses
packed 7-bit bytes or a 0x18 / uint16-size header followed by plain LZXPRESS.
The latter follows MS-XCA 2.4.4:
https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-xca/34cb9ab9-5ce6-42d7-a518-107c1c7c65e7
ESE framing: https://github.com/libyal/libesedb/blob/20260704/libesedb/libesedb_compression.c
"""


def decompress_binary(data: bytes) -> bytes:
    if not data:
        raise ValueError("Empty compressed ESE binary value")
    if data[0] != 0x18:
        output = bytearray()
        pending = bits = 0
        for byte in data[1:]:
            pending |= byte << bits
            bits += 8
            while bits >= 7:
                output.append(pending & 0x7F)
                pending >>= 7
                bits -= 7
        if pending:
            raise ValueError("Invalid compressed ESE 7-bit remainder")
        return bytes(output)
    return _decompress_xpress(data)


def _decompress_xpress(data: bytes) -> bytes:
    position = 1

    def read(size):
        nonlocal position
        end = position + size
        if end > len(data):
            raise ValueError("Truncated compressed ESE LZXPRESS value")
        value = int.from_bytes(data[position:end], "little")
        position = end
        return value

    expected_size = read(2)
    output = bytearray()
    flags = bits = 0
    upper_nibble = None
    while position < len(data):
        if bits == 0:
            flags, bits = read(4), 32
        bits -= 1
        if flags & (1 << bits) == 0:
            if len(output) >= expected_size:
                raise ValueError("ESE LZXPRESS output exceeds declared size")
            output.append(read(1))
            continue
        if position == len(data):
            break
        match = read(2)
        distance, length = (match >> 3) + 1, match & 7
        if length == 7:
            if upper_nibble is None:
                packed = read(1)
                length, upper_nibble = packed & 15, packed >> 4
            else:
                length, upper_nibble = upper_nibble, None
            if length == 15:
                length = read(1)
                if length == 255:
                    length = read(2)
                    if length == 0:
                        # ESE's uint16 output size cannot contain a match that
                        # requires the MS-XCA 32-bit length extension.
                        raise ValueError("ESE LZXPRESS match exceeds uint16 size")
                    if length < 22:
                        raise ValueError("Invalid ESE LZXPRESS match length")
                    length -= 22
                length += 15
            length += 7
        length += 3
        if length > 32771:
            raise ValueError("ESE LZXPRESS match exceeds libesedb's size limit")
        if distance > len(output) or len(output) + length > expected_size:
            raise ValueError("Invalid ESE LZXPRESS match bounds")
        for _ in range(length):
            output.append(output[-distance])
    if len(output) != expected_size:
        raise ValueError("ESE LZXPRESS output does not match declared size")
    return bytes(output)
