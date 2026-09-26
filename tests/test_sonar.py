"""Выбор улова по зелью сонара: какой предмет по надписи (с ошибками OCR), ловить ли его в этом
биоме, чтение надписи на кадре из игры и сценарий целиком в поддельной игре."""
import os
import time
import unittest

from helpers import FakeGame, Run, af, load_bgr

import catches
import ocr
import sonar
import textimg

DATA = os.path.join(af.ASSET_DIR, "fishing", "catches.json")


def by_ru(c, name):
    return next(i for i, it in c.items.items() if it["ru"] == name)


class TestCatches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = catches.Catches(DATA)

    def test_data(self):
        self.assertGreaterEqual(len(self.c.items), 100)
        keys = [g["key"] for g in self.c.groups]
        for k in ("forest", "ocean", "jungle", "snow", "desert", "corruption", "crimson", "hallow",
                  "dungeon", "space", "lava", "honey", "crates", "rare", "junk"):
            self.assertIn(k, keys)
        jungle = {it["ru"] for it in self.c.group["jungle"]["items"]}
        self.assertIn("Голубой неон", jungle)
        self.assertIn("Ящик джунглей", jungle)

    def test_identify_with_ocr_mistakes(self):
        c = self.c
        cases = {"Окунь": "Окунь", "Oкунь": "Окунь", "Bass": "Окунь", "Яшик джунглеи": "Ящик джунглей",
                 "Тропическая бapракуда": "Тропическая барракуда", "Neon Tetra": "Голубой неон",
                 "СТАРЫЙ БОТИНОК": "Старый ботинок", "Золотой карп.": "Золотой карп"}
        for text, want in cases.items():
            i, _ = c.identify(text)
            self.assertIsNotNone(i, text)
            self.assertEqual(c.items[i]["ru"], want, text)
        self.assertIsNone(c.identify("Мусор")[0])
        self.assertIsNone(c.identify("")[0])

    def test_guess_biome(self):
        c = self.c
        seen = [by_ru(c, "Голубой неон"), by_ru(c, "Двойная треска"), by_ru(c, "Старый ботинок")]
        self.assertEqual(c.guess_biome(seen), "jungle")
        self.assertIsNone(c.guess_biome([by_ru(c, "Старый ботинок")]))      # мусор — везде

    def test_wanted_per_biome(self):
        c = self.c
        truffle = by_ru(c, "Чешуйчатый трюфель")           # есть и в Порче, и в Святых землях
        want = {"corruption": [truffle], "hallow": []}
        self.assertTrue(c.wanted(truffle, want, "corruption"))
        self.assertFalse(c.wanted(truffle, want, "hallow"))
        boot = by_ru(c, "Старый ботинок")
        self.assertFalse(c.wanted(boot, {"junk": []}, "jungle"))
        self.assertTrue(c.wanted(boot, {"jungle": []}, "jungle"))            # список мусора не менялся


class TestFlash(unittest.TestCase):
    def test_text_is_not_lightning(self):
        # надпись сонара в верхних строках окошка — не вспышка молнии (раньше поклёвка под
        # надписью пропускалась); вспышка всего кадра — по-прежнему вспышка
        import numpy as np
        frame = load_bgr("bobber", "025_poisk.png", down=4)[20:78, 28:66]
        det = af.BiteDetector(np.array([[0.0, 180.0, 240.0]]))
        det.feed(frame, 0.0)
        with_text = frame.copy()
        with_text[:6, 5:33] = (170, 170, 170)
        det.feed(with_text, 0.02)
        self.assertFalse(det.flash)
        det.feed(np.clip(frame * 2.5 + 60, 0, 255), 0.04)
        self.assertTrue(det.flash)


@unittest.skipUnless(ocr.available_languages(), "нет распознавания текста Windows")
class TestReader(unittest.TestCase):
    def setUp(self):
        self.bg = load_bgr("bobber", "029_poisk_shiroko.png", down=4)       # ночь, вода, пирс
        self.rd = sonar.SonarReader(1.0)
        self.reg = self.rd.region((150, 108), (0, 0, self.bg.shape[1], self.bg.shape[0]))
        r = self.reg
        self.base = self.bg[r["top"]:r["top"] + r["height"], r["left"]:r["left"] + r["width"]]
        self.rd.set_base(self.base)

    def test_reads_names(self):
        c = catches.Catches(DATA)
        for text, color in (("Окунь", (255, 255, 255)), ("Ящик джунглей", (60, 200, 60)),
                            ("Голубой неон", (255, 150, 150)), ("Neon Tetra", (255, 150, 150))):
            got = self.rd.read(textimg.put_text(self.base, text, color, 20, 30))
            i, _ = c.identify(got)
            self.assertIsNotNone(i, "%s -> %r" % (text, got))

    def test_no_text(self):
        self.assertEqual(self.rd.read(self.base.copy()), "")


@unittest.skipUnless(ocr.available_languages(), "нет распознавания текста Windows")
class TestSonarFlow(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(af, n) for n in ("SONAR_FILTER", "CATCH_WANT", "CATCH_BIOME", "REEL_DELAY",
                                                  "HEALTH_GUARD", "BUFFS_ON")}
        c = catches.Catches(DATA)
        af.SONAR_FILTER, af.CATCH_BIOME, af.REEL_DELAY, af.HEALTH_GUARD, af.BUFFS_ON = True, "auto", 0.3, False, False
        af.CATCH_WANT = {"junk": set()}                      # мусор не ловим, остальное — да
        self.boot, self.bass = by_ru(c, "Старый ботинок"), by_ru(c, "Окунь")
        self.game = FakeGame(selected="5")
        self.restore = self.game.install()

    def tearDown(self):
        self.restore()
        for n, v in self.saved.items():
            setattr(af, n, v)

    def bite(self, r, text, color):
        g = self.game
        g.bite_text = (text, color)
        g.empty = True
        time.sleep(0.8)
        g.empty = False
        g.bite_text = None

    def test_skips_unwanted_and_hooks_wanted(self):
        r = Run(self.game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            time.sleep(1.2)
            casts = self.game.clicks.count("заброс")
            self.bite(r, "Старый ботинок", (170, 170, 170))       # мусор — не подсекаем
            time.sleep(0.5)
            self.assertEqual(r.fisher.hooks, 0, r.logs[-4:])
            self.assertEqual(r.fisher.skipped, 1, r.logs[-4:])
            self.assertEqual(self.game.clicks.count("вытащил"), 0)
            time.sleep(1.2)
            self.bite(r, "Окунь", (255, 255, 255))                 # окунь — подсекаем
            self.assertTrue(r.wait_for(lambda: r.fisher.hooks == 1, 5), r.logs[-4:])
            self.assertTrue(any(af.tr("Сонар: клюёт «%s» — не отмечено, пропускаю.") % "Старый ботинок" == l
                                for l in r.logs), r.logs)
            self.assertTrue(any("Окунь" in l and af.tr("Подсекаю")[:6] in l for l in r.logs), r.logs[-4:])
            self.assertGreaterEqual(self.game.clicks.count("заброс"), casts)
        finally:
            r.stop()


if __name__ == "__main__":
    unittest.main()
