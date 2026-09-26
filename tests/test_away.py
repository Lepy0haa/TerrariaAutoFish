"""Долгая рыбалка без присмотра: здоровье персонажа, наживка, лимиты сессии, новые зелья.
Сердечки — настоящий снимок верхнего правого угла игры (полное здоровье, 2 ряда по 10)."""
import time
import unittest

import numpy as np

from helpers import FakeGame, FakeSct, Run, af, hotbar, load_bgr

import buffs
import hotbar as hb


class Screen:
    """Экран 1680x1050: чёрный, справа вверху — снимок сердечек."""
    W, H = 1680, 1050

    def __init__(self):
        self.corner = load_bgr("game", "top_right_full_hp.png")
        self.img = np.zeros((self.H, self.W, 3), np.float32)
        self.put(self.corner)

    def put(self, corner):
        self.img[:corner.shape[0], self.W - corner.shape[1]:] = corner

    def hearts_x(self):
        m = af.heart_mask(self.corner)
        cols = np.nonzero(m[20:75].any(0))[0]
        return cols.min(), cols.max()


class TestHealth(unittest.TestCase):
    def setUp(self):
        self.saved = af.click, af.HEALTH_GUARD
        self.clicks = []
        af.click = lambda x, y, hold=0.06: self.clicks.append((x, y))
        af.HEALTH_GUARD = True
        self.scr = Screen()
        self.sct = FakeSct(lambda: self.scr.img)
        self.cl = (0, 0, Screen.W, Screen.H)
        self.f = af.Fisher()
        self.f.cast_point = (500, 600)
        self.f.running.set()

    def tearDown(self):
        af.click, af.HEALTH_GUARD = self.saved

    def check(self, n=3, watching=True):
        return [self.f.check_health(self.sct, self.cl, watching=watching) for _ in range(n)]

    def test_full_health_no_alarm(self):
        self.assertEqual(self.check(5), [False] * 5)
        self.assertTrue(self.f.running.is_set())
        self.assertGreater(self.f.hp_base, 2000)

    def test_damage_reels_in_and_pauses(self):
        self.check(2)
        # последние сердечки второго ряда опустели (игра убирает здоровье с конца)
        c = self.scr.corner.copy()
        x0, x1 = self.scr.hearts_x()
        c[45:75, x1 - int((x1 - x0) * 0.2):x1 + 1] = 20
        self.scr.put(c)
        res = self.check(3)
        self.assertIn(True, res)
        self.assertFalse(self.f.running.is_set(), "не встал на паузу")
        self.assertEqual(self.clicks, [(500, 600)], "не вытащил поплавок")

    def test_one_frame_glitch_is_ignored(self):
        self.check(2)
        c = self.scr.corner.copy()
        self.scr.put(c * 0.2)                 # один кадр «пропали сердечки» (например, вспышка)
        self.assertFalse(self.f.check_health(self.sct, self.cl, watching=True))
        self.scr.put(self.scr.corner)
        self.assertEqual(self.check(3), [False] * 3)
        self.assertTrue(self.f.running.is_set())

    def test_minimap_changes_are_ignored(self):
        self.check(2)
        c = self.scr.corner.copy()
        c[120:200, 100:400] = (40, 40, 230)      # что-то красное на мини-карте ниже сердечек
        self.scr.put(c)
        self.assertEqual(self.check(3), [False] * 3)
        c[120:200, 100:400] = 0
        self.scr.put(c)
        self.assertEqual(self.check(3), [False] * 3)

    def test_no_hearts_visible(self):
        self.scr.img[:] = 0
        self.assertEqual(self.check(3), [False] * 3)

    def test_regeneration_raises_baseline(self):
        c = self.scr.corner.copy()
        x0, x1 = self.scr.hearts_x()
        c[45:75, x1 - int((x1 - x0) * 0.2):x1 + 1] = 20
        self.scr.put(c)                           # начали рыбачить не с полным здоровьем
        self.check(2)
        self.scr.put(self.scr.corner)             # здоровье восстановилось — это не урон
        self.assertEqual(self.check(3), [False] * 3)


