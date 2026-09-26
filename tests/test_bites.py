"""Поклёвки: записи из режима записи (сколько поплавка было видно каждые ~17 мс и когда
подсёк игрок) прогоняются через настоящий детектор поклёвки — с подстройкой порога на лету
и «резким нырком»."""
import glob
import math
import os
import re
import unittest

import numpy as np

from helpers import DATA, af

FLAT = np.zeros((4, 4, 3), np.float32)           # «небо» не меняется — вспышек молний нет
DT = 0.017                                       # снимок примерно раз в 17 мс


def load(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    user = float(re.search(r"(\d+\.\d+) ", lines[0]).group(1))      # через сколько секунд подсёк игрок
    rows = [(float(t), int(v)) for t, v, _ in (ln.split(", ") for ln in lines[6:] if ln.count(",") == 2)]
    return user, rows


def replay(rows, ratio, auto=True):
    """Прогон через BiteDetector (как в Fisher.cycle). (время поклёвки или None, порог, детектор)."""
    det = af.BiteDetector(np.zeros((1, 3)))
    det.ratio, det.auto = ratio, auto
    seen = [0]
    det.visible = lambda frame: seen[0]
    for t, v in rows:
        seen[0] = v
        if det.feed(FLAT, t):
            return t, det.ratio, det
    return None, det.ratio, det


def synth(func, seconds):
    return [(i * DT, int(round(func(i * DT)))) for i in range(int(seconds / DT))]


class TestBites(unittest.TestCase):
    files = sorted(glob.glob(os.path.join(DATA, "bites", "*.txt")))

    def test_have_data(self):
        self.assertGreaterEqual(len(self.files), 9)

    def check_all_caught(self, ratio, auto):
        for f in self.files:
            user, rows = load(f)
            t, r, _ = replay(rows, ratio, auto)
            name = os.path.basename(f)
            self.assertIsNotNone(t, "%s: поклёвка не поймана (порог %.2f)" % (name, r))
            # не раньше, чем поплавок нырнул (игрок подсекает с запаздыванием до ~1.5 с)
            self.assertGreaterEqual(t, user - 1.5, name)
            self.assertLessEqual(t, user, name)

    def test_first_cast_catches_every_bite(self):
        self.check_all_caught(0.55, auto=True)          # порог из настроек + подстройка на лету

    def test_calibrated_threshold_catches_every_bite(self):
        self.check_all_caught(af.CALIB_MAX, auto=True)

    def test_too_low_threshold_still_catches_bites(self):
        # так было: автокалибровка «съехала» до 38 % — поклёвки всё равно ловятся (резкий нырок,
        # подстройка на лету)
        self.check_all_caught(0.38, auto=False)
        self.check_all_caught(0.38, auto=True)

    def test_no_bite_on_calm_water(self):
        # всё, что было раньше чем за 1.5 с до подсечки, — спокойная вода: срабатываний нет
        for f in self.files:
            user, rows = load(f)
            calm = [(t, v) for t, v in rows if t < user - 1.5]
            for ratio in (0.55, af.CALIB_MAX):
                t, _, _ = replay(calm, ratio)
                self.assertIsNone(t, "%s: ложная подсечка на %.2f с" % (os.path.basename(f), t or 0))

    def test_threshold_rises_on_calm_water(self):
        user, rows = load(self.files[0])
        _, _, det = replay([(t, v) for t, v in rows if t < user - 1.5], 0.55)
        self.assertGreaterEqual(det.ratio, 0.7)

    def test_detection_starts_quickly(self):
        # поклёвка в самом начале слежения тоже ловится: 0.4 с спокойно, потом поплавок ныряет
        rows = synth(lambda t: 160 if t < 0.41 else 50, 0.6)
        t, _, _ = replay(rows, 0.55)
        self.assertIsNotNone(t)
        self.assertLess(t, 0.6)

    def test_shallow_sharp_dip_is_a_bite(self):
        # поплавок дёрнуло только до 70 % — ниже порога 55 % не ушёл, но нырок резкий
        rows = synth(lambda t: 160 if t < 2.0 else 112, 2.2)
        t, _, _ = replay(rows, 0.55, auto=False)
        self.assertIsNotNone(t)
        self.assertLess(t, 2.1)

    def test_waves_and_landing_bounce_are_not_bites(self):
        # после приводнения поплавок покачивается (±12 %), потом волны (±6 %, 1 раз в секунду)
        def level(t):
            bounce = 0.12 * math.cos(2 * math.pi * 3 * t) * max(0.0, 1 - t / 0.6)
            return 160 * (1 + bounce + 0.06 * math.sin(2 * math.pi * t))
        t, _, det = replay(synth(level, 8.0), 0.55)
        self.assertIsNone(t, "ложная подсечка на %.2f с" % (t or 0))

    def test_calibration_ignores_landing_bounce(self):
        # покачивание в первые 0.6 с не должно опускать порог (так он съезжал до 38–47 %)
        def level(t):
            return 160 * (0.55 if 0.3 < t < 0.5 else 1.0)
        f = af.Fisher()
        det = af.BiteDetector(np.zeros((1, 3)))
        seen = [0]
        det.visible = lambda frame: seen[0]
        for t, v in synth(level, 2.5):                  # все кадры, не останавливаясь на подсечке
            seen[0] = v
            det.feed(FLAT, t)
        f.learn(det.calm, 2.5)
        self.assertGreaterEqual(f.sink_ratio(), 0.75)


if __name__ == "__main__":
    unittest.main()
