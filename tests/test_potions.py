"""Зелья из хотбара: программа находит нужное зелье (на снимках из игры в слоте 9 — зелье
рыбалки), берёт его цифрой слота, пьёт кликом и снова берёт удочку (слот 5)."""
import unittest

from helpers import FakeGame, Run, af, hotbar

import hotbar as hb


class FakeBuffs:
    """Баффы «на экране»: рыбалка появляется, когда в поддельной игре выпили зелье из слота 9."""
    icons = {"fishing": None, "crate": None, "sonar": None, "calm": None}

    def __init__(self, game):
        self.game = game

    def find(self, frame):
        return {"fishing": 1.0 if "9" in self.game.used else 0.0, "crate": 0.0, "sonar": 0.0, "calm": 0.0}


class TestPotions(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(af, n) for n in ("BUFFS_ON", "BUFF_WANT", "BUFF_METHOD", "BUFF_KEY", "HEALTH_GUARD",
                                                  "REEL_DELAY")}
        af.BUFFS_ON, af.BUFF_METHOD, af.HEALTH_GUARD, af.REEL_DELAY = True, "hotbar", False, 0.3
        af.BUFF_WANT = {"fishing": True, "crate": False, "sonar": False, "calm": False}
        self.game = FakeGame(selected="5")
        self.restore = self.game.install()

    def tearDown(self):
        self.restore()
        for n, v in self.saved.items():
            setattr(af, n, v)

    def fisher(self):
        f = af.Fisher()
        f.buffs = FakeBuffs(self.game)
        f.hotbar_frame = lambda sct, cl: self.game.screen()[:200, :self.game.W]
        f.park = (300, 300)
        f.rod_slot = 4
        return f

    def cl(self):
        return (0, 0, self.game.W, self.game.H)

    def test_potion_found_in_every_capture(self):
        f = self.fisher()
        for key in "1234567890":
            self.assertEqual(f.potion_slots(hotbar(key)), {"fishing": 8}, "выбран слот %s" % key)

    def test_drinks_from_hotbar_and_takes_rod_back(self):
        f = self.fisher()
        status = f.check_buffs(af.mss.MSS(), self.cl())
        self.assertEqual(self.game.keys, ["9", "5"])           # взял зелье, потом удочку
        self.assertEqual(self.game.used, ["9"])                 # выпил
        self.assertEqual(self.game.selected, "5")
        self.assertEqual(self.game.clicks, [])                  # не забрасывал
        self.assertEqual(status, {"fishing": True})

    def test_potion_not_in_hotbar(self):
        af.BUFF_WANT = {"fishing": False, "crate": True, "sonar": False, "calm": False}
        f = self.fisher()
        notes = []
        f.events = lambda k, d: notes.append((k, d))
        f.check_buffs(af.mss.MSS(), self.cl())
        self.assertEqual(self.game.keys, [])                    # ничего не нажимал
        self.assertIn("crate", f.buff_backoff)                  # и не будет пробовать каждые 20 с
        self.assertTrue(any(k == "notify" for k, _ in notes))

    def test_quick_buff_method(self):
        af.BUFF_METHOD = "quick"
        f = self.fisher()
        f.check_buffs(af.mss.MSS(), self.cl())
        self.assertEqual(self.game.keys, ["b"])

    def test_drinks_while_fishing(self):
        # рыбалка идёт, бафф кончился — между забросами выпил зелье и продолжил рыбачить
        r = Run(self.game)
        r.fisher.buffs = FakeBuffs(self.game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            self.assertEqual(self.game.used, ["9"])
            self.assertEqual(self.game.selected, "5")
            self.assertTrue(any(af.tr("Выпил: %s.") % af.tr("зелье рыбалки") == l for l in r.logs), r.logs)
            self.assertEqual(self.game.clicks, ["заброс"])
        finally:
            r.stop()


if __name__ == "__main__":
    unittest.main()
