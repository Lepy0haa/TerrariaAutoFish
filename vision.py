"""
Анализ картинки: цвета поплавка, поиск пятна поплавка, похожесть, поклёвка, сердечки.
Часть движка рыбалки (см. autofish.py). Настройки и общие функции берутся из autofish в момент
работы (через A.имя) — поэтому их можно менять на ходу (приложение, тесты).
"""
import sys
from collections import deque

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from i18n import tr


class _AutoFish:
    """autofish, откуда бы он ни был запущен (модулем или как __main__)."""

    def __getattr__(self, name):
        return getattr(sys.modules["autofish"], name)


A = _AutoFish()


def match(frame, tmpl):
    """Где в кадре шаблон поплавка: (y, x, ошибка). Ошибка — средний квадрат разницы."""
    th, tw = tmpl.shape[:2]
    win = sliding_window_view(frame, (th, tw, 3))[:, :, 0]
    d = win - tmpl
    err = np.einsum("ijklm,ijklm->ij", d, d) / d[0, 0].size
    y, x = np.unravel_index(int(err.argmin()), err.shape)
    return int(y), int(x), float(err[y, x])

def rect_around(center, half_w, half_h):
    return {"left": int(center[0] - half_w), "top": int(center[1] - half_h),
            "width": int(2 * half_w), "height": int(2 * half_h)}

def inside(region, cl):
    return (region["left"] >= cl[0] and region["top"] >= cl[1] and
            region["left"] + region["width"] <= cl[2] and region["top"] + region["height"] <= cl[3])

def light_factor(frame):
    """Насколько картинка темнее обычной (1 — днём; меньше — ночью, в пещере). Во столько раз
    можно смягчить пороги «насыщенности» и «отличия от фона», если поплавок иначе не виден."""
    top = np.median(frame[:3].reshape(-1, 3), 0).max()
    bottom = np.median(frame[-3:].reshape(-1, 3), 0).max()
    return float(np.clip(max(top, bottom) / 110.0, 0.35, 1.0))

