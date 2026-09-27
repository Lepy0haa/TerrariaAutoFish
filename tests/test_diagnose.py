"""Диагностика на поддельной игре: что в порядке, что исправить."""
import unittest

from helpers import FakeGame, af

import diagnose


class TestDiagnose(unittest.TestCase):
    def run_diag(self, game, active=True):
        restore = game.install()
        try:
            f = af.Fisher()
            return diagnose.run(f, af.mss.MSS(), 1, active)
        finally:
            restore()

    def test_everything_visible(self):
        res = self.run_diag(FakeGame(selected="5"))
        text = diagnose.text(res)
        self.assertIn("Хотбар виден: выбран слот 5", text)
        self.assertIn("Удочка в слоте 5, наживка: 356", text)       # число наживки прочитано
        self.assertNotIn(diagnose.MARK[diagnose.BAD], text, text)

    def test_no_game_window(self):
        res = diagnose.run(af.Fisher(), None, None, False)
        self.assertEqual(res[0][0], diagnose.BAD)

    def test_inactive_window_warns(self):
        res = self.run_diag(FakeGame(selected="5"), active=False)
        self.assertEqual(res[0][0], diagnose.WARN)


if __name__ == "__main__":
    unittest.main()
