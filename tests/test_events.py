"""События в чате (кровавая луна, вторжения, боссы) и смерть персонажа."""
import time
import unittest

import numpy as np

from helpers import FakeGame, FakeSct, Run, af, hotbar, load_bgr

import chat
import ocr
import textimg

RU_OCR = any(lang.startswith("ru") for lang in ocr.available_languages())
GREEN, PURPLE = chat.COLORS_BGR


class Screen:
    """Экран 1680x1050: слева вверху — настоящий хотбар, справа вверху — настоящие сердечки."""
    W, H = 1680, 1050

    def __init__(self):
        self.corner = load_bgr("game", "top_right_full_hp.png")
        self.bar = hotbar("5")
        self.img = np.zeros((self.H, self.W, 3), np.float32)
        self.img[:self.bar.shape[0], :self.bar.shape[1]] = self.bar
        self.put(self.corner)

    def put(self, corner):
        self.img[:corner.shape[0], self.W - corner.shape[1]:] = corner

    def dead(self):
        """Сердечки пустые — как у погибшего персонажа (серые контуры без красного)."""
        c = self.corner.copy()
        red = af.heart_mask(c)
        c[red] = (60, 60, 60)
        self.put(c)


class TestDeath(unittest.TestCase):
    def setUp(self):
        self.scr = Screen()
        self.sct = FakeSct(lambda: self.scr.img)
        self.cl = (0, 0, Screen.W, Screen.H)
        self.f = af.Fisher()
        self.f.cast_point = (500, 600)
        self.f.running.set()

    def test_death_stops_completely(self):
        self.assertFalse(self.f.check_death(self.sct, self.cl))
        self.scr.dead()
        self.assertFalse(self.f.check_death(self.sct, self.cl))       # один кадр — ещё не смерть
        self.assertTrue(self.f.check_death(self.sct, self.cl))
        self.assertFalse(self.f.running.is_set())
        self.assertIsNone(self.f.resume_at)

    def test_fullscreen_map_is_not_death(self):
        self.f.check_death(self.sct, self.cl)
        self.scr.img[:] = 0                                           # весь интерфейс скрыт
        self.scr.put(self.scr.corner * 0.0)
        for _ in range(3):
            self.assertFalse(self.f.check_death(self.sct, self.cl))
        self.assertTrue(self.f.running.is_set())

    def test_death_during_event_cancels_resume(self):
        logs = []
        self.f.events = lambda k, d: logs.append(d.get("text", "")) if k == "log" else None
        self.f.check_death(self.sct, self.cl)
        self.f.running.clear()                                        # пережидаем кровавую луну
        self.f.event, self.f.resume_at = "blood_moon", time.time() + 500
        self.scr.dead()
        self.f.check_death(self.sct, self.cl)
        self.assertTrue(self.f.check_death(self.sct, self.cl))
        self.assertIsNone(self.f.resume_at)
        self.assertIsNone(self.f.event)
        self.assertTrue(any("Кровавая луна" in l and "совсем" in l for l in logs), logs)


@unittest.skipUnless(RU_OCR, "нет русского распознавания текста Windows")
class TestChatMessages(unittest.TestCase):
    def check(self, text, color, want):
        g = FakeGame()
        g.chat_text = (text, color)
        s = g.screen()
        reg = chat.region((0, 0, g.W, g.H))
        fr = s[reg["top"]:reg["top"] + reg["height"], reg["left"]:reg["left"] + reg["width"]]
        self.assertEqual(chat.classify(chat.event_texts(fr)), want, text)

    def test_messages(self):
        for text, color, want in (
                ("Восходит кровавая луна...", GREEN, ("start", "blood_moon")),
                ("Восходит тыквенная луна...", GREEN, ("start", "pumpkin_moon")),
                ("Армия гоблинов прибыла!", PURPLE, ("start", "goblins")),
                ("Армия гоблинов побеждена!", PURPLE, ("end", "goblins")),
                ("Босс Глаз Ктулху пробудился!", PURPLE, ("start", "boss")),
                ("The Blood Moon is rising...", GREEN, ("start", "blood_moon")),
                ("Ваш мир благословлён кобальтом!", GREEN, None)):
            self.check(text, color, want)


@unittest.skipUnless(RU_OCR, "нет русского распознавания текста Windows")
class TestEventFlow(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(af, n) for n in ("REEL_DELAY", "HEALTH_GUARD", "BUFFS_ON", "SONAR_FILTER",
                                                  "CHAT_EVERY")}
        af.REEL_DELAY, af.HEALTH_GUARD, af.BUFFS_ON, af.SONAR_FILTER, af.CHAT_EVERY = 0.3, False, False, False, 0.3
        self.game = FakeGame(selected="5")
        self.restore = self.game.install()

    def tearDown(self):
        self.restore()
        for n, v in self.saved.items():
            setattr(af, n, v)

    def test_wait_out_and_continue(self):
        r = Run(self.game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            self.game.chat_text = ("Армия гоблинов прибыла!", PURPLE)
            self.assertTrue(r.wait_for(lambda: not r.fisher.running.is_set(), 10), r.logs[-4:])
            self.assertEqual(r.fisher.event, "goblins")
            self.assertGreater(r.fisher.resume_at, time.time() + 60)
            self.assertTrue(any("вытащил поплавок" in l for l in r.logs), r.logs[-4:])
            # гоблинов победили — продолжаем, не дожидаясь таймера
            r.fisher.chat_ignore_until = 0
            self.game.chat_text = ("Армия гоблинов побеждена!", PURPLE)
            self.assertTrue(r.wait_for(lambda: r.fisher.running.is_set(), 10), r.logs[-4:])
            self.game.chat_text = None
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            self.assertIsNone(r.fisher.event)
        finally:
            r.stop()


if __name__ == "__main__":
    unittest.main()
