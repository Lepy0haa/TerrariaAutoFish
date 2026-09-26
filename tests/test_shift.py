"""Сдвиг всей картинки (персонажа сдвинуло, камера уехала): точки переносятся на столько же."""
import time
import unittest

import numpy as np

from helpers import FakeGame, Run, af, load_bgr

import sceneshift


class TestEstimate(unittest.TestCase):
    def check(self, img):
        g = sceneshift.gray(img)
        H, W = g.shape
        h, w = H * 2 // 3, W * 2 // 3
        base = g[20:20 + h, 20:20 + w]
        rng = np.random.default_rng(1)
        for dx, dy in ((0, 0), (5, 0), (-12, 7), (18, -15)):
            cur = g[20 - dy:20 - dy + h, 20 - dx:20 - dx + w] + rng.normal(0, 4, (h, w))
            r = sceneshift.estimate(base, cur)
            self.assertIsNotNone(r, (dx, dy))
            self.assertEqual(r[:2], (dx, dy))
        # совсем другое место — это не сдвиг
        self.assertIsNone(sceneshift.estimate(base, g[H - h:H, W - w:W]))

    def test_pier(self):
        self.check(load_bgr("bobber", "029_poisk_shiroko.png", down=2))

    def test_lava(self):
        self.check(load_bgr("bobber", "lava_avto_poisk.png", down=2))


class TestFollowShift(unittest.TestCase):
    def test_points_follow_the_picture(self):
        saved = {n: getattr(af, n) for n in ("REEL_DELAY", "HEALTH_GUARD", "BUFFS_ON", "SONAR_FILTER")}
        af.REEL_DELAY, af.HEALTH_GUARD, af.BUFFS_ON, af.SONAR_FILTER = 0.3, False, False, False
        game = FakeGame(selected="5")
        game.terrain = True
        restore = game.install()
        r = Run(game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            time.sleep(0.5)
            cp, mark = r.fisher.cast_point, r.fisher.mark
            dx, dy = 45, 12                   # вода в поддельной игре повторяется через 30 пикс.
            # персонажа сдвинуло: вся картинка уехала, а в прежнюю точку заброса воды больше нет
            game.need_cast = (cp[0] + dx, cp[1] + dy)
            game.shift = (dx, dy)
            self.assertTrue(r.wait_for(lambda: any("сдвинулась" in l for l in r.logs), 30), r.logs[-6:])
            self.assertEqual(r.fisher.cast_point, (cp[0] + dx, cp[1] + dy))
            self.assertEqual(r.fisher.mark, (mark[0] + dx, mark[1] + dy))
            hooks = r.fisher.hooks
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-6:])     # снова ловит на новом месте
            time.sleep(0.8)
            game.empty = True                                           # клюнуло
            self.assertTrue(r.wait_for(lambda: r.fisher.hooks > hooks, 10), r.logs[-6:])
            self.assertTrue(r.fisher.running.is_set())
        finally:
            r.stop()
            restore()
            for n, v in saved.items():
                setattr(af, n, v)


if __name__ == "__main__":
    unittest.main()
