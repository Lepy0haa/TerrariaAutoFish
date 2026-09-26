"""Выбор улова по зелью сонара: какой предмет по надписи (с ошибками OCR), ловить ли его в этом
биоме, чтение надписи на кадре из игры и сценарий целиком в поддельной игре."""
import os
import time
import unittest

import numpy as np

from helpers import FakeGame, Run, af, load_bgr

import catches
import ocr
import sonar
import textimg

RU_OCR = any(lang.startswith("ru") for lang in ocr.available_languages())   # названия в тестах русские

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


class TestRealFont(unittest.TestCase):
    """Настоящие надписи шрифтом Terraria (названия предметов над хотбаром на снимках из игры):
    OCR читает их с ошибками, но из известного списка предмет выбирается уверенно — или не
    выбирается вовсе (а не выбирается неправильный)."""

    @unittest.skipUnless(RU_OCR, "нет русского распознавания текста Windows")
    def test_terraria_font(self):
        import numpy as np
        from helpers import hotbar as hb_img
        c = catches.Catches(DATA)
        extra = {99991: "Шипохват", 99992: "Удочка механика", 99993: "Мобильный телефон"}
        for i, n in extra.items():
            c.items[i] = {"ru": n, "en": n}
            c.names.append((catches.normalize(n, True), i))
        right = 0
        for key, want in (("1", 99991), ("5", 99992), (None, 99993)):
            img = (hb_img(key) if key else load_bgr("hotbar", "single_crate_potion.png"))[0:24, 100:460]
            rd = sonar.TextReader(1.0)
            rd.set_base(np.zeros_like(img) + np.array([240, 120, 60], np.float32))
            frame = np.where((img.min(2) > 200)[:, :, None], img, rd.base)     # только буквы появились
            got = c.identify_any(rd.read_all(frame))[0]
            self.assertIn(got, (want, None), "выбран не тот предмет")
            right += got == want
        self.assertGreaterEqual(right, 2)


class TestTextMemory(unittest.TestCase):
    """Память надписей: названия с настоящих снимков игры запоминаются и потом узнаются по образцу
    (сдвиг, чуть другой порог выделения), а разные названия не путаются."""

    def masks(self):
        from helpers import hotbar as hb_img
        out = {}
        for i, key in ((1, "1"), (2, "5"), (3, None)):
            img = (hb_img(key) if key else load_bgr("hotbar", "single_crate_potion.png"))[0:24, 100:460]
            out[i] = img
        return out

    def test_learn_and_match(self):
        import numpy as np
        import textmemory
        mem = textmemory.TextMemory()
        imgs = self.masks()
        for i, img in imgs.items():
            self.assertTrue(mem.learn(img.min(2) > 200, i))
        self.assertFalse(mem.learn(imgs[1].min(2) > 200, 1))          # такой образец уже есть
        for i, img in imgs.items():
            hit = mem.match(np.roll(img.min(2) > 200, 1, axis=1))
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0], i)
        self.assertIsNone(mem.match(textimg.render("Окунь", 16)))      # незнакомое — не узнаётся

    def test_saved_to_disk(self):
        import tempfile
        import textmemory
        path = os.path.join(tempfile.mkdtemp(), "names.npz")
        img = self.masks()[2]
        textmemory.TextMemory(path).learn(img.min(2) > 200, 7)
        again = textmemory.TextMemory(path)
        self.assertEqual(again.count(), 1)
        self.assertEqual(again.match(img.min(2) > 200)[0], 7)


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


class TestLavaBackground(unittest.TestCase):
    """Над лавой фон всё время «переливается»: раньше это принималось за надпись (она будто висела
    всегда), и появление настоящей надписи сонара не замечалось."""

    def frames(self):
        big = load_bgr("bobber", "lava_sonar_region.png", down=2)
        # та же лава, переливы чуть сдвинуты (на 1 и 2 пикселя)
        return big[2:-2, 4:-4], big[1:-3, 2:-6]

    def test_shimmer_is_not_text(self):
        base, shimmer = self.frames()
        rd = sonar.SonarReader(1.0)
        rd.set_base(base)
        self.assertIsNone(rd.extract(shimmer))

    def test_text_over_lava(self):
        base, shimmer = self.frames()
        frame = textimg.put_text(shimmer, "Обсидирыба", (230, 90, 60), 150, 60)
        rd = sonar.SonarReader(1.0)
        rd.set_base(base)
        self.assertIsNotNone(rd.extract(frame))
        y0, y1, x0, x1 = rd.crop(rd.text_mask(frame))
        self.assertLessEqual(abs(x0 - 150), 6)
        self.assertLess(y1 - y0, 30)                              # одна строка, а не весь кадр
        if RU_OCR:
            c = catches.Catches(DATA)
            c.use_game_names({"obsidifish": "Обсидирыба"})     # название, как в игре
            texts = rd.read_all(frame)
            self.assertEqual(c.identify_any(texts)[0], 2315, texts)


