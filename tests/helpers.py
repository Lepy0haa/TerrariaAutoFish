"""Общее для тестов: загрузка картинок и «поддельная игра».

Картинки — настоящие снимки из игры (tests/data): хотбар, зоны поиска поплавка из режима
записи, записи поклёвок. Поддельная игра подменяет в autofish окно, экран, мышь и клавиши:
экран собирается из снимков, клик забрасывает или вытаскивает поплавок, цифры 1–0 меняют
выбранный слот хотбара (показывается снимок с этим выбранным слотом).
"""
import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import autofish as af  # noqa: E402
from pngread import read_png  # noqa: E402

af.SOUND = False
af.log = lambda msg: None              # в тестах не печатаем журнал в консоль


def load_bgr(*parts, down=1):
    """PNG из tests/data как BGR float32. down — уменьшить в столько раз (картинки поиска
    сохранены увеличенными в 4 раза); зелёная отладочная рамка при этом убирается."""
    img = read_png(os.path.join(DATA, *parts))[::down, ::down, :3][:, :, ::-1].astype(np.float32).copy()
    if down > 1:
        g = (img[:, :, 1] > 200) & (img[:, :, 0] < 60) & (img[:, :, 2] < 60)
        for y, x in zip(*np.nonzero(g)):
            img[y, x] = img[y, x - 2] if x >= 2 else img[y, x + 2]
    return img


_hotbars = {}


def hotbar(key):
    """Снимок хотбара из игры, где выбран слот key ("1".."0"); удочка — в слоте 5.
    Возвращается копия (кэш — чтобы поддельная игра не распаковывала PNG на каждом кадре)."""
    if key not in _hotbars:
        _hotbars[key] = load_bgr("hotbar", "sel_%s.png" % key)
    return _hotbars[key].copy()


class FakeSct:
    def __init__(self, screen):
        self.screen = screen

    def grab(self, reg):
        a = self.screen()[reg["top"]:reg["top"] + reg["height"], reg["left"]:reg["left"] + reg["width"]]
        return np.dstack([a, np.zeros(a.shape[:2])])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class FakeGame:
    """Вода с поплавком из настоящей записи, сверху — настоящий хотбар.
    Поплавок летит 0.8 с после заброса и садится в (BX, BY)."""
    W, OFF = 560, 448

    def __init__(self, selected="5", night=False):
        z = load_bgr("bobber", "025_poisk.png", down=4)
        water = np.concatenate([z[:, 0:30]] * 20, axis=1)[:, :self.W]
        self.canvas = np.concatenate([np.repeat(water[:1], self.OFF, 0), water, np.repeat(water[-1:], 60, 0)], 0)
        self.H = self.canvas.shape[0]
        self.patch = z[26:58, 30:64]                 # поплавок из записи вместе с водой вокруг
        self.BX, self.BY = 150, self.OFF + 41
        self.out = False                             # поплавок заброшен
        self.cast_t = 0.0
        self.empty = False                           # «кончилась наживка»: поплавка не видно
        self.night = night
        self.decoy = False
        self.selected = selected
        self.clicks, self.keys, self.used = [], [], []
        self.cursor = (self.BX, self.OFF)
        self.lock = threading.Lock()

    def screen(self):
        s = self.canvas.copy()
        bar = _hotbars.get(self.selected)
        if bar is None:
            bar = hotbar(self.selected)
        bar = bar[:148, :self.W]
        s[:bar.shape[0], :bar.shape[1]] = bar
        if self.decoy:                               # яркий квадрат рядом с поплавком (не поплавок)
            s[self.BY - 14:self.BY - 2, self.BX + 28:self.BX + 40] = (40, 40, 220)
        if self.out and not self.empty:
            fly = time.time() - self.cast_t
            cx, cy = ((self.BX, self.BY) if fly > 0.8 else
                      (int(self.BX - 40 * (0.8 - fly)), int(self.BY - 30 * (0.8 - fly))))
            s[cy - 16:cy + 16, cx - 17:cx + 17] = self.patch
        if self.night:
            s = s * 0.3 + np.array([30, 28, 26], np.float32)
        return s

    def click(self, x, y, hold=0.06):
        with self.lock:
            if self.selected != "5":                 # в руках не удочка: клик — использовать предмет
                self.used.append(self.selected)      # (зелье в слоте 9 — выпить)
                return
            if self.out:
                self.out = False
                self.clicks.append("вытащил")
            else:
                self.out = True
                self.cast_t = time.time()
                self.clicks.append("заброс")

    def press_key(self, name):
        self.keys.append(name)
        if name in "1234567890" and len(name) == 1:
            self.selected = name
            self.out = False                         # сменили предмет — игра убирает поплавок

    def install(self):
        """Подменить в autofish всё, что связано с игрой. Возвращает функцию отката."""
        saved = {n: getattr(af, n) for n in ("terraria_window", "client_rect", "get_cursor", "set_cursor",
                                              "click", "press_key", "find_terraria")}
        saved_mss = getattr(af.mss, "MSS", None)
        af.terraria_window = lambda: 1
        af.find_terraria = lambda: 1
        af.client_rect = lambda h: (0, 0, self.W, self.H)
        af.get_cursor = lambda: self.cursor
        af.set_cursor = lambda x, y: None
        af.click = self.click
        af.press_key = self.press_key
        af.mss.MSS = lambda: FakeSct(self.screen)

        def restore():
            for n, v in saved.items():
                setattr(af, n, v)
            if saved_mss is None:
                del af.mss.MSS
            else:
                af.mss.MSS = saved_mss
        return restore


class Run:
    """Движок, запущенный на поддельной игре: события собираются для проверок."""

    def __init__(self, game, **kw):
        self.game = game
        self.states, self.logs, self.gear = [], [], []
        self.fisher = af.Fisher(events=self.event, **kw)
        self.fisher.listeners = []
        threading.Thread(target=self.fisher.worker, daemon=True).start()

    def event(self, kind, d):
        if kind == "state":
            self.states.append(d["title"])
        elif kind == "log":
            self.logs.append(d["text"])
        elif kind == "gear":
            self.gear.append(d)

    def state(self):
        return self.states[-1] if self.states else None

    def wait_for(self, cond, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def waiting(self):
        return self.state() == af.tr("Жду поклёвку")

    def toggle(self):
        self.fisher.on_toggle()

    def pause(self):
        self.fisher.on_toggle()
        self.wait_for(lambda: not self.fisher.running.is_set())
        time.sleep(0.3)

    def stop(self):
        self.fisher.shutdown()
        time.sleep(0.2)
