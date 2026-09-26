"""Маленький PNG-декодер без сторонних библиотек (для иконок баффов)."""
import struct
import zlib

import numpy as np


def read_png(path):
    """PNG -> numpy (H, W, 4) uint8 RGBA. Поддерживаются 8-битные RGB/RGBA/серый и палитра 1–8 бит."""
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, plte, trns = 8, b"", None, None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert interlace == 0, "interlaced PNG"
        elif kind == b"PLTE":
            plte = np.frombuffer(body, np.uint8).reshape(-1, 3)
        elif kind == b"tRNS":
            trns = np.frombuffer(body, np.uint8)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)                  # байт на пиксель (для фильтров)
    stride = (w * channels * depth + 7) // 8
    raw = zlib.decompress(idat)
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = np.frombuffer(raw, np.uint8, stride, y * (stride + 1) + 1).astype(np.int32)
        cur = np.zeros(stride, np.int32)
        for x in range(stride):
            a = cur[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 0:
                v = line[x]
            elif f == 1:
                v = line[x] + a
            elif f == 2:
                v = line[x] + b
            elif f == 3:
                v = line[x] + (a + b) // 2
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                v = line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)
            cur[x] = v & 0xFF
        out[y] = cur
        prev = cur
    if depth < 8:                                        # распаковать 1/2/4-битные значения
        bits = np.unpackbits(out, axis=1)
        vals = bits.reshape(h, -1, depth)
        weights = 1 << np.arange(depth - 1, -1, -1)
        out = (vals * weights).sum(2)[:, :w].astype(np.uint8)
    rgba = np.full((h, w, 4), 255, np.uint8)
    if ctype == 3:
        rgba[:, :, :3] = plte[out]
        if trns is not None:
            alpha = np.full(len(plte), 255, np.uint8)
            alpha[:len(trns)] = trns
            rgba[:, :, 3] = alpha[out]
    else:
        px = out.reshape(h, w, channels)
        if ctype in (0, 4):
            rgba[:, :, :3] = px[:, :, :1]
        else:
            rgba[:, :, :3] = px[:, :, :3]
        if ctype in (4, 6):
            rgba[:, :, 3] = px[:, :, -1]
    return rgba
