from __future__ import annotations

import binascii
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {2: 3, 6: 4}


class PngError(ValueError):
    pass


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_rgba(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise PngError(
            f"pixel buffer length {len(rgba)} does not match {width}x{height} RGBA"
        )
    stride = width * 4
    raw = b"".join(
        b"\x00" + rgba[row * stride : (row + 1) * stride] for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytes:
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        if filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                upper_left = previous[index - channels] if index >= channels else 0
                up = previous[index]
                estimate = left + up - upper_left
                deltas = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - upper_left),
                )
                nearest = (left, up, upper_left)[deltas.index(min(deltas))]
                line[index] = (line[index] + nearest) & 0xFF
        elif filter_type != 0:
            raise PngError(f"unsupported PNG filter type {filter_type}")
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return bytes(out)


def decode_rgba(data: bytes) -> tuple[int, int, bytes]:
    if not data.startswith(SIGNATURE):
        raise PngError("data does not begin with a PNG signature")
    position = len(SIGNATURE)
    header: tuple | None = None
    compressed = bytearray()
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if header is None:
        raise PngError("PNG has no IHDR chunk")
    width, height, depth, colour_type, _compression, _filter, interlace = header
    if depth != 8:
        raise PngError(f"only 8-bit PNGs are supported, got {depth}")
    if interlace != 0:
        raise PngError("interlaced PNGs are not supported")
    if colour_type not in _CHANNELS:
        raise PngError(f"unsupported PNG colour type {colour_type}")
    channels = _CHANNELS[colour_type]
    pixels = _unfilter(zlib.decompress(bytes(compressed)), width, height, channels)
    if channels == 4:
        return width, height, pixels
    rgba = bytearray(width * height * 4)
    for index in range(width * height):
        rgba[index * 4 : index * 4 + 3] = pixels[index * 3 : index * 3 + 3]
        rgba[index * 4 + 3] = 255
    return width, height, bytes(rgba)
