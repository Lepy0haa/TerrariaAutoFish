"""Окно игры: окна самой программы («Terraria AutoFish …» тоже начинаются с «Terraria») игрой
не считаются — иначе программа кликала бы в своё окно и не вставала на паузу."""
import unittest

from helpers import FakeGame, af


class TestWindow(unittest.TestCase):
    def test_game_window_rules(self):
        own = af.os.getpid()
        self.assertTrue(af.looks_like_game("Terraria: Водопад контента!", "terraria.exe", 1234))
        self.assertTrue(af.looks_like_game("tModLoader: мир", "dotnet.exe", 1234))
        self.assertFalse(af.looks_like_game("Terraria AutoFish 1.2.6", "terrariaautofish.exe", 1234))
        self.assertFalse(af.looks_like_game("Terraria: мир", "terrariaautofish.exe", 1234))
        self.assertFalse(af.looks_like_game("Terraria: мир", "python.exe", own))      # окно этой программы
        self.assertFalse(af.looks_like_game("Terraria Server v1.4.5", "terrariaserver.exe", 1234))
        self.assertFalse(af.looks_like_game("Проводник", "explorer.exe", 1234))

    def test_points_reset_during_cycle(self):
        # точки сбросили, пока шёл круг (например, пока пили зелья): круг просто заканчивается
        game = FakeGame()
        restore = game.install()
        try:
            f = af.Fisher()
            f.running.set()
            f.cast_point = None
            f.cycle(af.mss.MSS())
            self.assertEqual(game.clicks, [])
        finally:
            restore()


if __name__ == "__main__":
    unittest.main()