@unittest.skipUnless(RU_OCR, "нет русского распознавания текста Windows")
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
            got = self.rd.read_all(textimg.put_text(self.base, text, color, 20, 30))
            i = c.identify_any(got)[0]
            self.assertIsNotNone(i, "%s -> %r" % (text, got))

    def test_no_text(self):
        self.assertEqual(self.rd.read(self.base.copy()), "")


@unittest.skipUnless(RU_OCR, "нет русского распознавания текста Windows")
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

    def test_text_alone_is_a_bite(self):
        # поплавок ещё не нырнул, а надпись сонара уже появилась — это поклёвка
        r = Run(self.game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            time.sleep(1.0)
            self.game.bite_text, self.game.sonar_now = ("Старый ботинок", (170, 170, 170)), True
            self.assertTrue(r.wait_for(lambda: r.fisher.skipped == 1, 5), r.logs[-4:])      # мусор — пропуск
            self.assertEqual(r.fisher.hooks, 0)
            self.game.sonar_now, self.game.bite_text = False, None
            time.sleep(1.5)
            self.game.bite_text, self.game.sonar_now = ("Окунь", (255, 255, 255)), True
            self.assertTrue(r.wait_for(lambda: r.fisher.hooks == 1, 5), r.logs[-4:])        # окунь — подсечка
            self.assertTrue(r.wait_for(lambda: any(af.tr("надпись сонара") in l for l in r.logs), 3), r.logs[-4:])
        finally:
            self.game.sonar_now, self.game.bite_text = False, None
            r.stop()

    def test_angler_quest_fish(self):
        # задание рыбака: поймали нужную рыбу (по надписи о подборе) — пауза
        c = catches.Catches(DATA)
        derp = by_ru(c, "Рыба-крикун")
        saved = af.QUEST_FISH
        af.QUEST_FISH, af.SONAR_FILTER, af.CATCH_WANT = derp, False, {}
        r = Run(self.game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            time.sleep(1.0)
            self.game.catch_text = ("Рыба-крикун", (255, 150, 150))
            self.game.empty = True
            self.assertTrue(r.wait_for(lambda: not r.fisher.running.is_set(), 8), r.logs[-4:])
            self.game.empty = False
            self.assertTrue(any(af.tr("Поймал рыбу для задания рыбака: %s!") % "Рыба-крикун" == l for l in r.logs),
                            r.logs[-4:])
        finally:
            af.QUEST_FISH = saved
            self.game.catch_text = None
            r.stop()

    def test_biome_from_what_was_caught(self):
        # сонара нет — биом угадывается по надписи о подборе над персонажем после подсечки
        af.SONAR_FILTER = False
        af.CATCH_WANT = {}
        r = Run(self.game)
        events = []
        old = r.event
        r.fisher.events = lambda k, d: (events.append((k, d)), old(k, d))
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            for name in ("Голубой неон", "Двойная треска"):
                time.sleep(1.0)
                self.game.catch_text = (name, (255, 150, 150))
                n = r.fisher.hooks
                self.game.empty = True
                self.assertTrue(r.wait_for(lambda: r.fisher.hooks > n, 5))
                self.game.empty = False
                self.assertTrue(r.wait_for(lambda: any(af.tr("Поймал: %s.") % name == l for l in r.logs), 5),
                                r.logs[-4:])
                r.wait_for(r.waiting, 10)
            self.assertEqual(r.fisher.current_biome(), "jungle")
            self.assertTrue(any(k == "catch" and d.get("caught") for k, d in events))
        finally:
            r.stop()


if __name__ == "__main__":
    unittest.main()
