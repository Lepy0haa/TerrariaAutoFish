"""Сценарии целиком: движок рыбачит в «поддельной игре» (настоящие снимки поплавка и хотбара),
как будто игрок нажимает HOME, ставит паузу, берёт другой предмет, кончается наживка и т. д."""
import time
import unittest

from helpers import FakeGame, Run, af

ROD = 4


class TestFlow(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(af, n) for n in ("REEL_DELAY", "RECOVER_EVERY", "ROD_SLOT", "AUTO_MARK", "AUTO_ROD")}
        af.REEL_DELAY, af.RECOVER_EVERY = 0.3, 0.5
        af.ROD_SLOT, af.AUTO_MARK, af.AUTO_ROD = None, True, True
        self.game = FakeGame(selected="5")
        self.restore = self.game.install()
        self.run_ = Run(self.game)

    def tearDown(self):
        self.run_.stop()
        self.restore()
        for n, v in self.saved.items():
            setattr(af, n, v)

    def start_and_wait(self):
        r, g = self.run_, self.game
        r.toggle()
        self.assertTrue(r.wait_for(r.waiting, 20), "не дождался слежения: %s" % r.logs[-5:])

    def test_first_start_finds_bobber_and_remembers_rod(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        f = r.fisher
        self.assertEqual(g.clicks, ["заброс"])
        self.assertEqual(f.bobber_kind, "acc_glowing")
        self.assertLessEqual(abs(f.mark[0] - g.BX), 6)     # поплавок во вставке чуть правее середины
        self.assertEqual(f.rod_slot, ROD)                     # удачный заброс со слота 5 — запомнили
        self.assertTrue(any(d.get("rod_slot") == ROD for d in r.gear))

    def test_pause_and_resume(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        # пауза, поплавок в воде -> продолжить: не кликать, сразу следить
        r.pause()
        n = len(g.clicks)
        r.toggle()
        self.assertTrue(r.wait_for(r.waiting, 15))
        self.assertEqual(g.clicks[n:], [])
        # пауза, игрок сам вытащил поплавок -> продолжить: заброс
        r.pause()
        g.out, n = False, len(g.clicks)
        r.toggle()
        self.assertTrue(r.wait_for(r.waiting, 15))
        self.assertEqual(g.clicks[n:], ["заброс"])

    def test_takes_rod_back(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        r.pause()
        g.press_key("1")                                      # игрок взял кнут (поплавок пропал)
        g.keys, n = [], len(g.clicks)
        r.toggle()
        self.assertTrue(r.wait_for(r.waiting, 15))
        self.assertEqual(g.keys, ["5"])
        self.assertEqual(g.selected, "5")
        self.assertEqual(g.clicks[n:], ["заброс"])

    def test_bite_is_hooked_and_recast(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        time.sleep(0.6)                                       # поплавок спокойно полежал
        g.empty = True                                        # клюнуло: поплавок ушёл под воду
        self.assertTrue(r.wait_for(lambda: r.fisher.hooks == 1, 5), r.logs[-5:])
        g.empty = False
        self.assertTrue(r.wait_for(lambda: g.clicks.count("заброс") == 2 and r.waiting(), 10))

    def test_cast_to_watching_is_fast(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        for _ in range(2):
            r.pause()
            g.out = False
            r.toggle()
            self.assertTrue(r.wait_for(lambda: g.out, 5))
            t0 = g.cast_t
            self.assertTrue(r.wait_for(r.waiting, 10))
            # поплавок в игре летит 0.8 с — следить начинаем вскоре после того, как сел
            self.assertLess(time.time() - t0, 1.5)

    def test_out_of_bait_recovers(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        r.pause()
        g.out, g.empty = False, True                         # наживка кончилась: поплавка нет
        r.toggle()
        self.assertTrue(r.wait_for(lambda: any(af.tr("попробую снова")[:12] in l for l in r.logs), 30),
                        r.logs[-6:])
        g.empty = False                                       # наживку добавили
        self.assertTrue(r.wait_for(r.waiting, 30), r.logs[-6:])
        self.assertTrue(r.fisher.running.is_set())

    def test_night_resume(self):
        r, g = self.run_, self.game
        self.start_and_wait()
        r.pause()
        g.night, n = True, len(g.clicks)
        r.toggle()
        self.assertTrue(r.wait_for(r.waiting, 15))
        self.assertEqual(g.clicks[n:], [])


if __name__ == "__main__":
    unittest.main()
