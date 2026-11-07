#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the plist entitlement slot from a thin ARM64 Mach-O signature.

codesign's display output is not a stable plist serialization. Inspect the signed
file itself; signature authenticity is verified separately by codesign.
"""
import plistlib
import struct


def read_entitlements(binary):
    if len(binary) < 32 or struct.unpack_from("<II", binary) != (0xFEEDFACF, 0x0100000C):
        raise ValueError("Expected a thin ARM64 Mach-O")
    commands, command_bytes = struct.unpack_from("<II", binary, 16)
    end = 32 + command_bytes
    if end > len(binary) or commands > command_bytes // 8:
        raise ValueError("Invalid Mach-O load command bounds")
    cursor = 32
    for _ in range(commands):
        if cursor + 8 > end:
            raise ValueError("Truncated Mach-O load command")
        command, size = struct.unpack_from("<II", binary, cursor)
        if size < 8 or cursor + size > end:
            raise ValueError("Invalid Mach-O load command size")
        if command == 0x1D:  # LC_CODE_SIGNATURE
            if size < 16:
                raise ValueError("Truncated code signature command")
            offset, length = struct.unpack_from("<II", binary, cursor + 8)
            if length < 12 or offset + length > len(binary):
                raise ValueError("Invalid code signature bounds")
            magic, blob_length, count = struct.unpack_from(">III", binary, offset)
            if magic != 0xFADE0CC0 or blob_length > length or blob_length < 12 or count > (blob_length - 12) // 8:
                raise ValueError("Invalid embedded signature superblob")
            for index in range(count):
                slot, relative = struct.unpack_from(">II", binary, offset + 12 + index * 8)
                if slot != 5:  # CSSLOT_ENTITLEMENTS
                    continue
                if relative < 12 + count * 8 or relative + 8 > blob_length:
                    raise ValueError("Invalid entitlement slot bounds")
                kind, slot_length = struct.unpack_from(">II", binary, offset + relative)
                if kind != 0xFADE7171 or slot_length < 8 or relative + slot_length > blob_length:
                    raise ValueError("Invalid entitlement blob")
                value = plistlib.loads(binary[offset + relative + 8:offset + relative + slot_length])
                if not isinstance(value, dict):
                    raise ValueError("Expected entitlement dictionary")
                return value
            raise ValueError("The signature has no plist entitlement slot")
        cursor += size
    raise ValueError("The executable has no embedded signature")
