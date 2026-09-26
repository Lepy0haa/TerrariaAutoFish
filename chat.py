"""
Сообщения о событиях в чате игры (внизу слева). Игра пишет их особыми цветами: зелёным
(50, 255, 130 — луны, затмение, предупреждения о боссах) и фиолетовым (175, 75, 255 — вторжения,
пробуждение боссов). По цвету находим строку, а какое это событие — читаем распознаванием текста
Windows и сверяем с текстами игры (русскими и английскими).
"""
import difflib

import numpy as np

import catches
import sonar

COLORS_BGR = ((130, 255, 50), (255, 75, 175))    # зелёный и фиолетовый (в BGR, как снимки экрана)
COLOR_TOL = 40
MIN_PX = 40                    # столько пикселей такого цвета — может быть строка текста

# событие: (название для журнала, сколько минут пережидать, тексты начала, тексты конца)
# ночь в игре длится около 9 минут, день — около 15
EVENTS = {
    "blood_moon": ("Кровавая луна", 9, ("Восходит кровавая луна", "The Blood Moon is rising"), ()),
    "pumpkin_moon": ("Тыквенная луна", 9, ("Восходит тыквенная луна", "The Pumpkin Moon is rising"), ()),
    "frost_moon": ("Морозная луна", 9, ("Восходит морозная луна", "The Frost Moon is rising"), ()),
    "eclipse": ("Солнечное затмение", 15, ("Наступило солнечное затмение", "A solar eclipse is happening"), ()),
    "boss_night": ("Этой ночью придёт босс", 9, (
        "Вы чувствуете чье-то злобное внимание", "You feel an evil presence watching you",
        "Леденящий ужас спускается по твоему позвоночнику", "A horrible chill goes down your spine",
        "Вокруг тебя эхом разносятся крики", "Screams echo around you",
        "Вы чувствуете вибрации из глубины", "You feel vibrations from deep below",
        "Это будет ужасная ночь", "This is going to be a terrible night"), ()),
    "goblins": ("Армия гоблинов", 10, (
        "Армия гоблинов приближается", "A goblin army is approaching",
        "Армия гоблинов прибыла", "A goblin army has arrived"),
        ("Армия гоблинов побеждена", "A goblin army has been defeated")),
    "pirates": ("Пираты", 10, ("Пираты приближаются", "Pirates are approaching",
                               "Пираты прибыли", "The pirates have arrived"),
                ("Пираты побеждены", "The pirates have been defeated")),
    "frost_legion": ("Ледяной легион", 10, (
        "Ледяной легион приближается", "The Frost Legion is approaching",
        "Ледяной легион прибыл", "The Frost Legion has arrived"),
        ("Ледяной легион побежден", "The Frost Legion has been defeated")),
    "martians": ("Марсиане", 10, ("Марсиане наступают", "Martians are invading"),
                 ("Марсиане побеждены", "The martians have been defeated")),
    "celestial": ("Небесные существа", 10, ("Небесные существа наступают", "Celestial creatures are invading"), ()),
    "boss": ("Босс", 10, (), ()),              # «Босс … пробудился!» / «… has awoken!» — по концу строки
}
AWOKEN = ("пробудился", "пробудились", "awoken")


def region(cl):
    """Где чат: левая половина окна игры, нижняя треть (без самой нижней полоски — там поле ввода)."""
    w, h = cl[2] - cl[0], cl[3] - cl[1]
    top = cl[1] + int(h * 0.62)
    return {"left": cl[0], "top": top, "width": int(w * 0.5), "height": cl[3] - int(h * 0.02) - top}


def color_mask(frame, bgr):
    return np.abs(frame[:, :, :3] - np.array(bgr, np.float32)).max(2) <= COLOR_TOL


def event_texts(frame, scale=1.0):
    """Прочтения самой заметной строки каждого цвета событий: [текст, ...] (пусто — таких строк нет)."""
    texts = []
    for bgr in COLORS_BGR:
        m = color_mask(frame, bgr)
        if m.sum() < MIN_PX:
            continue
        rd = sonar.TextReader(scale)
        box = rd.crop(m)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        texts += rd.ocr(m[y0:y1, x0:x1])
    return texts


def _ratio(text, phrase):
    t, p = catches.normalize(text), catches.normalize(phrase)
    return difflib.SequenceMatcher(None, t[:len(p) + 4], p).ratio()


def classify(texts, min_ratio=0.6):
    """Что за сообщение: ("start", событие) / ("end", событие) / None. Берётся самая похожая фраза
    (у «Армия гоблинов прибыла» и «…побеждена» одинаковое начало — решает конец)."""
    best, found = min_ratio, None
    for t in texts:
        for key, (_, _, starts, ends) in EVENTS.items():
            for kind, phrases in (("start", starts), ("end", ends)):
                for p in phrases:
                    r = _ratio(t, p)
                    if r > best:
                        best, found = r, (kind, key)
        words = catches.normalize(t).split()
        if found is None and words and any(difflib.SequenceMatcher(None, w, a).ratio() >= 0.8
                                           for w in words[-2:] for a in AWOKEN):
            found = ("start", "boss")
    return found


def is_blood_moon(texts, min_ratio=0.6):
    return classify(texts, min_ratio) == ("start", "blood_moon")
