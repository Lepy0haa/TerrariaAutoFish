"""
Надписи Terraria, по которым видно, что клюёт и что поймано:
  * зелье сонара — при поклёвке над поплавком название того, что клюнуло;
  * подбор предмета — после подсечки над персонажем название пойманного.
Обе рисуются пиксельным шрифтом игры, цветом редкости, с тёмной тенью. Надпись выделяем
сравнением со снимком того же места до её появления (фон — небо, вода — не мешает) и читаем
встроенным в Windows OCR. Пиксельный шрифт OCR читает с ошибками, поэтому одну надпись читаем
в нескольких вариантах подготовки, а выбирает предмет catches.Catches (из известного списка).
"""
import numpy as np

# варианты подготовки для OCR: (увеличение, утолщение букв, размытие) — подобраны на надписях из игры
VARIANTS = ((3, True, 3), (4, False, 2), (3, False, 0))


def _blur(a, r):
    if r <= 0:
        return a
    k = np.ones(2 * r + 1) / (2 * r + 1)
    a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 0, a)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 1, a)


def prepare(mask, scale=3, thick=False, blur=0):
    """Маска букв -> картинка для OCR: буквы чёрные на белом, с полями, увеличено, сглажено."""
    m = mask.copy()
    if thick:
        m[1:] |= mask[:-1]
        m[:, 1:] |= mask[:, :-1]
    g = np.where(m, 0.0, 255.0)
    g = np.pad(g, 6, constant_values=255).repeat(scale, 0).repeat(scale, 1)
    return _blur(g, blur).clip(0, 255).astype(np.uint8)


class TextReader:
    def __init__(self, scale=1.0):
        self.s = scale
        self.base = None                 # снимок места надписи, пока её нет
        self.reg = None                  # где на экране (для grab)
        self.last_img = None             # что подали в OCR (для отладочных картинок)

    def set_base(self, frame):
        self.base = frame.copy()

    def text_mask(self, frame, exclude=None):
        """Пиксели появившейся надписи (буквы, без тёмной тени). exclude — (x0, y0, x1, y1), что не
        считать (поплавок: при поклёвке он ныряет)."""
        if self.base is None or self.base.shape != frame.shape:
            return np.zeros(frame.shape[:2], bool)
        changed = np.abs(frame - self.base).max(2) > 40
        if exclude is not None:
            x0, y0, x1, y1 = exclude
            changed[max(0, y0):y1, max(0, x0):x1] = False
        return changed & (frame.max(2) > 90)            # буквы (цвет редкости), а не тень

    def crop(self, mask):
        """Строка надписи: самая «плотная» полоса строк маски. (y0, y1, x0, x1) или None, если это
        не похоже на строку текста (искорки, частицы, мелкий шум)."""
        rows = mask.sum(1)
        if rows.max(initial=0) < 3:
            return None
        y = int(rows.argmax())
        y0 = y1 = y
        while y0 > 0 and rows[y0 - 1] > 0:
            y0 -= 1
        while y1 < len(rows) - 1 and rows[y1 + 1] > 0:
            y1 += 1
        band = mask[y0:y1 + 1]
        cols = np.nonzero(band.any(0))[0]
        if len(cols) < 3:
            return None
        x0, x1 = int(cols.min()), int(cols.max()) + 1
        h = y1 - y0 + 1
        # строка текста: высота букв и ширина хотя бы в пару букв, и букв — не пара точек
        if h < 6 * self.s or x1 - x0 < 2 * h or band.sum() < 12 * h:
            return None
        return y0, y1 + 1, x0, x1

    def read_all(self, frame, exclude=None, langs=("ru", "en-US")):
        """Все прочтения надписи (разные варианты подготовки и языки) — пустой список, если надписи нет."""
        import ocr
        mask = self.text_mask(frame, exclude)
        box = self.crop(mask)
        self.last_img = None
        if box is None:
            return []
        y0, y1, x0, x1 = box
        m = mask[y0:y1, x0:x1]
        texts = []
        for scale, thick, blur in VARIANTS:
            img = prepare(m, scale, thick, blur)
            if self.last_img is None:
                self.last_img = img
            for lang in langs:
                t = ocr.read_text(img, lang, prepared=True)
                if t and t not in texts:
                    texts.append(t)
        return texts

    def read(self, frame, exclude=None, langs=("ru", "en-US")):
        """Первое прочтение надписи или ""."""
        texts = self.read_all(frame, exclude, langs)
        return texts[0] if texts else ""


class SonarReader(TextReader):
    """Надпись зелья сонара — над поплавком."""

    def region(self, pos, cl):
        s = self.s
        w, up, down = int(420 * s), int(90 * s), int(14 * s)
        x0, x1 = max(cl[0], pos[0] - w // 2), min(cl[2], pos[0] + w // 2)
        y0, y1 = max(cl[1], pos[1] - up), min(cl[3], pos[1] + down)
        return {"left": x0, "top": y0, "width": max(1, x1 - x0), "height": max(1, y1 - y0)}


class PickupReader(TextReader):
    """Надпись о подборе предмета — над персонажем (он в центре экрана)."""

    def region(self, player, cl):
        s = self.s
        w, up, down = int(460 * s), int(170 * s), int(10 * s)
        x0, x1 = max(cl[0], player[0] - w // 2), min(cl[2], player[0] + w // 2)
        y0, y1 = max(cl[1], player[1] - up), min(cl[3], player[1] - down)
        return {"left": x0, "top": y0, "width": max(1, x1 - x0), "height": max(1, y1 - y0)}
