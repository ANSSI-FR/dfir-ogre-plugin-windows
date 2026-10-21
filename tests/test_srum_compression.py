"""Deterministic decoder boundary cases with known uncompressed contents."""

from unittest import TestCase

from dfir_ogre_plugin_windows._srum_compression import decompress_binary


def literal_stream(data):
    # An MS-XCA group has one 32-bit flag word and up to 32 literal tokens.
    groups = [b"\0" * 4 + data[i : i + 32] for i in range(0, len(data), 32)]
    return b"\x18" + len(data).to_bytes(2, "little") + b"".join(groups)


class SrumCompressionBoundaryTest(TestCase):
    def test_literal_flag_boundaries_and_uint16_output_limit(self):
        for size in (0, 1, 31, 32, 33, 63, 64, 65, 65535):
            with self.subTest(size=size):
                expected = bytes(i % 256 for i in range(size))
                self.assertEqual(decompress_binary(literal_stream(expected)), expected)

    def test_every_truncation_of_literal_stream_is_rejected(self):
        complete = literal_stream(bytes(range(65)))
        for size in range(len(complete)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                decompress_binary(complete[:size])

    def test_declared_size_must_match_literal_contents(self):
        complete = literal_stream(b"abc")
        for size in (0, 2, 4, 65535):
            data = complete[:1] + size.to_bytes(2, "little") + complete[3:]
            with self.subTest(size=size), self.assertRaises(ValueError):
                decompress_binary(data)

    def test_maximum_back_reference_distance(self):
        expected = bytes(range(256)) * 32
        data = literal_stream(expected)
        # Match token: distance 8192 (13 bits), length 3 (low three bits zero).
        data = (
            data[:1]
            + (8195).to_bytes(2, "little")
            + data[3:]
            + bytes.fromhex("00000080f8ff")
        )
        self.assertEqual(decompress_binary(data), expected + expected[:3])

    def test_native_match_length_boundary(self):
        for length in (32771, 32772):
            data = (
                b"\x18"
                + (length + 1).to_bytes(2, "little")
                + bytes.fromhex("000000406107000fff")
                + (length - 3).to_bytes(2, "little")
            )
            with self.subTest(length=length):
                if length == 32771:
                    self.assertEqual(decompress_binary(data), b"a" * (length + 1))
                else:
                    with self.assertRaises(ValueError):
                        decompress_binary(data)

    def test_seven_bit_values_across_all_bit_positions(self):
        # 128 characters occupy exactly 112 bytes, with no ambiguous pad byte.
        expected = bytes(range(128))
        packed = sum(value << (position * 7) for position, value in enumerate(expected))
        data = b"\x10" + packed.to_bytes(112, "little")
        self.assertEqual(decompress_binary(data), expected)
        self.assertEqual(decompress_binary(b"\x10"), b"")