def _background(frame, far_side):
    """Цвета фона окошка: верхние строки (небо), нижние (вода) и край со стороны без лески."""
    edge = frame[:, :3] if far_side < 0 else frame[:, -3:]
    bg = np.concatenate([edge.reshape(-1, 3), frame[:3].reshape(-1, 3), frame[-3:].reshape(-1, 3)])
    return edge, np.unique((bg // 4) * 4, axis=0)

def _pick_colors(px, bg, k):
    if not len(px):
        return px
    far = np.abs(px[:, None] - bg[None]).max(2).min(1) > A.BG_DIST * k
    vivid = (px.max(1) - px.min(1)) > A.SAT_MIN * k
    return np.unique((px[far & vivid] // 4) * 4, axis=0)

def template_palette(tmpl, frame, far_side, k=1.0):
    """Запасной путь: цвета верхней (надводной) части запомненного образца поплавка, которых нет
    в фоне текущего кадра. Не зависит от того, где кадр «думает», что проходит линия воды."""
    _, bg = A._background(frame, far_side)
    return A._pick_colors(tmpl[:tmpl.shape[0] * 2 // 3].reshape(-1, 3), bg, k)

def bobber_mask(img):
    """Силуэт поплавка: яркие насыщенные пиксели, не похожие на небо (верх) и воду (низ).
    Пороги подстраиваются под яркость картинки (ночь, пещера)."""
    k = A.light_factor(img)
    sky = np.median(img[:3].reshape(-1, 3), 0)
    water = np.median(img[-3:].reshape(-1, 3), 0)
    far = np.minimum(np.abs(img - sky).max(2), np.abs(img - water).max(2)) > A.BG_DIST * k
    vivid = (img.max(2) - img.min(2)) > A.SAT_MIN * k
    return far & vivid

def shape_similarity(patch, ref, shift=2):
    """Похож ли силуэт в patch на силуэт поплавка ref (0..1, пересечение/объединение) —
    с допуском сдвига на shift пикселей. Небо и вода не участвуют, поэтому яркое пятно
    другой формы у линии воды (не поплавок) получает низкую оценку."""
    a, b = A.bobber_mask(patch), A.bobber_mask(ref)
    if b.sum() < 4 or a.sum() < 4:
        return 0.0
    best = 0.0
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            sa = np.roll(np.roll(a, dy, 0), dx, 1)
            inter = (sa & b).sum()
            best = max(best, inter / float((sa | b).sum()))
    return best

def color_match(patch, ref):
    """Доля ярких пикселей patch, чей оттенок (цвет без яркости) есть среди оттенков поплавка ref."""
    a, b = patch[A.bobber_mask(patch)], ref[A.bobber_mask(ref)]
    if not len(a) or not len(b):
        return 0.0
    ca = a / (a.sum(1, keepdims=True) + 1e-6)
    cb = np.unique(np.round(b / (b.sum(1, keepdims=True) + 1e-6), 2), axis=0)
    d = np.abs(ca[:, None] - cb[None]).max(2).min(1)
    return float((d <= 0.08).mean())

def bobber_likeness(patch, ref):
    """Похоже ли место на поплавок: силуэт × цвет (0..1)."""
    return A.shape_similarity(patch, ref) * A.color_match(patch, ref)

def patch_similarity(a, b):
    """Похожи ли две картинки одного размера по рисунку (нормированная корреляция, -1..1).
    Не зависит от общей яркости и оттенка — годится и днём, и ночью."""
    a = a - a.mean(axis=(0, 1))
    b = b - b.mean(axis=(0, 1))
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 1e-6 else 0.0

def bobber_palette(frame, box, far_side, k=1.0):
    """Цвета надводной части поплавка: насыщенные пиксели в рамке box (x, y, w, h) выше
    линии воды, которых нет в фоне. Фон — верхние строки (небо), нижние (вода) и
    3 столбца с края far_side (-1 левый, +1 правый) — со стороны, противоположной леске:
    там небо, вода и блики у линии воды. По краю же находим линию воды."""
    edge, bg = A._background(frame, far_side)
    sky = np.median(frame[:3].reshape(-1, 3), 0)
    water = np.median(frame[-3:].reshape(-1, 3), 0)
    rows = np.median(edge, 1)
    wet = np.abs(rows - water).max(1) < np.abs(rows - sky).max(1)
    waterline = int(np.argmax(wet)) if wet.any() else frame.shape[0]
    x, y, w, h = box
    if waterline < y + h // 3:
        # «Вода» нашлась выше поплавка — так не бывает (ночью небо и вода почти одного цвета).
        # Считаем, что линия воды проходит по середине поплавка.
        waterline = y + h // 2
    return A._pick_colors(frame[y:min(y + h, waterline + 1), x:x + w].reshape(-1, 3), bg, k)

def snap_bobber(frame, w, h, min_px, k=1.0):
    """Ищет в кадре место w x h с наибольшим числом ярких насыщенных пикселей, не похожих
    на небо (верхние строки) и воду (нижние). Возвращает (x, y) левого верхнего угла или None."""
    sky = np.median(frame[:3].reshape(-1, 3), 0)
    water = np.median(frame[-3:].reshape(-1, 3), 0)
    far = np.minimum(np.abs(frame - sky).max(2), np.abs(frame - water).max(2)) > A.BG_DIST * k
    vivid = (frame.max(2) - frame.min(2)) > A.SAT_MIN * k
    m = (far & vivid).astype(np.int32)
    if m.shape[0] < h or m.shape[1] < w:
        return None
    ii = np.pad(m.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    sums = ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w]
    y, x = np.unravel_index(int(sums.argmax()), sums.shape)
    if sums[y, x] < min_px:
        return None
    # поплавок — сплошное пятно: у него есть «серединка», где все соседи тоже яркие.
    # У лески, полосы по краю воды и их пересечения такой серединки 3x3 нет.
    blob = m[y:y + h, x:x + w].astype(bool)
    core = blob[1:-1, 1:-1].copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            core &= blob[dy:dy + h - 2, dx:dx + w - 2]
    if core.any(1).sum() < 3 or core.any(0).sum() < 3:
        return None
    return int(x), int(y)

def snap_adaptive(frame, w, h, min_px):
    """snap_bobber с обычными порогами, а если не нашлось — с порогами под яркость картинки."""
    corner = A.snap_bobber(frame, w, h, min_px)
    k = A.light_factor(frame)
    if corner is None and k < 0.95:
        corner = A.snap_bobber(frame, w, h, min_px, k)
    return corner

def heart_mask(img):
    """Пиксели сердечек здоровья (красные) на кадре BGR."""
    b, g, r = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    return (r > 170) & (g < 100) & (b < 120) & (r - g > 110)

def heart_rows(mask):
    """Полоса строк с сердечками: ряды сердечек (их бывает два) — до промежутка больше высоты
    ряда; ниже бывает мини-карта, там тоже встречается красное. (y0, y1) или None."""
    rows = mask.sum(1)
    full = np.nonzero(rows > 5)[0]
    if not len(full):
        return None
    y0 = int(full[0])
    y = y0
    while y < len(rows) and rows[y] >= 2:            # первый ряд сердечек
        y += 1
    height = max(6, y - y0)
    y1, gap = y - 1, 0
    for y in range(y, len(rows)):
        if rows[y] >= 2:
            y1, gap = y, 0
        else:
            gap += 1
            if gap > height:
                break
    return max(0, y0 - 2), y1 + 3

def same_colors(block, ref, share=0.5):
    """Похожи ли яркие цвета в block на яркие цвета поплавка ref (хотя бы share пикселей)."""
    def vivid(img):
        px = img.reshape(-1, 3)
        return px[(px.max(1) - px.min(1)) > A.SAT_MIN]
    a, b = vivid(block), vivid(ref)
    if not len(a) or not len(b):
        return False
    pal = np.unique((b // 4) * 4, axis=0)
    d = np.abs(a[:, None] - pal[None]).max(2).min(1)
    return (d <= A.COLOR_TOL).mean() >= share

class BiteDetector:
    """Считает, сколько пикселей цвета поплавка видно в окошке. Поклёвка — когда их
    становится заметно меньше обычного (поплавок утянуло под воду)."""

    def __init__(self, palette, debug=False, top=0):
        """top — сколько верхних строк окошка не считать: поплавок при поклёвке уходит вниз, а над
        ним появляется надпись зелья сонара — её буквы бывают цвета поплавка."""
        self.palette, self.debug, self.top = palette, debug, top
        self.hist = deque(maxlen=400)   # (t, видно пикселей)
        self.hits = 0
        self.seen = self.ref = 0
        self.sky = None                 # обычный цвет неба — чтобы узнавать вспышки молний
        self.flash = False
        self.ratio = A.SINK_RATIO         # порог подсечки (автокалибровка может его менять)
        self.jumps = 0                  # снимков подряд с резким нырком
        self.auto = False               # подстраивать порог на лету (автокалибровка)
        self.calm = []                  # (t, доля видимого поплавка) — для автокалибровки
        self.last_calib = 0.0
        self.raised = False             # порог только что подняли (для журнала)
        self.last_dbg = -1.0

    def fit_top(self, frame):
        """Не считать строки выше поплавка (по первому снимку: где начинаются его цвета, минус 3):
        при поклёвке поплавок уходит вниз, а сверху появляется надпись сонара."""
        px = frame.reshape(-1, 1, 3)
        hit = (np.abs(px - self.palette[None]).max(2).min(1) <= A.COLOR_TOL).reshape(frame.shape[:2])
        rows = np.nonzero(hit.sum(1) >= 2)[0]
        self.top = max(0, int(rows[0]) - 3) if len(rows) else 0

    def visible(self, frame):
        px = frame[self.top:].reshape(-1, 1, 3)
        d = np.abs(px - self.palette[None]).max(2).min(1)
        return int((d <= A.COLOR_TOL).sum())

    def feed(self, frame, t):
        """Кадр окошка слежения; t — секунд с начала слежения. Возвращает причину поклёвки или None."""
        # вспышка молнии меняет цвет всего кадра — смотрим на медиану всего окошка (надпись сонара
        # над поплавком занимает малую часть и вспышкой не считается)
        sky = np.median(frame.reshape(-1, 3), 0)
        if self.sky is None:
            self.sky = sky
        self.flash = bool(np.abs(sky - self.sky).max() > A.FLASH_DIFF)
        if self.flash:                                 # вспышка: цвета всего кадра другие
            self.hits = 0
            return None
        self.sky = self.sky * 0.95 + sky * 0.05       # медленные перемены (закат) — норма
        self.seen = self.visible(frame)
        # «обычно» — без последних 0.4 с (в самом начале — без последних 0.15 с, чтобы
        # поклёвку сразу после заброса не пропустить)
        lag = 0.4 if t > 1.0 else 0.15
        old = [v for tt, v in self.hist if tt < t - lag]
        self.hist.append((t, self.seen))
        if t < A.CALIB_TIME or not old:
            return None
        self.ref = float(np.median(old))
        self.calm.append((t, self.seen / self.ref))
        if self.auto and t >= A.CALIB_NOW and t - self.last_calib >= 0.5:
            # подстройка на лету: по спокойной воде этого заброса (без покачивания после
            # приводнения и без последних 0.4 с) порог поднимается до «спокойно минус запас».
            # Только вверх: лёгкие подёргивания перед поклёвкой не должны его опускать
            self.last_calib = t
            steady = [r for tt, r in self.calm if A.CALIB_SKIP <= tt < t - 0.4]
            if len(steady) >= 15:
                live = float(np.clip(np.percentile(steady, A.CALIB_PCT) - A.CALIB_MARGIN, A.CALIB_MIN, A.CALIB_MAX))
                if live > self.ratio + 0.01:
                    self.ratio = live
                    self.raised = True
        sunk = self.seen < self.ref * self.ratio
        self.hits = self.hits + 1 if sunk else 0
        # резкий нырок: только что было видно намного больше (поплавок дёрнуло вниз)
        recent = [v for tt, v in self.hist if t - A.JUMP_WINDOW <= tt < t - 0.03]
        jump = (t >= 0.4 and recent and self.seen < max(recent) * (1 - A.JUMP_DROP)
                and self.seen < self.ref * 0.9)
        self.jumps = self.jumps + 1 if jump else 0
        if self.debug and t - self.last_dbg > 0.25:
            A.log(tr("  видно поплавка: %d (обычно %.0f, порог %.0f)") % (self.seen, self.ref, self.ref * self.ratio))
            self.last_dbg = t
        if self.hits >= A.CONFIRM:
            return tr("видно %d%% поплавка") % (100 * self.seen / max(1.0, self.ref))
        if self.jumps >= A.JUMP_CONFIRM:
            return tr("резкий нырок, видно %d%% поплавка") % (100 * self.seen / max(1.0, self.ref))
        return None
