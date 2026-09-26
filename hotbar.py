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
STEP = 45          # шаг между слотами (замерено по левому краю выбранного слота: 21 + 45·номер)
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
    if index >= 2:
        # масштаб точнее по месту выбранного слота (левый край — (21 + 45·номер)·масштаб), чем
        # по ширине заливки: ошибка в пару пикселей по ширине набегает к дальним слотам
        u = x0 / float(LEFT + STEP * index)
    return index, u, (int(x0), int(y0), int(x1), int(y1))


def slot_boxes(index, u, sel_box):
    """Прямоугольники всех 10 слотов (x0, y0, x1, y1) и их размер относительно полного."""
    sx0, sy0, sx1, sy1 = sel_box
    cy = (sy0 + sy1) / 2.0
    small = SMALL * u
    boxes = []
    for j in range(10):
        # слоты считаем от начала хотбара: левый край — (21 + 45·номер)·масштаб, а правее
        # выбранного (он шире) — ещё на (61 − 45)·масштаб
        x0 = (LEFT + STEP * j + (AFTER - STEP if j > index else 0)) * u
        if j == index:
            x0, size, rel = sx0, sx1 - sx0, 1.0
        else:
            size, rel = small, 0.75
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


def count_text(cell, size):
    """Пиксели числа внизу слота — без рамки слота (у выбранного слота она светлая с тёмной
    обводкой, как цифры). size — размер слота относительно полного при масштабе интерфейса 100 %."""
    m = int(round(5 * size / 0.75))
    t = text_mask(cell)
    return t[int(cell.shape[0] * 0.55):-m or None, m:-m or None]


def has_count(cell, size):
    """Написано ли внизу слота число (у удочки — сколько наживки, у стопок — сколько штук)."""
    return count_text(cell, size).sum() >= 10 * (size / 0.75) ** 2


def bait_digits(cell, size):
    """Сколько цифр в числе внизу слота (у удочки — сколько наживки): 0 — числа нет.
    Сами цифры слишком мелкие, чтобы уверенно их прочитать, но ширину надписи видно хорошо:
    одна цифра — около 6 пикселей при масштабе интерфейса 100 % в обычном слоте."""
    if not has_count(cell, size):
        return 0
    cols = np.nonzero(count_text(cell, size).any(0))[0]
    width = cols.max() - cols.min() + 1
    return max(1, int(round((width + 1) / (6.0 * size / 0.75))))


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
    # ±6 пикселей: раскладку хотбара мы знаем с точностью до пары пикселей
    for dy in range(-4, 5):
        for dx in range(-6, 7):
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


class ItemFinder:
    """Предметы в хотбаре по картинкам с Вики (папка folder, файл = ключ предмета).
    Сравниваем только слоты с числом внизу (стопки, удочки с наживкой) — у них есть что узнавать,
    а мелкие иконки оружия и инструментов слишком похожи на что угодно."""

    def __init__(self, folder, need_count=True):
        """need_count=False — сравнивать и слоты без числа (стопка из одного предмета числа
        не показывает — например, одно зелье)."""
        import os
        from pngread import read_png
        self.need_count = need_count
        self.rgba = {}
        for f in sorted(os.listdir(folder)):
            if f.endswith(".png"):
                self.rgba[f[:-4]] = read_png(os.path.join(folder, f))

    def cell_scores(self, cell, size):
        """{ключ: оценка} для одного слота (size — его размер относительно полного)."""
        bg = slot_background(cell)
        out = {}
        for key, rgba in self.rgba.items():
            h, w = rgba.shape[:2]
            base = min(1.0, 32.0 / max(h, w)) * size       # как игра уменьшает предмет в слоте
            out[key] = max(icon_score(cell, rgba, base * k, bg) for k in (0.95, 1.0, 1.05))
        return out

    def cells(self, frame):
        """(номер выбранного слота, [(слот, его размер, есть ли число, сравнивать ли), ...]) или None."""
        sel = selected_slot(frame)
        if sel is None:
            return None
        index, u, box = sel
        out = []
        for x0, y0, x1, y1, rel in slot_boxes(index, u, box):
            cell = frame[max(0, y0):y1, max(0, x0):x1].astype(np.float64)
            big = cell.shape[0] >= 16 and cell.shape[1] >= 16
            count = big and has_count(cell, rel * u)
            out.append((cell, rel * u, count, big and (count or not self.need_count)))
        return index, out

    def all_scores(self, frame):
        """(номер выбранного слота, [({ключ: оценка} или None, есть ли число), ...] по слотам)
        или None, если хотбар не виден."""
        r = self.cells(frame)
        if r is None:
            return None
        return r[0], [(self.cell_scores(c, size) if use else None, count) for c, size, count, use in r[1]]

    def find_item(self, frame, key, min_score=0.5):
        """В каком слоте предмет key: слот, где он больше всех похож именно на key (а не на
        другой предмет из папки), с оценкой не ниже min_score. (слот, оценка) или None."""
        r = self.all_scores(frame)
        if r is None:
            return None
        best = None
        for j, (sc, _) in enumerate(r[1]):
            if not sc or max(sc, key=sc.get) != key or sc[key] < min_score:
                continue
            if best is None or sc[key] > best[1]:
                best = (j, sc[key])
        return best


class RodFinder(ItemFinder):
    """Где в хотбаре удочка. По одной форме иконки удочку не отличить: иконки мелкие, а мечи,
    кнуты и кирки — такие же диагональные палочки. Но на удочке игра пишет, сколько наживки,
    а на оружии и инструментах чисел нет. Поэтому сравниваем с картинками удочек только
    слоты с числом (удочки и стопки), а среди них удочку отличает форма. Слот, который больше
    похож на известное зелье (others — папка с картинками зелий), удочкой не считаем."""

    def __init__(self, rods_dir, others=None):
        import os
        ItemFinder.__init__(self, rods_dir)
        self.rods = sprites.SpriteSet(rods_dir, names=sprites.ROD_NAMES)
        if others is None:
            others = os.path.join(os.path.dirname(os.path.abspath(rods_dir)), "potions")
        self.others = ItemFinder(others) if others and os.path.isdir(others) else None

    def scores(self, frame):
        """(номер выбранного слота, [(оценка, удочка, есть ли число), ...] по слотам) или None,
        если хотбар не виден. Слоты без числа (и похожие на зелья) — оценка 0."""
        r = self.cells(frame)
        if r is None:
            return None
        out = []
        for cell, size, count, use in r[1]:
            if not use:
                out.append((0.0, None, False))
                continue
            sc = self.cell_scores(cell, size)
            key = max(sc, key=sc.get)
            if self.others is not None and max(self.others.cell_scores(cell, size).values()) > sc[key]:
                out.append((0.0, None, True))          # это зелье (или другая известная стопка)
                continue
            out.append((sc[key], key, True))
        return r[0], out

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
