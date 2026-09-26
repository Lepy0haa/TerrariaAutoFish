"""
Надпись зелья сонара: при поклёвке над поплавком появляется название того, что клюнуло
(цветом редкости, с тёмной тенью). Выделяем её сравнением со снимком того же места до поклёвки
(фон — небо, вода — не мешает) и читаем встроенным в Windows OCR.
"""
import numpy as np


class SonarReader:
    def __init__(self, scale=1.0):
        self.s = scale
        self.base = None                 # снимок места надписи, пока всё спокойно
        self.last_text = ""
        self.last_img = None             # что подали в OCR (для отладочных картинок)

    def region(self, pos, cl):
        """Где искать надпись: над поплавком и чуть ниже его верха, по центру поплавка."""
        s = self.s
        w, up, down = int(420 * s), int(90 * s), int(14 * s)
        x0 = max(cl[0], pos[0] - w // 2)
        x1 = min(cl[2], pos[0] + w // 2)
        y0 = max(cl[1], pos[1] - up)
        y1 = min(cl[3], pos[1] + down)
        return {"left": x0, "top": y0, "width": max(1, x1 - x0), "height": max(1, y1 - y0)}

    def set_base(self, frame):
        self.base = frame.copy()

    def text_mask(self, frame, bobber_box=None):
        """Пиксели появившейся надписи (буквы, без тёмной тени). bobber_box — (x0, y0, x1, y1)
        поплавка в координатах кадра: он при поклёвке ныряет, его не считаем."""
        if self.base is None or self.base.shape != frame.shape:
            return np.zeros(frame.shape[:2], bool)
        changed = np.abs(frame - self.base).max(2) > 40
        if bobber_box is not None:
            x0, y0, x1, y1 = bobber_box
            changed[max(0, y0):y1, max(0, x0):x1] = False
        bright = frame.max(2) > 90                     # буквы (цвет редкости), а не тень
        return changed & bright

    def crop(self, mask):
        """Строка надписи: самая «плотная» полоса строк маски. (y0, y1, x0, x1) или None."""
        rows = mask.sum(1)
        if rows.max(initial=0) < 3:
            return None
        y = int(rows.argmax())
        y0 = y1 = y
        while y0 > 0 and rows[y0 - 1] > 0:
            y0 -= 1
        while y1 < len(rows) - 1 and rows[y1 + 1] > 0:
            y1 += 1
        cols = np.nonzero(mask[y0:y1 + 1].any(0))[0]
        if len(cols) < 3 or (y1 - y0) < 4:
            return None
        return y0, y1 + 1, int(cols.min()), int(cols.max()) + 1

    def prepare(self, mask, box, scale=3):
        """Для OCR: буквы чёрные на белом, с полями, увеличено."""
        y0, y1, x0, x1 = box
        m = mask[y0:y1, x0:x1]
        img = np.where(m, 0, 255).astype(np.uint8)
        img = np.pad(img, 8, constant_values=255)
        return img.repeat(scale, 0).repeat(scale, 1)

    def read(self, frame, bobber_box=None, langs=("ru", "en-US")):
        """Текст надписи или "" (надписи нет / OCR не справился)."""
        import ocr
        mask = self.text_mask(frame, bobber_box)
        box = self.crop(mask)
        self.last_img = None
        if box is None:
            return ""
        img = self.prepare(mask, box)
        self.last_img = img
        for lang in langs:
            text = ocr.read_text(img, lang, prepared=True)
            if text:
                self.last_text = text
                return text
        return ""
