"""
Отслеживание баффов (зелье рыбалки, ящичное зелье) по иконкам в левом верхнем углу игры.

Иконки баффов в игре рисуются полупрозрачными поверх фона: «иконка × прозрачность + фон».
Поэтому сравниваем нормированной корреляцией — она не зависит от яркости и сдвига цвета.
Иконки взяты с Terraria Wiki (terraria.wiki.gg), принадлежат Re-Logic.
"""
import os

import numpy as np

from pngread import read_png

BUFFS = ("fishing", "crate", "sonar", "calm")   # какие баффы умеем узнавать
SCALES = (1.0, 0.75, 1.25, 1.5, 1.75, 2.0)   # «Масштаб интерфейса» в настройках Terraria
THRESHOLD = 0.6                       # с такой уверенностью считаем, что бафф есть (ошибиться в сторону
                                      # «нет» не страшно: быстрый бафф не тратит зелье, если бафф ещё идёт)


def _resize(img, s):
    """Ближайший сосед (пиксельная графика)."""
    if abs(s - 1.0) < 1e-6:
        return img
    h, w = img.shape[:2]
    nh, nw = max(4, int(round(h * s))), max(4, int(round(w * s)))
    ys = (np.arange(nh) * h / nh).astype(int)
    xs = (np.arange(nw) * w / nw).astype(int)
    return img[ys][:, xs]


def _window_sums(a, h, w):
    ii = np.pad(a.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w]


def ncc_map(img, tmpl):
    """Нормированная корреляция шаблона со всеми местами кадра (через БПФ). Кадр и шаблон —
    (H, W, 3) float. Возвращает карту (H-h+1, W-w+1) со значениями от -1 до 1."""
    H, W = img.shape[:2]
    h, w = tmpl.shape[:2]
    if H < h or W < w:
        return np.zeros((0, 0))
    n = h * w
    t0 = tmpl - tmpl.mean(axis=(0, 1))
    tnorm = np.sqrt((t0 ** 2).sum()) + 1e-6
    num = 0.0
    var = 0.0
    for c in range(3):
        channel = img[:, :, c].astype(np.float64)
        conv = np.fft.irfft2(np.fft.rfft2(channel) * np.fft.rfft2(t0[::-1, ::-1, c], s=(H, W)), s=(H, W))
        num = num + conv[h - 1:, w - 1:]
        s1 = _window_sums(channel, h, w)
        s2 = _window_sums(channel * channel, h, w)
        var = var + np.maximum(s2 - s1 * s1 / n, 0)
    score = num / (np.sqrt(var) + 1e-6) / tnorm
    score[var < n * 3 * 16] = 0            # однотонный участок (разброс яркости < 4) — там иконки нет
    return np.clip(score, -1, 1)


class BuffWatcher:
    def __init__(self, asset_dir):
        self.icons = {}
        for name in BUFFS:
            rgba = read_png(os.path.join(asset_dir, "buff_%s.png" % name)).astype(np.float32)
            self.icons[name] = rgba[2:30, 2:30, 2::-1].copy()     # BGR, без прозрачных углов
        self.scale = None                                        # найденный масштаб интерфейса

    def find(self, frame):
        """Уверенность (0..1), что каждый бафф есть на кадре (левый верхний угол игры, BGR)."""
        scales = [self.scale] + [s for s in SCALES if s != self.scale] if self.scale else SCALES
        best = {name: 0.0 for name in self.icons}
        for s in scales:
            for name, icon in self.icons.items():
                m = ncc_map(frame, _resize(icon, s))
                if m.size:
                    best[name] = max(best[name], float(m.max()))
            if max(best.values()) >= THRESHOLD:
                self.scale = s                                   # дальше сначала пробуем этот масштаб
                break
        return best
