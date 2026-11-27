"""Encode a short ASCII confirmation code as a Version 1-L QR image."""

import struct
import zlib

SIZE = 21
DATA_WORDS = 19
# Generator polynomial coefficients for the seven Reed–Solomon parity bytes.
PARITY_COEFFICIENTS = (127, 122, 154, 164, 11, 68, 117)
FORMAT_BITS = 0x77C4  # Error correction L, mask 0, with QR format parity.


def gf_multiply(value, factor):
    """Multiply in the QR finite field with reduction polynomial 0x11D."""
    product = 0
    while factor:
        if factor & 1:
            product ^= value
        factor >>= 1
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    return product


def qr_codewords(code):
    """Build byte-mode data and its error correction codewords."""
    payload = code.encode("ascii")
    if not 1 <= len(payload) <= 17:
        raise ValueError("A Version 1-L QR accepts 1–17 ASCII characters in byte mode.")

    bits = f"0100{len(payload):08b}"  # Byte mode and character count.
    bits += "".join(f"{byte:08b}" for byte in payload)
    bits += "0000"  # End marker. This byte-mode payload now ends on a byte boundary.
    words = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    for i in range(DATA_WORDS - len(words)):
        words.append(0xEC if i % 2 == 0 else 0x11)

    parity = [0] * len(PARITY_COEFFICIENTS)
    for word in words:
        factor = word ^ parity.pop(0)
        parity.append(0)
        for i, coefficient in enumerate(PARITY_COEFFICIENTS):
            parity[i] ^= gf_multiply(coefficient, factor)
    return words + parity


def qr_matrix(code):
    """Place finder, timing, format and data modules in a 21 × 21 grid."""
    grid = [[None] * SIZE for _ in range(SIZE)]
    for center_x, center_y in [(3, 3), (SIZE - 4, 3), (3, SIZE - 4)]:
        for y in range(max(0, center_y - 4), min(SIZE, center_y + 5)):
            for x in range(max(0, center_x - 4), min(SIZE, center_x + 5)):
                distance = max(abs(x - center_x), abs(y - center_y))
                grid[y][x] = distance not in (2, 4)

    for i in range(8, SIZE - 8):
        grid[6][i] = i % 2 == 0
        grid[i][6] = i % 2 == 0

    primary = [(8, y) for y in range(6)] + [(8, 7), (8, 8), (7, 8)]
    primary += [(x, 8) for x in range(5, -1, -1)]
    secondary = [(x, 8) for x in range(SIZE - 1, SIZE - 9, -1)]
    secondary += [(8, y) for y in range(SIZE - 7, SIZE)]
    for i, ((x1, y1), (x2, y2)) in enumerate(zip(primary, secondary)):
        dark = bool(FORMAT_BITS & (1 << i))
        grid[y1][x1] = dark
        grid[y2][x2] = dark
    grid[SIZE - 8][8] = True

    # Fill two columns at a time, alternating up and down. Skip the timing column.
    bits = iter("".join(f"{word:08b}" for word in qr_codewords(code)))
    right_column = SIZE - 1
    upwards = True
    while right_column > 0:
        if right_column == 6:
            right_column -= 1
        rows = range(SIZE - 1, -1, -1) if upwards else range(SIZE)
        for y in rows:
            for x in (right_column, right_column - 1):
                if grid[y][x] is None:
                    dark = next(bits) == "1"
                    grid[y][x] = dark ^ ((x + y) % 2 == 0)
        right_column -= 2
        upwards = not upwards
    return grid


def png_chunk(kind, data):
    """Wrap a block of PNG data with its length, type and checksum."""
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def qr_png(code):
    """Return a grayscale PNG with a four-module white border."""
    scale = 8
    side = (SIZE + 8) * scale
    blank = b"\x00" + b"\xff" * side
    pixels = [blank] * (4 * scale)
    for modules in qr_matrix(code):
        row = b"\x00" + b"\xff" * (4 * scale)
        row += b"".join((b"\x00" if module else b"\xff") * scale for module in modules)
        row += b"\xff" * (4 * scale)
        pixels.extend([row] * scale)
    pixels.extend([blank] * (4 * scale))

    header = struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(b"".join(pixels)))
        + png_chunk(b"IEND", b"")
    )
