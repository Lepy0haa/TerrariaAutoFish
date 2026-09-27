"""
Поиск спрайтов Terraria (удочки в хотбаре, поплавки на воде) на снимке экрана.

Спрайты взяты с Terraria Wiki (terraria.wiki.gg) и принадлежат Re-Logic. У спрайтов есть
прозрачные места — сравниваем только непрозрачные пиксели (маска) и нормированной корреляцией:
она не зависит от яркости и оттенка (ночь, полупрозрачный фон слотов, подкраска водой).
"""
import os

import numpy as np

from pngread import read_png

ROD_NAMES = {
    "wood": "Wood Fishing Pole", "reinforced": "Reinforced Fishing Pole", "fisher_of_souls": "Fisher of Souls",
    "fleshcatcher": "Fleshcatcher", "chum_caster": "Chum Caster", "scarab": "Scarab Fishing Rod",
    "fiberglass": "Fiberglass Fishing Pole", "mechanics": "Mechanic's Rod",
    "sitting_duck": "Sitting Duck's Fishing Pole", "hotline": "Hotline Fishing Hook", "golden": "Golden Fishing Rod",
}
BOBBER_NAMES = dict(ROD_NAMES, **{
    "acc_fishing_bobber": "Fishing Bobber", "acc_glowing": "Glowing Fishing Bobber",
    "acc_lava_moss": "Lava Moss Fishing Bobber", "acc_krypton_moss": "Krypton Moss Fishing Bobber",
    "acc_xenon_moss": "Xenon Moss Fishing Bobber", "acc_argon_moss": "Argon Moss Fishing Bobber",
    "acc_neon_moss": "Neon Moss Fishing Bobber", "acc_helium_moss": "Helium Moss Fishing Bobber",
})


def resize(img, s):
    """Ближайший сосед (пиксельная графика)."""
    h, w = img.shape[:2]
    nh, nw = max(3, int(round(h * s))), max(3, int(round(w * s)))
    ys = np.minimum((np.arange(nh) / s).astype(int), h - 1)
    xs = np.minimum((np.arange(nw) / s).astype(int), w - 1)
    return img[ys][:, xs]


class Sprite:
    def __init__(self, name, rgba, part=1.0, penalty=0.0):
        """part — какую верхнюю долю спрайта сравнивать (у поплавка низ под водой).
        penalty — сколько вычесть из совпадения (у верхушки поменьше похожего меньше примет)."""
        h = max(3, int(round(rgba.shape[0] * part)))
        rgba = rgba[:h]
        ys, xs = np.nonzero(rgba[:, :, 3] > 0)                    # обрезаем пустые поля
        rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        self.name = name
        self.penalty = penalty
        self.bgr = rgba[:, :, 2::-1].astype(np.float32)
        self.mask = (rgba[:, :, 3] > 127).astype(np.float32)

    def scaled(self, s):
        return resize(self.bgr, s), resize(self.mask, s)


def masked_ncc(img, tmpl, mask, fimg=None):
    """Нормированная корреляция шаблона (только пиксели маски) со всеми местами кадра.
    img (H, W, 3), tmpl (h, w, 3), mask (h, w). fimg — заранее посчитанные БПФ кадра (ускорение).
    Возвращает карту (H-h+1, W-w+1), значения -1..1."""
    H, W = img.shape[:2]
    h, w = mask.shape
    if H < h or W < w or mask.sum() < 4:
        return np.zeros((0, 0))
    n = mask.sum() * 3
    if fimg is None:
        fimg = image_fft(img)
    fi, fi2 = fimg
    m = mask[::-1, ::-1]
    fm = np.fft.rfft2(m, s=(H, W))
    mu = (tmpl * mask[:, :, None]).sum() / n
    t0 = (tmpl - mu) * mask[:, :, None]
    tnorm = np.sqrt((t0 ** 2).sum()) + 1e-6
    num = s1 = s2 = 0.0
    for c in range(3):
        ft = np.fft.rfft2(t0[::-1, ::-1, c], s=(H, W))
        num = num + np.fft.irfft2(fi[c] * ft, s=(H, W))[h - 1:, w - 1:]
        s1 = s1 + np.fft.irfft2(fi[c] * fm, s=(H, W))[h - 1:, w - 1:]
        s2 = s2 + np.fft.irfft2(fi2[c] * fm, s=(H, W))[h - 1:, w - 1:]
    var = np.maximum(s2 - s1 * s1 / n, 0)
    score = num / (np.sqrt(var) + 1e-6) / tnorm
    score[var < n * 16] = 0            # однотонное место (разброс < 4) — там ничего нет
    return np.clip(score, -1, 1)


def image_fft(img):
    img = img.astype(np.float64)
    H, W = img.shape[:2]
    return ([np.fft.rfft2(img[:, :, c]) for c in range(3)],
            [np.fft.rfft2(img[:, :, c] ** 2) for c in range(3)])


PART_PENALTY = 0.05   # за каждую следующую (меньшую) долю спрайта — совпадение хуже на столько
LONE_GAP = 0.2        # поплавок — отдельный предмет: в той же строке левее и правее (дальше своей ширины)
                      # совпадение должно быть хуже хотя бы на столько. Иначе это полоса (кромка воды)


def ridge_penalty(sc, x, y, w):
    """Насколько место (x, y) карты совпадений sc — не отдельный предмет, а часть полосы: лучшее
    совпадение в тех же строках (±2) не ближе ширины w слева и справа почти такое же, как в
    самом месте. 0 — место отдельное (или сбоку не с чем сравнить)."""
    rows = sc[max(0, y - 2):y + 3]
    side = max(rows[:, :max(0, x - w + 1)].max(initial=-1.0), rows[:, x + w:].max(initial=-1.0))
    return max(0.0, float(side) - (float(sc[y, x]) - LONE_GAP))


class SpriteSet:
    def __init__(self, folder, part=1.0, names=None):
        """part — доля спрайта сверху или несколько долей: поплавок в воде виден больше чем
        наполовину, а в лаве (она непрозрачная) — только верхушка."""
        parts = part if isinstance(part, (tuple, list)) else (part,)
        self.sprites = []
        for f in sorted(os.listdir(folder)):
            if f.endswith(".png"):
                key = f[:-4]
                rgba = read_png(os.path.join(folder, f))
                for k, pt in enumerate(parts):
                    self.sprites.append(Sprite(key, rgba, pt, PART_PENALTY * k))
        self.names = names or {}

    def title(self, key):
        return self.names.get(key, key)

    def find(self, img, scales, only=None, lone=False):
        """Лучшее совпадение: (оценка, x, y, w, h, ключ, масштаб) или None.
        lone — место должно быть отдельным предметом, а не частью полосы (см. ridge_penalty):
        для поиска поплавка в широкой картинке, где есть кромка воды."""
        best = None
        fimg = image_fft(img)
        for sp in self.sprites:
            if only and sp.name not in only:
                continue
            for s in scales:
                t, m = sp.scaled(s)
                sc = masked_ncc(img, t, m, fimg)
                if not sc.size:
                    continue
                y, x = np.unravel_index(int(sc.argmax()), sc.shape)
                v = float(sc[y, x]) - sp.penalty
                if lone:
                    v -= ridge_penalty(sc, x, y, t.shape[1])
                if best is None or v > best[0]:
                    best = (v, int(x), int(y), t.shape[1], t.shape[0], sp.name, s)
        return best
