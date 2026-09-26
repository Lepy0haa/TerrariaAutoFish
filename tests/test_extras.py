"""Обновления, полный инвентарь, отчёт об улове, мастер первого запуска."""
import json
import os
import time
import unittest

import numpy as np

from helpers import FakeGame, Run, af

import catches
import updates
import wizard


class TestUpdates(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(updates.parse_version("v1.3.2"), (1, 3, 2))
        self.assertGreater(updates.parse_version("1.10.0"), updates.parse_version("1.9.9"))
        self.assertEqual(updates.parse_version("нет"), ())

    def test_newer(self):
        old = updates.latest
        try:
            updates.latest = lambda timeout=10: ("v9.0.0", "https://example/r")
            self.assertEqual(updates.newer("1.3.2"), ("9.0.0", "https://example/r"))
            updates.latest = lambda timeout=10: ("v1.3.2", "https://example/r")
            self.assertIsNone(updates.newer("1.3.2"))
        finally:
            updates.latest = old


class TestInventory(unittest.TestCase):
    def test_stops_when_catch_is_not_picked_up(self):
        f = af.Fisher()
        f.running.set()
        f.check_inventory(False)                     # надписи не было никогда — ничего не решаем
        f.check_inventory(False)
        f.check_inventory(False)
        self.assertTrue(f.running.is_set())
        f.check_inventory(True)                      # подобрал — надпись видна
        for _ in range(af.INV_FULL_HOOKS - 1):
            f.check_inventory(False)
        self.assertTrue(f.running.is_set())
        f.check_inventory(False)
        self.assertFalse(f.running.is_set())

    def test_flow(self):
        saved = {n: getattr(af, n) for n in ("REEL_DELAY", "HEALTH_GUARD", "BUFFS_ON", "SONAR_FILTER")}
        af.REEL_DELAY, af.HEALTH_GUARD, af.BUFFS_ON, af.SONAR_FILTER = 0.3, False, False, False
        game = FakeGame(selected="5")
        restore = game.install()
        r = Run(game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            game.catch_text = ("Окунь", (255, 255, 255))
            for n in range(2 + af.INV_FULL_HOOKS):   # +1: сразу после подбора надпись ещё видна
                if not r.fisher.running.is_set():
                    break
                if n == 1:
                    game.catch_text = None           # инвентарь полон — надписи о подборе больше нет
                time.sleep(0.8)
                hooks = r.fisher.hooks
                game.empty = True
                self.assertTrue(r.wait_for(lambda: r.fisher.hooks > hooks, 5), r.logs[-4:])
                game.empty = False
                r.wait_for(lambda: r.waiting() or not r.fisher.running.is_set(), 10)
            self.assertTrue(r.wait_for(lambda: not r.fisher.running.is_set(), 5), r.logs[-4:])
            self.assertTrue(any(af.tr("инвентарь полон") in l for l in r.logs), r.logs[-4:])
        finally:
            r.stop()
            restore()
            for n, v in saved.items():
                setattr(af, n, v)


class TestPickupStacks(unittest.TestCase):
    def test_same_text_stays_no_false_pause(self):
        # из игры: рыба клюёт каждые ~3 с, игра не пишет новую надпись о подборе, а прибавляет
        # число к ещё висящей старой — раньше это принималось за полный инвентарь
        saved = {n: getattr(af, n) for n in ("REEL_DELAY", "HEALTH_GUARD", "BUFFS_ON", "SONAR_FILTER")}
        af.REEL_DELAY, af.HEALTH_GUARD, af.BUFFS_ON, af.SONAR_FILTER = 0.3, False, False, False
        game = FakeGame(selected="5")
        restore = game.install()
        r = Run(game)
        try:
            r.toggle()
            self.assertTrue(r.wait_for(r.waiting, 20), r.logs[-5:])
            game.catch_text = ("Окунь", (255, 255, 255))
            game.pickup_life = 1000                  # надпись не пропадает между поклёвками
            for n in range(2 + af.INV_FULL_HOOKS):
                time.sleep(0.8)
                hooks = r.fisher.hooks
                game.empty = True
                self.assertTrue(r.wait_for(lambda: r.fisher.hooks > hooks, 5), r.logs[-4:])
                game.empty = False
                r.wait_for(lambda: r.waiting() or not r.fisher.running.is_set(), 10)
                self.assertTrue(r.fisher.running.is_set(), r.logs[-4:])
            self.assertTrue(r.fisher.running.is_set(), r.logs[-4:])
            self.assertFalse(any(af.tr("инвентарь полон") in l for l in r.logs), r.logs[-4:])
            self.assertEqual(sum(r.fisher.caught.values()) + r.fisher.caught_unknown, r.fisher.hooks)
        finally:
            r.stop()
            restore()
            for n, v in saved.items():
                setattr(af, n, v)


class TestReportAndWizard(unittest.TestCase):
    def test_catch_rows(self):
        import app
        c = catches.Catches(os.path.join(af.ASSET_DIR, "fishing", "catches.json"))
        bass = next(i for i, it in c.items.items() if it["en"] == "Bass")
        neon = next(i for i, it in c.items.items() if it["en"] == "Neon Tetra")

        class Fake:
            catch_data = c
            fisher = type("F", (), {"caught": {bass: 2, neon: 5}, "caught_unknown": 1, "skipped": 3,
                                    "hooks": 8, "started": time.time() - 1800})()
        rows = app.App.catch_rows(Fake())
        self.assertEqual([r[1] for r in rows], [5, 2])
        self.assertIn("8", app.App.catch_summary(Fake()))

    def test_wizard_pages(self):
        pages = wizard.pages("HOME", "END")
        self.assertEqual(len(pages), 4)
        self.assertIn("HOME", pages[-1][1])
        self.assertIn("END", pages[-1][1])


if __name__ == "__main__":
    unittest.main()


class TestGameNames(unittest.TestCase):
    """Названия улова из файлов перевода игры (как они лежат внутри Terraria.exe)."""

    def fake_exe(self):
        en = {"IronPickaxe": "Iron Pickaxe", "Obsidifish": "Obsidifish", "FlarefinKoi": "Flarefin Koi"}
        ru = {"IronPickaxe": "Железная кирка", "Obsidifish": "Обсидирыба", "FlarefinKoi": "Золотоперый карп"}
        for d in (en, ru):
            for k in range(1200):
                d["Filler%d" % k] = "x%d" % k
        blob = b"MZ\x00junk"
        for d, extra in ((en, ',\n}'), (ru, '\n}')):
            text = json.dumps({"ItemName": d}, ensure_ascii=False, indent=1)
            text = text[:-3] + extra + "\n}"             # в игре бывает лишняя запятая в конце
            blob += b"\x00\x01" + text.encode("utf-8") + b"\x00\xff\xfe"
        return blob

    def test_tables(self):
        import gamenames
        names = gamenames.english_to_russian(gamenames.read_tables(self.fake_exe()))
        self.assertEqual(gamenames.lookup(names, "Obsidifish"), "Обсидирыба")
        self.assertEqual(gamenames.lookup(names, "flarefin  koi"), "Золотоперый карп")

    def test_catches_use_game_names(self):
        import gamenames
        c = catches.Catches(os.path.join(af.ASSET_DIR, "fishing", "catches.json"))
        names = gamenames.english_to_russian(gamenames.read_tables(self.fake_exe()))
        self.assertEqual(c.use_game_names(names), 2)
        self.assertEqual(c.items[2315]["ru"], "Обсидирыба")
        self.assertEqual(c.identify_any(["Обсидирыба"])[0], 2315)
        self.assertEqual(c.identify_any(["Золотоперый карп"])[0], 2312)
        self.assertEqual(c.identify_any(["Карп-огнепёрка"])[0], 2312)          # название с Вики — запасное
