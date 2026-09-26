"""Надпись «как у сонара» для тестов: цветной текст с чёрной тенью, нарисованный шрифтом Windows
(GDI) — на снимке фона из игры. Шрифт Terraria другой, но проверяется весь путь: выделение
надписи по отличию от фона, подготовка, OCR, поиск предмета по названию."""
import ctypes
import ctypes.wintypes as wt

import numpy as np

gdi, user = ctypes.windll.gdi32, ctypes.windll.user32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def render(text, height=20, width=400, font="Segoe UI"):
    """Маска букв (h, w) bool: белый текст на чёрном, шрифт font полужирный."""
    hdc = gdi.CreateCompatibleDC(0)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hbmp = gdi.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    gdi.SelectObject(hdc, hbmp)
    hfont = gdi.CreateFontW(-height, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 3, 0, font)   # 3 = NONANTIALIASED
    gdi.SelectObject(hdc, hfont)
    gdi.SetBkMode(hdc, 1)
    gdi.SetTextColor(hdc, 0xFFFFFF)
    gdi.TextOutW(hdc, 4, height // 4, text, len(text))
    buf = (ctypes.c_uint8 * (width * height * 2 * 4)).from_address(bits.value)
    img = np.frombuffer(bytes(buf), np.uint8).reshape(height * 2, width, 4)[:, :, :3].copy()
    gdi.DeleteObject(hfont)
    gdi.DeleteObject(hbmp)
    gdi.DeleteDC(hdc)
    return img.max(2) > 128


def put_text(background, text, color, x, y, height=18):
    """Нарисовать на кадре BGR надпись цвета color (BGR) с чёрной тенью (как в Terraria)."""
    m = render(text, height)
    ys, xs = np.nonzero(m)
    out = background.copy()
    H, W = out.shape[:2]
    for dy, dx in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        yy, xx = ys + y + dy, xs + x + dx
        ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
        out[yy[ok], xx[ok]] = (10, 10, 10)
    yy, xx = ys + y, xs + x
    ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
    out[yy[ok], xx[ok]] = color
    return out