class TestBait(unittest.TestCase):
    def digits(self, key, slot):
        img = hotbar(key)
        sel = hb.selected_slot(img)
        x0, y0, x1, y1, rel = hb.slot_boxes(*sel)[slot]
        return hb.bait_digits(img[y0:y1, x0:x1].astype(np.float64), rel * sel[1])

    def test_digits(self):
        self.assertEqual(self.digits("5", 4), 3)      # удочка в руках: 356
        self.assertEqual(self.digits("1", 4), 3)      # удочка в обычном слоте
        self.assertEqual(self.digits("1", 8), 1)      # зелья: 5
        self.assertEqual(self.digits("5", 8), 1)
        self.assertEqual(self.digits("1", 1), 0)      # кирка — без числа
        self.assertEqual(self.digits("1", 0), 0)      # кнут в руках — без числа

    def test_low_bait_warns_once(self):
        f = af.Fisher()
        notes = []
        f.events = lambda k, d: notes.append(k)
        img = hotbar("9")                             # в руках зелья с числом «5» — как удочка с 5 наживками
        sel = hb.selected_slot(img)
        f.check_bait(img, sel)
        f.check_bait(img, sel)
        self.assertEqual(f.bait_digits, 1)
        self.assertEqual(notes.count("notify"), 1)

    def test_no_bait_pauses_without_retries(self):
        f = af.Fisher()
        f.running.set()
        f.bait_digits = 0
        f.fail("Поплавок не найден")
        self.assertFalse(f.running.is_set())
        self.assertEqual(f.recover_round, 0)


class TestSession(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(af, n) for n in ("REEL_DELAY", "STOP_AFTER_HOOKS", "STOP_AFTER_MIN",
                                                  "SHUTDOWN_AFTER", "schedule_shutdown", "HEALTH_GUARD")}
        af.REEL_DELAY = 0.3
        af.HEALTH_GUARD = False                       # в поддельной игре сердечек нет
        self.shutdowns = []
        af.schedule_shutdown = lambda s: self.shutdowns.append(s)

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(af, n, v)

    def run_until_stop(self, shutdown):
        af.STOP_AFTER_HOOKS, af.STOP_AFTER_MIN, af.SHUTDOWN_AFTER = 2, 0, shutdown
        game = FakeGame(selected="5")
        restore = game.install()
        r = Run(game)
        events = []
        old = r.event
        r.fisher.events = lambda k, d: (events.append(k), old(k, d))
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20))
            for _ in range(2):                        # две поклёвки
                time.sleep(0.6)
                game.empty = True
                n = r.fisher.hooks
                self.assertTrue(r.wait_for(lambda: r.fisher.hooks > n, 5))
                game.empty = False
                r.wait_for(lambda: r.waiting() or not r.fisher.running.is_set(), 10)
            self.assertTrue(r.wait_for(lambda: not r.fisher.running.is_set(), 10), r.logs[-4:])
            self.assertTrue(any(af.tr("Рыбалка закончена")[:10] in l for l in r.logs))
            return events
        finally:
            r.stop()
            restore()

    def test_stop_after_hooks(self):
        self.run_until_stop(False)
        self.assertEqual(self.shutdowns, [])

    def test_stop_and_shutdown(self):
        events = self.run_until_stop(True)
        self.assertEqual(self.shutdowns, [af.SHUTDOWN_DELAY])
        self.assertIn("shutdown", events)


class TestBuffs(unittest.TestCase):
    def test_new_potions_loaded(self):
        w = buffs.BuffWatcher(af.ASSET_DIR)
        self.assertEqual(sorted(w.icons), ["calm", "crate", "fishing", "sonar"])
        for n in w.icons:
            self.assertIn(n, af.BUFF_NAMES)
            self.assertIn(n, af.BUFF_WANT)


if __name__ == "__main__":
    unittest.main()
