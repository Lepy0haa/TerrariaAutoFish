"""Поиск поплавка по картинкам поплавков с Wiki — на зонах поиска из режима записи
(светящийся поплавок ночью) и на широком кадре с пирсом, факелами, NPC и столбами."""
import unittest

import numpy as np

from helpers import FakeSct, af, load_bgr

ZONES = ("019", "022", "025", "026")


def with_bobber(scene, src, x, waterline=108):
    """Положить поплавок из зоны src на кромку воды сцены в точке x."""
    z = load_bgr("bobber", "%s_poisk.png" % src, down=4)
    out = scene.copy()
    out[waterline - 20:waterline + 6, x - 10:x + 10] = z[27:53, 42:62]
    return out


class TestBobber(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = af.Fisher()
        cls.pier = load_bgr("bobber", "029_poisk_shiroko.png", down=4)   # пирс, поплавка на воде нет

    def test_sprite_recognizes_bobber(self):
        for z in ZONES:
            best = self.f.sprite_search(load_bgr("bobber", "%s_poisk.png" % z, down=4))
            self.assertIsNotNone(best, z)
            self.assertGreaterEqual(best[0], af.SPRITE_MIN, z)
            self.assertEqual(best[3], "acc_glowing", z)

    def test_empty_water(self):
        best = self.f.sprite_search(load_bgr("bobber", "027_poisk_net.png", down=4))
        self.assertTrue(best is None or best[0] < af.SPRITE_MIN)

    def test_pier_is_not_bobber(self):
        # в широком кадре с пирсом без «снимка до заброса» — только строгое совпадение
        best = self.f.sprite_search(self.pier)
        self.assertTrue(best is None or best[0] < af.SPRITE_MIN + 0.05)
        self.assertLess(self.f.sprite_search(self.pier, only=["acc_glowing"])[0], af.SPRITE_MIN)

    def auto_mark(self, before, after):
        H, W = after.shape[:2]
        screen = [before]
        sct = FakeSct(lambda: screen[0])
        cl, player = (0, 0, W, H), (37, 25)
        f = af.Fisher()
        f.cast_point, f.park = (200, 150), (47, 5)
        area = f.mark_area(cl, player)
        f.mark_before = sct.grab(area)[:, :, :3].astype(np.float32) if before is not None else None
        screen[0] = after
        return f.auto_mark(sct, cl, player), f

    def test_auto_mark_finds_new_bobber_on_pier_scene(self):
        for z in ZONES:
            for x in (150, 200, 235):
                pos, f = self.auto_mark(self.pier, with_bobber(self.pier, z, x))
                self.assertIsNotNone(pos, "%s x=%d" % (z, x))
                self.assertLessEqual(abs(pos[0] - x), 3, "%s x=%d -> %s" % (z, x, pos))
                self.assertLessEqual(abs(pos[1] - 102), 3, "%s x=%d -> %s" % (z, x, pos))
                self.assertEqual(f.bobber_kind, "acc_glowing")

    def test_auto_mark_nothing_new(self):
        pos, _ = self.auto_mark(self.pier, self.pier)
        self.assertIsNone(pos)

    def test_wide_search_ignores_pier(self):
        f = af.Fisher()
        z = load_bgr("bobber", "025_poisk.png", down=4)
        f.bobber = z[31:53, 45:59].copy()
        f.bobber0 = f.bobber.copy()
        H, W = self.pier.shape[:2]
        pos, _ = f.search(FakeSct(lambda: self.pier), (0, 0, W, H), (127, 101), f.zone_x * 3, f.zone_y * 3, wide=True)
        self.assertIsNone(pos)
        # а настоящий поплавок в стороне широкий поиск находит
        scene = with_bobber(self.pier, "019", 190)
        pos, _ = f.search(FakeSct(lambda: scene), (0, 0, W, H), (127, 101), f.zone_x * 3, f.zone_y * 3, wide=True)
        self.assertIsNotNone(pos)
        self.assertLessEqual(abs(pos[0] - 190), 3)


if __name__ == "__main__":
    unittest.main()
