"""Зелья из хотбара: программа находит нужное зелье (на снимках из игры в слоте 9 — зелье
рыбалки), берёт его цифрой слота, пьёт кликом и снова берёт удочку (слот 5)."""
import unittest

from helpers import FakeGame, Run, af, hotbar, load_bgr

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

    def test_single_potion_without_number(self):
        # снимок игрока: рыбалка в слоте 7 (с числом), сонар в 8 (с числом), ящичное зелье в 9 —
        # одно, игра число не пишет; в руках телефон (слот 0), удочка в слоте 5
        img = load_bgr("hotbar", "single_crate_potion.png")
        f = self.fisher()
        self.assertEqual(f.potion_slots(img), {"fishing": 6, "sonar": 7, "crate": 8})
        self.assertEqual(f.rods.find(img)[0], 4)

    def test_yellow_garland_behind_hotbar(self):
        # снимок игрока: за хотбаром гирлянда с жёлтыми огоньками — раньше она «прилипала» к жёлтой
        # заливке выбранного слота, раскладка слотов съезжала и не находились ни зелья, ни удочка
        import hotbar
        img = load_bgr("hotbar", "garland_crate_potion.png")
        sel = hotbar.selected_slot(img)
        self.assertEqual(sel[0], 5)
        x0, y0, x1, y1 = sel[2]
        self.assertLessEqual(abs((y1 - y0) - (x1 - x0)), 4)       # слот квадратный
        f = self.fisher()
        self.assertEqual(f.potion_slots(img), {"crate": 8})
        self.assertEqual(f.rods.find(img)[0], 5)

    def test_potion_retry_is_short_and_manual_check_resets_it(self):
        af.BUFF_WANT = {"fishing": False, "crate": True, "sonar": False, "calm": False}
        f = self.fisher()
        f.check_buffs(af.mss.MSS(), self.cl())                  # ящичного зелья в хотбаре нет
        self.assertLessEqual(f.buff_backoff["crate"] - af.time.time(), af.POTION_RETRY + 1)
        f.check_buffs(af.mss.MSS(), self.cl(), force=True)      # «Проверить баффы сейчас»
        self.assertEqual(f.buff_backoff, {})

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

    def test_absent_potions_one_reminder(self):
        # из журнала игрока: каждую минуту по три строки «Нет … в хотбаре» — теперь одна строка на
        # все зелья, и повтор только если список изменился (или раз в 10 минут)
        f = self.fisher()
        logs = []
        f.events = lambda k, d: logs.append(d["text"]) if k == "log" else None
        f.report_absent(["fishing", "crate", "sonar"])
        self.assertEqual(len(logs), 1)
        for n in ("рыбалки", "ящичное", "сонара"):
            self.assertIn(n, logs[0])
        f.report_absent(["sonar", "crate", "fishing"])      # тот же список — молчим
        self.assertEqual(len(logs), 1)
        f.report_absent(["sonar"])                          # список изменился — одна строка
        self.assertEqual(len(logs), 2)
        f.absent_told -= af.POTION_NAG_EVERY + 1            # прошло 10 минут — напомнить
        f.report_absent(["sonar"])
        self.assertEqual(len(logs), 3)
        af.POTION_REMIND = False
        try:
            f.report_absent(["fishing"])
            self.assertEqual(len(logs), 3)
        finally:
            af.POTION_REMIND = True

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
