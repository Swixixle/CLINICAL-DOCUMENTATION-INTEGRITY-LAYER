"""
UUIDv7 generator implementation.

UUIDv7 embeds a timestamp in the first 48 bits for natural time-based ordering.
This is more appropriate for transaction IDs than random UUIDv4.
"""

import time
import os
import uuid


def generate_uuid7() -> str:
    """
    Generate a UUIDv7 string.

    Format (RFC 9562):
    - Bits 0-47: Unix timestamp in milliseconds (48 bits)
    - Bits 48-51: Version = 7 (0111)
    - Bits 52-53: Variant = RFC4122 (10)
    - Bits 54-127: Random data (74 bits)

    Returns:
        String representation of UUIDv7
    """
    # Get current timestamp in milliseconds
    timestamp_ms = int(time.time() * 1000)

    # Extract 48 bits of timestamp
    timestamp_48 = timestamp_ms & 0xFFFFFFFFFFFF

    # Generate random bytes for the rest
    random_bytes = os.urandom(10)  # 80 bits of random data

    # Build the UUID bytes
    # Bytes 0-5: timestamp (48 bits)
    uuid_bytes = bytearray()
    uuid_bytes.extend(timestamp_48.to_bytes(6, byteorder="big"))

    # Bytes 6-7: version and random (16 bits)
    # Take first 2 bytes of random, set version to 7 (0111 in high nibble of byte 6)
    uuid_bytes.extend(random_bytes[0:2])
    uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x70  # Set version to 7

    # Bytes 8-9: variant and random (16 bits)
    # Set variant to 10 (RFC4122)
    uuid_bytes.extend(random_bytes[2:4])
    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80  # Set variant to 10

    # Bytes 10-15: random (48 bits)
    uuid_bytes.extend(random_bytes[4:10])

    # Convert to UUID object to get proper string formatting
    return str(uuid.UUID(bytes=bytes(uuid_bytes)))
