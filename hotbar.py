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


def render(rgba, s):
    """Картинка предмета так, как её рисует игра в слоте: уменьшенная со сглаживанием.
    Возвращает (цвет BGR, уже умноженный на прозрачность; прозрачность 0..1)."""
    h, w = rgba.shape[:2]
    nh, nw = max(1, int(round(h * s))), max(1, int(round(w * s)))
    pm = rgba[:, :, 2::-1].astype(np.float64) * (rgba[:, :, 3:4] / 255.0)
    a = rgba[:, :, 3].astype(np.float64) / 255.0
    ys = np.clip((np.arange(nh) + 0.5) / s - 0.5, 0, h - 1)
    xs = np.clip((np.arange(nw) + 0.5) / s - 0.5, 0, w - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]

    def sample(img):
        gy, gx = (fy[:, :, None], fx[:, :, None]) if img.ndim == 3 else (fy, fx)
        return (img[y0][:, x0] * (1 - gy) * (1 - gx) + img[y0][:, x1] * (1 - gy) * gx +
                img[y1][:, x0] * gy * (1 - gx) + img[y1][:, x1] * gy * gx)
    return sample(pm), sample(a)


def text_mask(cell):
    """Цифры в слоте (номер слота, количество): белые с тёмной обводкой. Облака за
    полупрозрачным слотом тоже белые, но обводки у них нет."""
    white = (cell.min(2) > 200) & (cell.max(2) - cell.min(2) < 40)
    dark = cell.max(2) < 70
    near = np.zeros_like(dark)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            near |= np.roll(np.roll(dark, dy, 0), dx, 1)
    return white & near


def has_count(cell, size):
    """Написано ли внизу слота число (у удочки — сколько наживки, у стопок — сколько штук).
    size — размер слота относительно полного при масштабе интерфейса 100 %."""
    low = text_mask(cell)[int(cell.shape[0] * 0.55):].sum()
    return low >= 10 * (size / 0.75) ** 2


def slot_background(cell):
    edge = np.concatenate([cell[4:6].reshape(-1, 3), cell[-6:-4].reshape(-1, 3),
                           cell[:, 4:6].reshape(-1, 3), cell[:, -6:-4].reshape(-1, 3)])
    return np.median(edge, 0)


def icon_score(cell, rgba, s, bg):
    """Насколько предмет в слоте похож на картинку rgba (игра рисует его по центру слота):
    корреляция по пикселям предмета, кроме цифр. -1..1."""
    pm, a = render(rgba, s)
    h, w = a.shape
    H, W = cell.shape[:2]
    pred = pm + bg[None, None, :] * (1 - a[:, :, None])      # как предмет выглядит на фоне слота
    cy, cx = int(round(H / 2.0 - h / 2.0)), int(round(W / 2.0 - w / 2.0))
    txt = text_mask(cell)
    best = -1.0
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            y0, x0 = cy + dy, cx + dx
            if y0 < 0 or x0 < 0 or y0 + h > H or x0 + w > W:
                continue
            patch = cell[y0:y0 + h, x0:x0 + w]
            m = (a > 0.3) & ~txt[y0:y0 + h, x0:x0 + w] & ~(patch.max(2) < 45)
            if m.sum() < 15:
                continue
            p, q = patch[m].ravel(), pred[m].ravel()
            p, q = p - p.mean(), q - q.mean()
            best = max(best, float((p * q).sum() / (np.sqrt((p * p).sum() * (q * q).sum()) + 1e-6)))
    return best


class RodFinder:
    """Где в хотбаре удочка. По одной форме иконки удочку не отличить: иконки мелкие, а мечи,
    кнуты и кирки — такие же диагональные палочки. Но на удочке игра пишет, сколько наживки,
    а на оружии и инструментах чисел нет. Поэтому сравниваем с картинками удочек только
    слоты с числом (удочки и стопки вроде зелий), а среди них удочку отличает форма."""

    def __init__(self, rods_dir):
        self.rods = sprites.SpriteSet(rods_dir, names=sprites.ROD_NAMES)
        self.rgba = {}
        import os
        from pngread import read_png
        for f in sorted(os.listdir(rods_dir)):
            if f.endswith(".png"):
                self.rgba[f[:-4]] = read_png(os.path.join(rods_dir, f))

    def scores(self, frame):
        """(номер выбранного слота, [(оценка, удочка, есть ли число), ...] по слотам) или None,
        если хотбар не виден. Слоты без числа не сравниваем (оценка 0)."""
        sel = selected_slot(frame)
        if sel is None:
            return None
        index, u, box = sel
        out = []
        for x0, y0, x1, y1, rel in slot_boxes(index, u, box):
            cell = frame[max(0, y0):y1, max(0, x0):x1].astype(np.float64)
            best = (0.0, None, False)
            if cell.shape[0] >= 16 and cell.shape[1] >= 16 and has_count(cell, rel * u):
                bg = slot_background(cell)
                best = (-1.0, None, True)
                for key, rgba in self.rgba.items():
                    h, w = rgba.shape[:2]
                    base = min(1.0, 32.0 / max(h, w)) * rel * u      # как игра уменьшает предмет в слоте
                    for k in (0.95, 1.0, 1.05):
                        v = icon_score(cell, rgba, base * k, bg)
                        if v > best[0]:
                            best = (v, key, True)
            out.append(best)
        return index, out

    def find(self, frame, min_score=0.45, margin=0.1):
        """Слот с удочкой: (номер слота 0..9, какая удочка, оценка, номер выбранного слота) или None.
        Удочка — слот с числом, больше всех похожий на удочку, с запасом над остальными."""
        r = self.scores(frame)
        if r is None:
            return None
        index, out = r
        cands = [i for i in range(len(out)) if out[i][2]]
        if not cands:
            return None
        j = max(cands, key=lambda i: out[i][0])
        rest = max((out[i][0] for i in cands if i != j), default=0.0)
        if out[j][0] < min_score or out[j][0] - rest < margin:
            return None
        return j, out[j][1], out[j][0], index
