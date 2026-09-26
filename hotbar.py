"""
Хотбар Terraria: где выбранный слот и в каком слоте лежит удочка.

Раскладка хотбара в игре: слоты начинаются в 20 px от левого края, выбранный слот рисуется
в полный размер (52 px), остальные — в 3/4 (39 px), между слотами 4 px; всё это умножается на
«Масштаб интерфейса». Предмет в слоте уменьшается так, чтобы влезть в 32 px, и ещё умножается
на размер слота. Выбранный слот — ярко-жёлтый, по нему и находим масштаб и номер.
"""
import numpy as np

import sprites

# Замерено по скриншоту хотбара при масштабе интерфейса 100 %:
INNER = 50         # ширина жёлтой заливки выбранного слота
BORDER = 3         # тёмная рамка вокруг слота
STEP = 44          # шаг между обычными (маленькими) слотами
SMALL = 40         # размер обычного слота вместе с рамкой
AFTER = 61         # от левого края выбранного слота до левого края следующего
LEFT = 21          # левый край первого слота


def selected_slot(frame):
    """Выбранный (жёлтый) слот: (номер 0..9, масштаб интерфейса, (x0, y0, x1, y1)) или None.
    frame — левый верхний угол игры (BGR)."""
    b, g, r = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
    yellow = (r > 230) & (g > 190) & (b < 90)
    cols = yellow.sum(0)
    # самый длинный отрезок столбцов, где жёлтого много, — это фон выбранного слота
    best, start = (0, 0, 0), None
    for x, c in enumerate(list(cols) + [0]):
        if c >= 8 and start is None:
            start = x
        elif c < 8 and start is not None:
            if x - start > best[0]:
                best = (x - start, start, x)
            start = None
    width, x0, x1 = best
    if width < 20:
        return None
    rows = np.nonzero(yellow[:, x0:x1].sum(1) >= width // 4)[0]
    if not len(rows):
        return None
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    u = width / float(INNER)
    x0, x1 = x0 - BORDER * u, x1 + BORDER * u
    y0, y1 = y0 - BORDER * u, y1 + BORDER * u
    index = int(round((x0 - LEFT * u) / (STEP * u)))
    if not 0 <= index <= 9:
        return None
    return index, u, (int(x0), int(y0), int(x1), int(y1))


def slot_boxes(index, u, sel_box):
    """Прямоугольники всех 10 слотов (x0, y0, x1, y1) и их размер относительно полного."""
    sx0, sy0, sx1, sy1 = sel_box
    cy = (sy0 + sy1) / 2.0
    small, step = SMALL * u, STEP * u
    boxes = []
    for j in range(10):
        if j < index:
            x0, size, rel = sx0 - (index - j) * step, small, 0.75
        elif j == index:
            x0, size, rel = sx0, sx1 - sx0, 1.0
        else:
            x0, size, rel = sx0 + AFTER * u + (j - index - 1) * step, small, 0.75
        boxes.append((int(x0), int(cy - size / 2), int(x0 + size), int(cy + size / 2), rel))
    return boxes


class RodFinder:
    def __init__(self, rods_dir):
        self.rods = sprites.SpriteSet(rods_dir, names=sprites.ROD_NAMES)

    def scores(self, frame):
        """Лучшая удочка в каждом слоте: (номер выбранного слота, [(оценка, удочка), ...] по слотам)
        или None, если хотбар не виден. frame — левый верхний угол игры (BGR)."""
        sel = selected_slot(frame)
        if sel is None:
            return None
        index, u, box = sel
        out = []
        for x0, y0, x1, y1, rel in slot_boxes(index, u, box):
            x0, y0 = max(0, x0), max(0, y0)
            cell = frame[y0:y1, x0:x1]
            best = (0.0, None)
            if cell.shape[0] >= 8 and cell.shape[1] >= 8:
                fimg = sprites.image_fft(cell)
                for sp in self.rods.sprites:
                    h, w = sp.mask.shape
                    base = min(1.0, 32.0 / max(h, w)) * rel * u      # как игра уменьшает предмет в слоте
                    for k in (0.9, 1.0, 1.1):
                        t, m = sp.scaled(base * k)
                        if t.shape[0] > cell.shape[0] or t.shape[1] > cell.shape[1]:
                            continue
                        sc = sprites.masked_ncc(cell, t, m, fimg)
                        if sc.size and sc.max() > best[0]:
                            best = (float(sc.max()), sp.name)
            out.append(best)
        return index, out

    def find(self, frame, min_score=0.55):
        """В каком слоте удочка: (номер слота 0..9, какая удочка, оценка, номер выбранного слота)
        или None. frame — левый верхний угол игры (BGR)."""
        r = self.scores(frame)
        if r is None:
            return None
        index, out = r
        j = max(range(len(out)), key=lambda i: out[i][0])
        if out[j][0] < min_score:
            return None
        return j, out[j][1], out[j][0], index
