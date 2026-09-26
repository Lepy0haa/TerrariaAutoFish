"""Поклёвки: записи из режима записи (сколько поплавка было видно каждые ~17 мс и когда
подсёк игрок) прогоняются через детектор поклёвки вместе с автокалибровкой по первому забросу."""
import glob
import os
import re
import unittest

import numpy as np

from helpers import DATA, af

FLAT = np.zeros((4, 4, 3), np.float32)           # «небо» не меняется — вспышек молний нет


def load(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    user = float(re.search(r"(\d+\.\d+) ", lines[0]).group(1))      # через сколько секунд подсёк игрок
    rows = [(float(t), int(v)) for t, v, _ in (ln.split(", ") for ln in lines[6:] if ln.count(",") == 2)]
    return user, rows


def replay(rows, ratio, calibrate):
    """Как в Fisher.cycle: порог ratio, а без прошлых забросов — по первой секунде этого.
    Возвращает (время поклёвки или None, порог)."""
    det = af.BiteDetector(np.zeros((1, 3)))
    det.ratio = ratio
    seen = [0]
    det.visible = lambda frame: seen[0]
    calm = []
    for t, v in rows:
        seen[0] = v
        why = det.feed(FLAT, t)
        if det.ref and t >= af.CALIB_TIME:
            calm.append(v / det.ref)
        if calibrate and t >= af.CALIB_NOW and len(calm) >= 30:
            calibrate = False
            det.ratio = float(np.clip(np.percentile(calm, 2) - af.CALIB_MARGIN, 0.35, af.CALIB_MAX))
        if why:
            return t, det.ratio
    return None, det.ratio


class TestBites(unittest.TestCase):
    files = sorted(glob.glob(os.path.join(DATA, "bites", "*.txt")))

    def test_have_data(self):
        self.assertGreaterEqual(len(self.files), 9)

    def test_first_cast_catches_every_bite(self):
        for f in self.files:
            user, rows = load(f)
            t, ratio = replay(rows, 0.55, calibrate=True)
            name = os.path.basename(f)
            self.assertIsNotNone(t, "%s: поклёвка не поймана (порог %.2f)" % (name, ratio))
            # не раньше, чем поплавок нырнул (игрок подсекает с запаздыванием до ~1.5 с)
            self.assertGreaterEqual(t, user - 1.5, name)
            self.assertLessEqual(t, user, name)

    def test_calibrated_threshold_catches_every_bite(self):
        for f in self.files:
            user, rows = load(f)
            t, _ = replay(rows, af.CALIB_MAX, calibrate=False)
            self.assertIsNotNone(t, os.path.basename(f))
            self.assertGreaterEqual(t, user - 1.5, os.path.basename(f))

    def test_no_bite_on_calm_water(self):
        # всё, что было раньше чем за 1.5 с до подсечки, — спокойная вода: срабатываний нет
        for f in self.files:
            user, rows = load(f)
            calm = [(t, v) for t, v in rows if t < user - 1.5]
            t, _ = replay(calm, af.CALIB_MAX, calibrate=False)
            self.assertIsNone(t, "%s: ложная подсечка на %.2f с" % (os.path.basename(f), t or 0))

    def test_detection_starts_quickly(self):
        # поклёвка в самом начале слежения тоже ловится: 0.4 с спокойно, потом поплавок ныряет
        rows = [(i * 0.017, 160) for i in range(24)] + [(0.41 + i * 0.017, 50) for i in range(10)]
        t, _ = replay(rows, 0.55, calibrate=True)
        self.assertIsNotNone(t)
        self.assertLess(t, 0.6)


if __name__ == "__main__":
    unittest.main()
