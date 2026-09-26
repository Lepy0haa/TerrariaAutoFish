"""
Своё «распознавание» шрифта Terraria: память названий. Встроенный в Windows OCR читает пиксельный
шрифт игры с ошибками, а по отдельным буквам надпись не разбить (буквы слипаются и рвутся).
Зато одни и те же предметы попадаются снова и снова: когда название прочитано уверенно, его
картинка (маска букв) запоминается как образец этого предмета. В следующий раз надпись сначала
сравнивается с образцами — быстро и без ошибок OCR; OCR нужен только для новых названий.
"""
import os

import numpy as np

HEIGHT = 16          # образцы приводим к этой высоте
KEEP = 4             # образцов на предмет


def norm(mask):
    """Маска букв -> обрезанная по буквам и приведённая к высоте HEIGHT (ближайший сосед)."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = m.shape
    k = HEIGHT / float(h)
    nw = max(4, int(round(w * k)))
    yi = np.minimum((np.arange(HEIGHT) / k).astype(int), h - 1)
    xi = np.minimum((np.arange(nw) / k).astype(int), w - 1)
    return m[yi][:, xi]


def dice(a, b):
    s = a.sum() + b.sum()
    return 2.0 * (a & b).sum() / s if s else 0.0


def score(cand, tmpl):
    """Похожесть надписи cand на образец tmpl (обе после norm). Надпись может быть длиннее образца
    на приписку вроде « (5)» (стопка) — сравниваем её начало длиной с образец."""
    W = tmpl.shape[1]
    if cand.shape[1] < 0.85 * W or cand.shape[1] > 1.7 * W:
        return 0.0
    best = 0.0
    for dx in (-2, -1, 0, 1, 2):
        a = np.zeros_like(tmpl)
        src = cand[:, max(0, dx):max(0, dx) + W]
        a[:, max(0, -dx):max(0, -dx) + src.shape[1]] = src[:, :W - max(0, -dx)]
        best = max(best, dice(a, tmpl))
    return best


class TextMemory:
    def __init__(self, path=None):
        self.path = path
        self.items = {}                       # id -> [образцы]
        if path and os.path.exists(path):
            try:
                with np.load(path) as d:
                    for key in d.files:
                        item_id = int(key.split("_")[0])
                        self.items.setdefault(item_id, []).append(d[key].astype(bool))
            except Exception:
                self.items = {}

    def count(self):
        return sum(len(v) for v in self.items.values())

    def match(self, mask, min_score=0.78, min_margin=0.08):
        """(id, похожесть, отрыв от лучшего другого предмета) или None."""
        cand = norm(mask)
        if cand is None or not self.items:
            return None
        best = {}
        for item_id, tmpls in self.items.items():
            best[item_id] = max(score(cand, t) for t in tmpls)
        order = sorted(best.items(), key=lambda kv: -kv[1])
        top_id, top = order[0]
        second = order[1][1] if len(order) > 1 else 0.0
        if top >= min_score and top - second >= min_margin:
            return top_id, top, top - second
        return None

    def learn(self, mask, item_id):
        """Запомнить, как выглядит название item_id (если такого образца ещё нет)."""
        n = norm(mask)
        if n is None:
            return False
        tmpls = self.items.setdefault(item_id, [])
        if any(t.shape == n.shape and dice(t, n) > 0.92 for t in tmpls):
            return False
        tmpls.append(n)
        del tmpls[:-KEEP]
        self.save()
        return True

    def save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            arrays = {"%d_%d" % (i, n): t for i, ts in self.items.items() for n, t in enumerate(ts)}
            np.savez_compressed(self.path, **arrays)
        except Exception:
            pass
