"""
Образцы цифр игрового шрифта для чтения числа наживки на удочке (assets/digits.npz).
Берутся со снимков хотбара из игры в tests/data/hotbar: какое число написано в каком слоте —
в таблице ниже (проверено глазами).

    python tools/build_digits.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import hotbar  # noqa: E402
from pngread import read_png  # noqa: E402

DATA = os.path.join(ROOT, "tests", "data", "hotbar")
# снимок -> {номер слота на клавиатуре: число}
NUMBERS = {
    "blurred_whip_selected.png": {"8": "12", "9": "11"},
    "garland_crate_potion.png": {"6": "294", "9": "5"},
    "old_capture_rod_selected.png": {"5": "208"},
    "single_crate_potion.png": {"5": "154", "7": "6", "8": "20"},
    "rod_274_bait.png": {"6": "274", "7": "90", "9": "10"},
}
for k in "1234567890":
    NUMBERS["sel_%s.png" % k] = {"5": "356", "9": "5"}


def samples():
    """[(цифра, признаки, снимок)] со всех размеченных снимков."""
    out = []
    for name, numbers in sorted(NUMBERS.items()):
        img = read_png(os.path.join(DATA, name))[:, :, :3][:, :, ::-1].astype(np.float32)
        sel = hotbar.selected_slot(img)
        boxes = hotbar.slot_boxes(*sel)
        for key, number in numbers.items():
            x0, y0, x1, y1, rel = boxes[(int(key) - 1) % 10]
            cell = img[max(0, y0):y1, max(0, x0):x1].astype(np.float64)
            glyphs = hotbar.digit_glyphs(cell, rel * sel[1])
            assert len(glyphs) == len(number), (name, key, number, len(glyphs))
            for g, ch in zip(glyphs, number):
                out.append((ch, hotbar.glyph_features(g), name))
    return out


def main():
    s = samples()
    path = os.path.join(ROOT, "assets", "digits.npz")
    np.savez_compressed(path, features=np.array([f for _, f, _ in s]), labels=np.array([c for c, _, _ in s]))
    print("%d образцов, цифры: %s -> %s" % (len(s), "".join(sorted({c for c, _, _ in s})), path))


if __name__ == "__main__":
    main()
