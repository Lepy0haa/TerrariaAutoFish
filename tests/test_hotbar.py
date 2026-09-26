"""Хотбар: выбранный слот и где удочка — на настоящих снимках из игры.

На снимках sel_1..sel_0 выбран слот 1..0, удочка (Mechanic's Rod, 356 наживки) — в слоте 5,
в слоте 1 — кнут «Шипохват», в слоте 9 — зелья (тоже с числом)."""
import unittest


import helpers  # noqa: F401  (пути и настройки)
from helpers import af, hotbar, load_bgr

import hotbar as hb

ROD = 4                                          # слот 5


class TestHotbar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rods = hb.RodFinder(af.ASSET_DIR + "/rods")

    def test_selected_slot(self):
        for key in "1234567890":
            sel = hb.selected_slot(hotbar(key))
            self.assertIsNotNone(sel, key)
            self.assertEqual((sel[0] + 1) % 10, int(key), "выбран слот %s" % key)
            self.assertAlmostEqual(sel[1], 1.0, delta=0.05)

    def test_rod_found_whatever_is_selected(self):
        for key in "1234567890":
            r = self.rods.find(hotbar(key), af.ROD_HINT_MIN, af.ROD_HINT_MARGIN)
            self.assertIsNotNone(r, "выбран слот %s: удочка не найдена" % key)
            self.assertEqual(r[0], ROD, "выбран слот %s" % key)
            self.assertEqual(r[1], "mechanics")

    def test_only_rod_and_potions_have_numbers(self):
        _, out = self.rods.scores(hotbar("1"))
        self.assertEqual([i for i, (_, _, cnt) in enumerate(out) if cnt], [ROD, 8])

    def test_blurred_screenshot_with_whip_selected(self):
        # скриншот игрока (уменьшенный и размытый), в руках кнут
        r = self.rods.find(load_bgr("hotbar", "blurred_whip_selected.png"), af.ROD_HINT_MIN, af.ROD_HINT_MARGIN)
        self.assertIsNotNone(r)
        self.assertEqual(r[0], ROD)

    def test_old_capture(self):
        r = self.rods.find(load_bgr("hotbar", "old_capture_rod_selected.png"), af.ROD_HINT_MIN, af.ROD_HINT_MARGIN)
        self.assertIsNotNone(r)
        self.assertEqual(r[0], ROD)

    def test_no_rod_in_hotbar(self):
        # вместо удочки в слоте 5 — то же, что в слоте 6 (без числа): удочки нет — ничего не выдумываем
        img = hotbar("1")
        boxes = hb.slot_boxes(*hb.selected_slot(img))
        x0, y0, x1, y1, _ = boxes[ROD]
        a0, b0, a1, b1, _ = boxes[ROD + 1]
        img[y0:y1, x0:x1] = img[b0:b1, a0:a1]
        r = self.rods.find(img, af.ROD_HINT_MIN, af.ROD_HINT_MARGIN)
        self.assertTrue(r is None or r[0] != ROD)

    def test_ensure_rod_takes_rod_from_whip(self):
        # слот удочки ещё неизвестен, в руках кнут: программа сама жмёт 5
        game = helpers.FakeGame(selected="1")
        restore = game.install()
        try:
            f = af.Fisher()
            f.hotbar_frame = lambda sct, cl: game.screen()[:200, :game.W]
            self.assertTrue(f.ensure_rod(None, (0, 0, game.W, game.H)))
            self.assertEqual(game.keys, ["5"])
            self.assertEqual(f.cast_slot, ROD)
            f.learn_rod()
            self.assertEqual(f.rod_slot, ROD)
            # теперь слот известен: снова выбрали кнут — снова 5, уже без поиска по картинкам
            game.selected, game.keys = "1", []
            f.rods = None
            self.assertTrue(f.ensure_rod(None, (0, 0, game.W, game.H)))
            self.assertEqual(game.keys, ["5"])
        finally:
            restore()

    def test_manual_rod_slot(self):
        game = helpers.FakeGame(selected="1")
        restore = game.install()
        old = af.ROD_SLOT
        try:
            af.ROD_SLOT = 2
            f = af.Fisher()
            f.hotbar_frame = lambda sct, cl: game.screen()[:200, :game.W]
            f.ensure_rod(None, (0, 0, game.W, game.H))
            self.assertEqual(game.keys, ["3"])
        finally:
            af.ROD_SLOT = old
            restore()

    def test_rod_already_in_hand(self):
        game = helpers.FakeGame(selected="5")
        restore = game.install()
        try:
            f = af.Fisher()
            f.hotbar_frame = lambda sct, cl: game.screen()[:200, :game.W]
            self.assertFalse(f.ensure_rod(None, (0, 0, game.W, game.H)))
            self.assertEqual(game.keys, [])
            self.assertEqual(f.cast_slot, ROD)
        finally:
            restore()


if __name__ == "__main__":
    unittest.main()
