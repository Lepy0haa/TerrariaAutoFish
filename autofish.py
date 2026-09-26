"""
Terraria AutoFish — автоматическая рыбалка для Terraria (1.4.x, 1.4.5, tModLoader).

Работает только «по картинке»: вы один раз показываете, где поплавок, программа
запоминает, как он выглядит, и подсекает, когда поплавок уходит под воду.
В память и файлы игры не лезет.

Это «движок» и консольная версия. Приложение с окном — app.py.
Управление (пока окно Terraria активно):
  HOME — старт (курсор на воде, куда забрасывать) / отметить поплавок / пауза
  END  — выход (только в консольной версии)
Ключи запуска:
  --debug   печатать замеры и сохранять картинки в папку debug
  --record  режим записи: забрасывает программа, подсекаете вы, а программа
            записывает, сколько поплавка было видно перед подсечкой (папка record)
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import threading
import time
import winsound
from collections import deque

import mss
import mss.tools
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from pynput import keyboard, mouse

import i18n
from i18n import tr

i18n.set_lang("auto")

# ============================ НАСТРОЙКИ ============================
TOGGLE_KEY = "home"   # старт / отметить поплавок / пауза (имя клавиши из pynput: home, insert, f6 ...)
EXIT_KEY = "end"      # выход из консольной версии
RESET_KEY = "delete"  # выбрать новые точки (в приложении с окном — настраивается)

SCALE = 1.0           # «Масштаб» (Zoom) в настройках игры: 100% -> 1.0, 150% -> 1.5, 200% -> 2.0

SETTLE_TIME = 1.6     # сек. после заброса, пока поплавок упадёт в воду
CALIB_TIME = 0.6      # сек. замера, сколько поплавка видно обычно
MAX_WAIT = 45.0       # сек. без поклёвки -> вытащить и забросить заново
REEL_DELAY = 0.9      # сек. после подсечки до нового заброса
POLL = 0.005          # сек. между снимками при ожидании поклёвки

ZONE_X = 40           # насколько далеко от отметки (px при SCALE=1) может упасть поплавок по горизонтали
ZONE_Y = 30           # ...и по вертикали
NOT_FOUND_ERR = 1500  # если в зоне нет ничего похожего на поплавок сильнее этого — «не найден»
SIMILAR_MIN = 0.3     # «поплавок уже в воде», только если силуэт и цвет так похожи на запомненный

SINK_RATIO = 0.55     # поклёвка: видно меньше этой доли поплавка, чем обычно (поплавок ушёл под воду)
CONFIRM = 3           # сколько снимков подряд должно подтверждать поклёвку
COLOR_TOL = 30        # насколько цвет пикселя может отличаться от цвета поплавка
BG_DIST = 50          # цвет поплавка должен отличаться от неба, воды и бликов хотя бы на столько
SAT_MIN = 60          # ...и быть насыщенным (не серым), чтобы не спутать с бликами на воде
FLASH_DIFF = 40       # небо резко сменило цвет (молния) — такие кадры пропускаем
MAX_FAILS = 3         # столько неудачных забросов подряд -> пауза (кончилась наживка?)
AUTO_CALIB = True     # автокалибровка: порог подсечки подбирается сам по тому, как качается поплавок
CALIB_MARGIN = 0.2    #   порог = «спокойный минимум» (сколько поплавка видно на волнах) минус столько
CALIB_MIN_CASTS = 2   #   после стольких забросов порог начинает подбираться сам

AUTO_RECOVER = True   # после сбоев не вставать на паузу сразу, а пробовать продолжить
RECOVER_WAITS = (10, 30, 60)   # сколько секунд ждать перед каждой новой попыткой
AUTO_RESUME = True    # пауза из-за переключения в другое окно — продолжить, когда вернётесь в игру
RESUME_AFTER = 2.0    #   ...через столько секунд в игре

BUFFS_ON = False      # следить за зельями и пить их (клавишей быстрого баффа)
BUFF_WANT = {"fishing": True, "crate": True}   # какие баффы держать
BUFF_KEY = "b"        # клавиша быстрого баффа в Terraria (по умолчанию B)
BUFF_CHECK_EVERY = 20.0   # как часто проверять баффы, секунд
BUFF_BACKOFF = 300.0  # если выпить не получилось (кончились зелья) — не пробовать столько секунд
AUTO_ROD = True       # перед забросом брать удочку в руки (клавишей её слота в хотбаре)
AUTO_MARK = True      # после первого заброса искать поплавок самому (по картинкам поплавков с Вики)
SPRITE_MIN = 0.75     # насколько картинка на экране должна совпасть с поплавком с Вики
ROD_SELECTED_MIN = 0.45   # в руках удочка, если выбранный слот похож на удочку хотя бы так
ROD_OTHER_MIN = 0.5       # ...иначе ищем удочку в другом слоте: оценка не ниже этой
ROD_MARGIN = 0.1          # ...и заметно лучше, чем у остальных слотов
SOUND = True          # пищать при старте, отметке, паузе
# ==================================================================

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # реальные пиксели при масштабе Windows 125/150%
except Exception:
    user32.SetProcessDPIAware()

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
# папка программы: рядом с .exe или со скриптом
HERE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
DEBUG_DIR = os.path.join(HERE, "debug")
# картинки (иконки баффов): внутри .exe — во временной папке PyInstaller, иначе — рядом со скриптом
ASSET_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets")
RECORD_DIR = os.path.join(HERE, "record")


def log(msg):
    try:
        print(time.strftime("[%H:%M:%S] ") + msg, flush=True)
    except Exception:  # у оконного .exe нет консоли
        pass


def beep(freq=880, ms=120):
    if not SOUND:
        return
    try:
        winsound.Beep(freq, ms)
    except Exception:
        pass


def key_from_name(name):
    return getattr(keyboard.Key, name, None) or keyboard.KeyCode.from_char(name)


def get_cursor():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def set_cursor(x, y):
    user32.SetCursorPos(int(x), int(y))


def click(x, y, hold=0.06):
    set_cursor(x, y)
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold)  # игра опрашивает мышь раз в кадр — держим дольше 1/60 с
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def terraria_window():
    """hwnd активного окна, если это Terraria / tModLoader, иначе None."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    title = buf.value.lower()
    if title.startswith("terraria") or title.startswith("tmodloader"):
        return hwnd
    return None


def client_rect(hwnd):
    """Клиентская область окна в экранных координатах: (left, top, right, bottom)."""
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return p.x, p.y, p.x + r.right, p.y + r.bottom


def grab(sct, region):
    img = sct.grab(region)
    return np.asarray(img)[:, :, :3].astype(np.float32)  # BGR


def save_png(img, path, scale=1, rects=()):
    """Сохраняет кадр (BGR) в PNG; rects — [(x, y, w, h, (b, g, r)), ...]."""
    img = img.astype(np.int16).copy()
    for x, y, w, h, color in rects:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(img.shape[1] - 1, x + w - 1), min(img.shape[0] - 1, y + h - 1)
        if x0 > x1 or y0 > y1:
            continue
        img[y0, x0:x1 + 1] = color
        img[y1, x0:x1 + 1] = color
        img[y0:y1 + 1, x0] = color
        img[y0:y1 + 1, x1] = color
    if scale > 1:
        img = img.repeat(scale, 0).repeat(scale, 1)
    rgb = np.ascontiguousarray(img[:, :, ::-1].clip(0, 255).astype(np.uint8))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mss.tools.to_png(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), output=path)


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
    far = np.abs(px[:, None] - bg[None]).max(2).min(1) > BG_DIST * k
    vivid = (px.max(1) - px.min(1)) > SAT_MIN * k
    return np.unique((px[far & vivid] // 4) * 4, axis=0)


def template_palette(tmpl, frame, far_side, k=1.0):
    """Запасной путь: цвета верхней (надводной) части запомненного образца поплавка, которых нет
    в фоне текущего кадра. Не зависит от того, где кадр «думает», что проходит линия воды."""
    _, bg = _background(frame, far_side)
    return _pick_colors(tmpl[:tmpl.shape[0] * 2 // 3].reshape(-1, 3), bg, k)


def bobber_mask(img):
    """Силуэт поплавка: яркие насыщенные пиксели, не похожие на небо (верх) и воду (низ).
    Пороги подстраиваются под яркость картинки (ночь, пещера)."""
    k = light_factor(img)
    sky = np.median(img[:3].reshape(-1, 3), 0)
    water = np.median(img[-3:].reshape(-1, 3), 0)
    far = np.minimum(np.abs(img - sky).max(2), np.abs(img - water).max(2)) > BG_DIST * k
    vivid = (img.max(2) - img.min(2)) > SAT_MIN * k
    return far & vivid


def shape_similarity(patch, ref, shift=2):
    """Похож ли силуэт в patch на силуэт поплавка ref (0..1, пересечение/объединение) —
    с допуском сдвига на shift пикселей. Небо и вода не участвуют, поэтому яркое пятно
    другой формы у линии воды (не поплавок) получает низкую оценку."""
    a, b = bobber_mask(patch), bobber_mask(ref)
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
    a, b = patch[bobber_mask(patch)], ref[bobber_mask(ref)]
    if not len(a) or not len(b):
        return 0.0
    ca = a / (a.sum(1, keepdims=True) + 1e-6)
    cb = np.unique(np.round(b / (b.sum(1, keepdims=True) + 1e-6), 2), axis=0)
    d = np.abs(ca[:, None] - cb[None]).max(2).min(1)
    return float((d <= 0.08).mean())


def bobber_likeness(patch, ref):
    """Похоже ли место на поплавок: силуэт × цвет (0..1)."""
    return shape_similarity(patch, ref) * color_match(patch, ref)


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
    edge, bg = _background(frame, far_side)
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
    return _pick_colors(frame[y:min(y + h, waterline + 1), x:x + w].reshape(-1, 3), bg, k)


def snap_bobber(frame, w, h, min_px, k=1.0):
    """Ищет в кадре место w x h с наибольшим числом ярких насыщенных пикселей, не похожих
    на небо (верхние строки) и воду (нижние). Возвращает (x, y) левого верхнего угла или None."""
    sky = np.median(frame[:3].reshape(-1, 3), 0)
    water = np.median(frame[-3:].reshape(-1, 3), 0)
    far = np.minimum(np.abs(frame - sky).max(2), np.abs(frame - water).max(2)) > BG_DIST * k
    vivid = (frame.max(2) - frame.min(2)) > SAT_MIN * k
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
    corner = snap_bobber(frame, w, h, min_px)
    k = light_factor(frame)
    if corner is None and k < 0.95:
        corner = snap_bobber(frame, w, h, min_px, k)
    return corner


def press_key(name):
    """Нажать клавишу в игре (например, B — быстрый бафф)."""
    name = name.lower()
    vk = {"space": 0x20}.get(name, ord(name.upper()) if len(name) == 1 else 0)
    if not vk:
        return
    sc = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, sc, 0, 0)
    time.sleep(0.06)
    user32.keybd_event(vk, sc, 2, 0)


BUFF_NAMES = {"fishing": "зелье рыбалки", "crate": "ящичное зелье"}


def BUFF_THRESHOLD():
    import buffs
    return buffs.THRESHOLD


def find_terraria():
    """Окно Terraria, даже если оно сейчас не активно (для проверки баффов из окна программы)."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        t = buf.value.lower()
        if user32.IsWindowVisible(hwnd) and (t.startswith("terraria") or t.startswith("tmodloader")):
            found.append(hwnd)
        return True
    user32.EnumWindows(each, 0)
    return found[0] if found else None


def same_colors(block, ref, share=0.5):
    """Похожи ли яркие цвета в block на яркие цвета поплавка ref (хотя бы share пикселей)."""
    def vivid(img):
        px = img.reshape(-1, 3)
        return px[(px.max(1) - px.min(1)) > SAT_MIN]
    a, b = vivid(block), vivid(ref)
    if not len(a) or not len(b):
        return False
    pal = np.unique((b // 4) * 4, axis=0)
    d = np.abs(a[:, None] - pal[None]).max(2).min(1)
    return (d <= COLOR_TOL).mean() >= share


class BiteDetector:
    """Считает, сколько пикселей цвета поплавка видно в окошке. Поклёвка — когда их
    становится заметно меньше обычного (поплавок утянуло под воду)."""

    def __init__(self, palette, debug=False):
        self.palette, self.debug = palette, debug
        self.hist = deque(maxlen=400)   # (t, видно пикселей)
        self.hits = 0
        self.seen = self.ref = 0
        self.sky = None                 # обычный цвет неба — чтобы узнавать вспышки молний
        self.flash = False
        self.ratio = SINK_RATIO         # порог подсечки (автокалибровка может его менять)
        self.last_dbg = -1.0

    def visible(self, frame):
        px = frame.reshape(-1, 1, 3)
        d = np.abs(px - self.palette[None]).max(2).min(1)
        return int((d <= COLOR_TOL).sum())

    def feed(self, frame, t):
        """Кадр окошка слежения; t — секунд с начала слежения. Возвращает причину поклёвки или None."""
        sky = np.median(frame[:3].reshape(-1, 3), 0)
        if self.sky is None:
            self.sky = sky
        self.flash = bool(np.abs(sky - self.sky).max() > FLASH_DIFF)
        if self.flash:                                 # вспышка: цвета всего кадра другие
            self.hits = 0
            return None
        self.sky = self.sky * 0.95 + sky * 0.05       # медленные перемены (закат) — норма
        self.seen = self.visible(frame)
        old = [v for tt, v in self.hist if tt < t - 0.4]   # «обычно» — без последних 0.4 с
        self.hist.append((t, self.seen))
        if t < CALIB_TIME or not old:
            return None
        self.ref = float(np.median(old))
        sunk = self.seen < self.ref * self.ratio
        self.hits = self.hits + 1 if sunk else 0
        if self.debug and t - self.last_dbg > 0.25:
            log(tr("  видно поплавка: %d (обычно %.0f, порог %.0f)") % (self.seen, self.ref, self.ref * self.ratio))
            self.last_dbg = t
        if self.hits >= CONFIRM:
            return tr("видно %d%% поплавка") % (100 * self.seen / max(1.0, self.ref))
        return None


class Fisher:
    """Движок рыбалки. События для интерфейса отправляет в events(kind, data):
      log      {text, kind}                   — строка журнала (kind: info, good, bad, ask)
      state    {state, title, hint}           — что сейчас происходит
      stats    {hooks, casts, fails, started} — счётчики
      live     {seen, ref, ratio, frame, t, max_wait, flash} — живые замеры (~10 раз в секунду)
      bobber   {img}                          — запомненный поплавок
      points   {saved}                        — сохранены ли точка заброса и поплавок
      calib    {ratio, casts, auto}           — порог подсечки (автокалибровка)
      buffs    {status}                       — какие баффы есть: {"fishing": True, ...}
      gear     {rod_slot, rod, bobber}        — слот удочки, какая удочка и какой поплавок (названия или None)
      hook     {why, waited}                  — подсечка
      notify   {title, text}                  — важное: пауза не по вашей команде, ошибка
    """

    def __init__(self, debug=False, record=False, events=None, toggle_key=None, exit_key=None,
                 reset_key=None, points_path=None):
        self.debug = debug
        self.record = record
        self.events = events
        self.running = threading.Event()
        self.quit = threading.Event()
        self.marking = threading.Event()   # ждём, пока игрок отметит поплавок
        self.clicks = queue.Queue()        # время кликов игрока в режиме записи
        self.cast_point = None
        self.park = None
        self.mark = None                   # где искать поплавок (сдвигается, если он падает в другом месте)
        self.bobber = None                 # как выглядит поплавок (обновляется под освещение)
        self.mark0 = self.bobber0 = None   # то, что игрок отметил сам, — для поиска потерянного поплавка
        # Где сейчас поплавок: "idle" — не заброшен, "watching" — в воде и мы за ним следили
        # (self.watched = (центр, снимок окошка)), "unknown" — неизвестно (пауза во время заброса,
        # неудача, запуск программы). Нужно, чтобы после паузы не кликать вслепую.
        self.phase = "idle"
        self.watched = None
        self.calm_floors = deque(maxlen=8)  # автокалибровка: «спокойный минимум» по последним забросам
        self.hooks = self.casts = self.fails = 0
        self.recover_round = 0             # сколько раз подряд уже пробовали восстановиться
        self.errors = 0                    # ошибок подряд
        self.resume_on_focus = False       # продолжить, когда игрок вернётся в окно игры
        self.focus_since = None
        try:                               # узнаём баффы по иконкам
            import buffs
            self.buffs = buffs.BuffWatcher(ASSET_DIR)
        except Exception:
            self.buffs = None
        self.last_buff_check = 0.0
        self.buff_backoff = {}
        try:                               # удочки и поплавки с Вики (для хотбара и поиска поплавка)
            import hotbar
            import sprites
            self.rods = hotbar.RodFinder(os.path.join(ASSET_DIR, "rods"))
            self.bobber_sprites = sprites.SpriteSet(os.path.join(ASSET_DIR, "bobbers"), part=0.55,
                                                    names=sprites.BOBBER_NAMES)
        except Exception:
            self.rods = self.bobber_sprites = None
        self.rod_slot = None               # в каком слоте хотбара удочка (0..9)
        self.hotbar_u = 1.0                # масштаб интерфейса, при котором его запомнили
        self.rod_misses = 0                # сколько раз подряд не получилось взять удочку
        self.rod_name = None               # какая это удочка (ключ картинки) или None — не узнали
        self.bobber_kind = None            # какой поплавок (ключ картинки) или None — не узнали
        self.mark_before = None            # снимок места до первого заброса (для поиска поплавка)
        self.started = None                # когда начали рыбачить (для «подсечек в час»)
        self.n = 0
        self.listeners = []
        self.set_hotkey(toggle_key or TOGGLE_KEY)
        self.exit_key = key_from_name(exit_key) if exit_key else None
        self.set_reset_key(reset_key)
        self.set_scale(SCALE)
        self.points_path = points_path     # файл, где точки хранятся между запусками программы

    # ---------- настройки ----------
    def set_scale(self, s):
        self.scale = s
        self.tw, self.th = max(8, int(14 * s)), max(12, int(22 * s))  # шаблон поплавка (с крючком)
        self.track_rx = max(8, int(12 * s))    # запас окошка слежения вокруг поплавка по бокам
        self.track_ry = max(12, int(18 * s))   # ...и сверху/снизу (там небо и вода)
        self.zone_x, self.zone_y = int(ZONE_X * s), int(ZONE_Y * s)
        self.snap = int(20 * s)                # насколько далеко от курсора искать поплавок при отметке
        self.min_bobber_px = max(6, int(8 * s * s))  # столько ярких пикселей должно быть у поплавка

    def set_hotkey(self, name):
        self.key_name = name.upper()
        self.toggle_key = key_from_name(name)

    def set_reset_key(self, name):
        """Клавиша «выбрать новые точки» (None — нет)."""
        self.reset_name = name.upper() if name else None
        self.reset_key = key_from_name(name) if name else None

    # ---------- события ----------
    def emit(self, event, **data):
        if self.events:
            try:
                self.events(event, data)
            except Exception:
                pass

    def log(self, msg, kind="info"):
        log(msg)
        self.emit("log", text=msg, kind=kind)

    def state(self, state, title, hint=""):
        self.emit("state", state=state, title=title, hint=hint)

    def stats(self):
        self.emit("stats", hooks=self.hooks, casts=self.casts, fails=self.fails, started=self.started)

    def has_points(self):
        return self.cast_point is not None and self.bobber is not None

    def idle_hint(self):
        if self.has_points():
            new = (tr(" %s — выбрать новые") % self.reset_name) if self.reset_name else ""
            return tr("Точки сохранены. В игре: %s — продолжить.%s") % (self.key_name, new)
        return tr("Наведите курсор на воду в игре и нажмите %s") % self.key_name

    def points_changed(self):
        self.emit("points", saved=self.has_points())

    def save_points(self):
        """Запомнить точку заброса и поплавок на диск — чтобы продолжить после перезапуска."""
        if not self.points_path or not self.has_points() or self.bobber0 is None:
            return
        try:
            os.makedirs(os.path.dirname(self.points_path), exist_ok=True)
            np.savez(self.points_path, cast_point=self.cast_point, mark=self.mark, mark0=self.mark0,
                     bobber=self.bobber, bobber0=self.bobber0, scale=self.scale,
                     bobber_kind=self.bobber_kind or "")
        except Exception:
            pass

    def load_points(self):
        try:
            d = np.load(self.points_path)
            if abs(float(d["scale"]) - self.scale) > 1e-6 or d["bobber"].shape[:2] != (self.th, self.tw):
                return False
            self.cast_point = tuple(int(v) for v in d["cast_point"])
            self.mark = tuple(int(v) for v in d["mark"])
            self.mark0 = tuple(int(v) for v in d["mark0"])
            self.bobber = d["bobber"].astype(np.float32)
            self.bobber0 = d["bobber0"].astype(np.float32)
            self.bobber_kind = str(d["bobber_kind"]) if "bobber_kind" in d.files and str(d["bobber_kind"]) else None
            self.phase = "unknown"
            self.gear_changed()
            return True
        except Exception:
            return False

    def delete_points(self):
        try:
            if self.points_path and os.path.exists(self.points_path):
                os.remove(self.points_path)
        except Exception:
            pass

    # ---------- автокалибровка ----------
    def sink_ratio(self):
        """Текущий порог подсечки: подобранный автокалибровкой или заданный вручную."""
        if AUTO_CALIB and len(self.calm_floors) >= CALIB_MIN_CASTS:
            return float(np.clip(np.median(self.calm_floors) - CALIB_MARGIN, 0.35, 0.75))
        return SINK_RATIO

    def calib_changed(self):
        self.emit("calib", ratio=self.sink_ratio(), casts=len(self.calm_floors), auto=AUTO_CALIB)

    def learn(self, calm, end_t):
        """Запомнить, сколько поплавка было видно в спокойные моменты заброса (без последней
        секунды перед подсечкой): низкий процентиль — это то, как сильно поплавок «проседает»
        на волнах и под дождём. Порог подсечки ставится ниже этого уровня."""
        ratios = [r for t, r in calm if t < end_t - 1.0]
        if len(ratios) < 40:
            return
        old = self.sink_ratio()
        self.calm_floors.append(float(np.percentile(ratios, 2)))
        new = self.sink_ratio()
        self.calib_changed()
        if AUTO_CALIB and (len(self.calm_floors) == CALIB_MIN_CASTS or abs(new - old) >= 0.03):
            self.log(tr("Автокалибровка: подсекаю, когда видно меньше %d%% поплавка (по %d забросам).")
                     % (round(100 * new), len(self.calm_floors)))

    # ---------- управление ----------
    def on_toggle(self):
        if self.marking.is_set():
            self.mark = get_cursor()
            self.marking.clear()
            beep(1200, 80)
            return
        self.resume_on_focus = False
        if self.running.is_set():
            self.stop_fishing(tr("Пауза (по вашей команде)."), notify=False)
            return
        if not terraria_window():
            self.log(tr("Сначала переключитесь в окно Terraria."), "ask")
            self.state("idle", tr("Нужно окно Terraria"), tr("Переключитесь в игру и нажмите %s") % self.key_name)
            return
        self.fails = self.recover_round = self.errors = self.rod_misses = 0
        if self.started is None:
            self.started = time.time()
        if self.has_points():
            self.log(tr("Продолжаю: точка заброса и поплавок прежние."), "good")
        else:
            self.cast_point = get_cursor()
            self.mark = self.bobber = self.mark0 = self.bobber0 = None
            self.rod_slot = self.rod_name = self.bobber_kind = None
            self.gear_changed()
            self.phase, self.watched = "unknown", None
            self.calm_floors.clear()      # новое место — калибруемся заново
            self.log(tr("Старт. Точка заброса: %s.%s") % (self.cast_point, tr(" Подсекаете вы.") if self.record else ""),
                     "good")
        self.running.set()
        self.points_changed()
        self.stats()
        beep(880)

    def reset_points(self):
        """Забыть точку заброса и поплавок: следующий старт — с выбором новых."""
        self.resume_on_focus = False
        self.stop_fishing(tr("Пауза: выбираем новые точки."), notify=False)
        self.cast_point = self.mark = self.bobber = self.mark0 = self.bobber0 = None
        self.rod_slot = self.rod_name = self.bobber_kind = None
        self.gear_changed()
        self.calm_floors.clear()
        self.calib_changed()
        self.delete_points()
        self.log(tr("Точки сброшены. Наведите курсор на воду и нажмите %s.") % self.key_name, "ask")
        self.state("idle", tr("Выберите новые точки"), self.idle_hint())
        self.points_changed()

    def stop_fishing(self, reason, notify=True):
        """Пауза. notify — показать системное уведомление (если пауза не по команде игрока)."""
        self.marking.clear()
        if self.running.is_set():
            self.running.clear()
            self.log(reason, "bad" if notify else "info")
            self.state("pause", tr("Пауза"), self.idle_hint())
            if notify:
                self.emit("notify", title=tr("Рыбалка на паузе"), text=reason)
                beep(330, 300)
            else:
                beep(440)

    def pause(self, reason):
        self.resume_on_focus = False
        self.stop_fishing(tr("Пауза: ") + reason)

    def pause_window(self):
        """Игрок переключился в другое окно. Если можно — продолжим сами, когда он вернётся."""
        if AUTO_RESUME and self.has_points():
            self.stop_fishing(tr("Пауза: окно Terraria не активно. Вернитесь в игру — продолжу сам."),
                              notify=False)
            self.resume_on_focus = True
            self.focus_since = None
            self.state("pause", tr("Пауза"), tr("Вернитесь в игру — продолжу сам через %d с") % RESUME_AFTER)
        else:
            self.pause(tr("окно Terraria не активно"))

    def forget_bobber(self):
        """Забыть поплавок — при следующем забросе программа попросит отметить его снова."""
        self.bobber = self.bobber0 = self.mark0 = None
        self.bobber_kind = None
        self.gear_changed()
        self.points_changed()

    def stopped(self):
        return not self.running.is_set() or self.quit.is_set()

    def wait(self, seconds):
        """Сон, который прерывается паузой/выходом. False — если прервали."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            if self.stopped():
                return False
            time.sleep(0.02)
        return True

    def reel(self, msg, kind="info"):
        """Вытащить поплавок (вызывается, только когда он точно в воде)."""
        click(*self.cast_point)
        self.phase, self.watched = "idle", None
        set_cursor(*self.park)
        self.log(msg, kind)
        self.wait(REEL_DELAY)

    def fail(self, msg):
        """Неудачный заброс: вытащить (если поплавок всё же в воде) и, если так уже
        MAX_FAILS раз подряд, встать на паузу."""
        self.fails += 1
        self.stats()
        # Не кликаем вслепую: клик мог бы и вытащить, и забросить. Где поплавок — посмотрим
        # на следующем круге и тогда решим.
        self.phase, self.watched = "unknown", None
        self.log("%s (%d/%d)" % (msg, self.fails, MAX_FAILS), "bad")
        self.wait(REEL_DELAY)
        if self.fails < MAX_FAILS or self.stopped():
            return
        if AUTO_RECOVER and self.recover_round < len(RECOVER_WAITS):
            # Не сдаёмся: ждём (вдруг наступит утро, пройдёт дождь, уплывёт что-то мешающее),
            # возвращаемся к исходной отметке и пробуем снова.
            delay = RECOVER_WAITS[self.recover_round]
            self.recover_round += 1
            self.fails = 0
            if self.mark0 is not None:
                self.mark = self.mark0
            self.log(tr("Не получается %d раз подряд — попробую снова через %d с (попытка %d из %d).")
                     % (MAX_FAILS, delay, self.recover_round, len(RECOVER_WAITS)), "bad")
            self.state("search", tr("Восстанавливаюсь…"), tr("Попробую снова через %d с") % delay)
            self.wait(delay)
            return
        self.recover_round = 0
        self.pause(tr("не получается %d раз подряд. Нет наживки?") % MAX_FAILS)

    def save_dbg(self, name, img, **kw):
        if self.debug or self.record:
            save_png(img, os.path.join(RECORD_DIR if self.record else DEBUG_DIR, name), **kw)

    # ---------- поиск поплавка ----------
    def ask_mark(self, sct, cl):
        """Первый заброс: игрок сам показывает поплавок. Программа уточняет место (ищет
        поплавок рядом с курсором) и запоминает, как он выглядит. Возвращает центр или None."""
        tw, th, snap = self.tw, self.th, self.snap
        hint = tr("Наведите курсор на поплавок в игре и нажмите %s") % self.key_name
        while True:
            self.log(tr(">>> Наведите курсор на ПОПЛАВОК и нажмите %s.") % self.key_name, "ask")
            self.state("mark", tr("Отметьте поплавок"), hint)
            beep(660, 200)
            self.mark = None
            self.marking.set()
            while self.marking.is_set():
                if self.stopped():
                    self.marking.clear()
                    return None
                time.sleep(0.03)
            if self.mark is None:
                return None
            set_cursor(*self.park)      # убираем курсор, чтобы он не попал в снимок поплавка
            if not self.wait(0.3):
                return None
            area = rect_around(self.mark, tw // 2 + snap, th // 2 + snap)
            if not inside(area, cl):
                self.log(tr("Отметка слишком близко к краю окна — попробуйте ещё раз."), "ask")
                hint = tr("Отметка у края окна. Наведите на поплавок и нажмите %s ещё раз") % self.key_name
                continue
            frame = grab(sct, area)
            corner = snap_adaptive(frame, tw, th, self.min_bobber_px)
            if corner is None:
                self.log(tr("Рядом с курсором не видно поплавка — наведите точнее, прямо на него."), "ask")
                hint = tr("Рядом с курсором нет поплавка. Наведите прямо на него и нажмите %s") % self.key_name
                self.n += 1
                self.save_dbg("%03d_ne_poplavok.png" % self.n, frame, scale=6)
                continue
            x, y = corner
            self.adopt_bobber(area, frame, x, y)
            self.identify_bobber(frame)
            self.log(tr("Поплавок запомнен: %s. Дальше — автоматически.") % (self.mark,), "good")
            return self.mark

    def identify_bobber(self, frame):
        """Какой это поплавок (по картинкам с Вики) — чтобы потом находить его и по картинке."""
        if self.bobber_sprites is None:
            return
        best = self.bobber_sprites.find(frame, self.sprite_scales())
        if best is not None and best[0] >= SPRITE_MIN:
            self.bobber_kind = best[5]
            self.log(tr("Это %s.") % self.bobber_sprites.title(best[5]))
        else:
            self.bobber_kind = None
        self.gear_changed()
        self.save_points()

    def adopt_bobber(self, area, frame, x, y):
        """Запомнить поплавок, найденный в кадре frame (снят с экрана в area) в углу (x, y)."""
        tw, th = self.tw, self.th
        self.mark = (area["left"] + x + tw // 2, area["top"] + y + th // 2)
        self.bobber = frame[y:y + th, x:x + tw].copy()
        self.mark0, self.bobber0 = self.mark, self.bobber.copy()
        self.emit("bobber", img=self.bobber)
        self.points_changed()
        self.save_points()
        self.n += 1
        self.save_dbg("%03d_poplavok.png" % self.n, self.bobber, scale=8)

    # ---------- удочка и поплавки с Вики ----------
    def gear_changed(self):
        rods = sprite_names = None
        if self.rods is not None:
            rods = self.rods.rods
        if self.bobber_sprites is not None:
            sprite_names = self.bobber_sprites
        self.emit("gear", rod_slot=self.rod_slot,
                  rod=rods.title(self.rod_name) if rods and self.rod_name else None,
                  bobber=sprite_names.title(self.bobber_kind) if sprite_names and self.bobber_kind else None)

    def sprite_scales(self):
        """Масштабы, в которых искать поплавок: около Zoom из настроек (игра не бывает мельче 100 %)."""
        return sorted({max(1.0, round(self.scale, 2))} |
                      {v for v in (1.0, 1.25, 1.5, 1.75, 2.0) if abs(v - self.scale) <= 0.3})

    def hotbar_frame(self, sct, cl):
        region = {"left": cl[0], "top": cl[1], "width": min(cl[2] - cl[0], 1000),
                  "height": min(cl[3] - cl[1], 200)}
        return grab(sct, region)

    def ensure_rod(self, sct, cl):
        """Удочка должна быть в руках. Первый раз запоминаем её слот (обычно — тот, что выбран
        при старте: с ним игрок и рыбачит), потом, если выбран другой слот, жмём цифру слота удочки.
        True — переключили предмет (значит, старый поплавок, если был, игра убрала)."""
        if not AUTO_ROD or self.rods is None:
            return False
        import hotbar
        frame = self.hotbar_frame(sct, cl)
        if self.rod_slot is None:
            r = self.rods.scores(frame)
            if r is None:
                return False                 # хотбара не видно (открыт инвентарь, карта…)
            index, out = r
            self.hotbar_u = hotbar.selected_slot(frame)[1]
            self.rod_misses = 0
            best = max(range(len(out)), key=lambda i: out[i][0])
            others = [v for i, (v, _) in enumerate(out) if i != best]
            if out[index][0] >= ROD_SELECTED_MIN:
                self.rod_slot, self.rod_name = index, out[index][1]
            elif (best != index and out[best][0] >= ROD_OTHER_MIN and
                  out[best][0] - max(others, default=0) >= ROD_MARGIN):
                self.rod_slot, self.rod_name = best, out[best][1]
            else:
                self.rod_slot, self.rod_name = index, None
            if self.rod_name:
                self.log(tr("Удочка: %s, слот %d.") % (self.rods.rods.title(self.rod_name), (self.rod_slot + 1) % 10))
            else:
                self.log(tr("Удочку по картинке не узнал — считаю, что она в слоте %d (он был выбран).")
                         % ((self.rod_slot + 1) % 10))
            self.gear_changed()
        sel = hotbar.selected_slot(frame)
        # хотбар другого размера — значит, это не он (открыт инвентарь и т. п.): ничего не жмём
        if sel is None or sel[0] == self.rod_slot or abs(sel[1] - self.hotbar_u) > 0.1:
            return False
        if self.rod_misses >= 3:
            return False                     # переключить не получается — больше не пытаемся
        # игрок сам взял удочку из другого слота? тогда запоминаем новый слот и ничего не жмём
        r = self.rods.scores(frame)
        if r is not None and r[1][sel[0]][0] >= ROD_SELECTED_MIN:
            self.rod_slot, self.rod_name = sel[0], r[1][sel[0]][1]
            self.log(tr("Удочка теперь в слоте %d.") % ((self.rod_slot + 1) % 10))
            self.gear_changed()
            return False
        key = str((self.rod_slot + 1) % 10)
        press_key(key)
        time.sleep(0.3)
        sel2 = hotbar.selected_slot(self.hotbar_frame(sct, cl))
        if sel2 is not None and sel2[0] == self.rod_slot:
            self.rod_misses = 0
            self.log(tr("В руках был другой предмет (слот %d) — взял удочку (слот %s).")
                     % ((sel[0] + 1) % 10, key), "good")
        else:
            self.rod_misses += 1
            self.log(tr("Нажал %s, чтобы взять удочку, но слот не сменился.") % key, "bad")
            if self.rod_misses >= 3:
                self.log(tr("Не получается взять удочку клавишей — больше не переключаю. "
                            "Возьмите удочку в руки сами."), "bad")
                self.emit("notify", title=tr("Удочка"), text=tr("Не получается взять удочку. Возьмите её в руки сами."))
        return True

    def sprite_candidates(self, frame, n=8, changed=None):
        """Места, где может быть поплавок: пятна ярких цветов, не похожих на небо и воду
        (лучшие n, не ближе ширины поплавка друг к другу). Список (x, y) центров.
        changed — маска того, что изменилось после заброса (тогда ищем только среди нового)."""
        tw, th = self.tw, self.th
        if frame.shape[0] < th or frame.shape[1] < tw:
            return []
        k = min(1.0, light_factor(frame))
        # фон — обычный цвет своей же строки: небо, вода (у поверхности светлее, чем в глубине)
        # и кромка воды идут горизонтальными полосами, а поплавок занимает в строке мало места
        row_bg = np.median(frame, 1)[:, None, :]
        far = np.abs(frame - row_bg).max(2) > BG_DIST * k
        vivid = (frame.max(2) - frame.min(2)) > SAT_MIN * k
        m = far & vivid
        if changed is not None:
            m &= changed
        # только «сплошные» места (все соседи 3x3 тоже яркие): у поплавка они есть, а у тонких
        # полос — светлой кромки воды, лески, контуров — нет, иначе они забирают всех кандидатов
        core = m.copy()
        core[0, :] = core[-1, :] = core[:, 0] = core[:, -1] = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                core[1:-1, 1:-1] &= m[1 + dy:m.shape[0] - 1 + dy, 1 + dx:m.shape[1] - 1 + dx]
        m = core.astype(np.int32)
        ii = np.pad(m.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        sums = (ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]).astype(np.float64)
        # поплавок — отдельное пятно: в окне вдвое больше вокруг него ярких мест почти не прибавляется.
        # У больших ярких областей (пирс, постройки, NPC, отражения) — прибавляется много
        py, px = th // 2, tw // 2
        jj = np.pad(np.pad(m, ((py, py), (px, px))).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        H, W = th + 2 * py, tw + 2 * px
        big = (jj[H:, W:] - jj[:-H, W:] - jj[H:, :-W] + jj[:-H, :-W]).astype(np.float64)
        if changed is None:
            sums[sums < 0.5 * big] = 0
        out = []
        for _ in range(n):
            y, x = np.unravel_index(int(sums.argmax()), sums.shape)
            if sums[y, x] < 2:
                break
            out.append((int(x) + tw // 2, int(y) + th // 2))
            sums[max(0, y - th):y + th, max(0, x - tw):x + tw] = -1
        return out

    def sprite_search(self, frame, only=None, changed=None, n=8):
        """Поплавок по картинкам с Вики: (оценка, центр x, центр y, ключ) или None."""
        if self.bobber_sprites is None:
            return None
        pad_x, pad_y = self.tw + int(8 * self.scale), self.th + int(8 * self.scale)
        best = None
        for cx, cy in self.sprite_candidates(frame, n, changed):
            x0, y0 = max(0, cx - pad_x), max(0, cy - pad_y)
            patch = frame[y0:cy + pad_y, x0:cx + pad_x]
            r = self.bobber_sprites.find(patch, self.sprite_scales(), only=only)
            if r and (best is None or r[0] > best[0]):
                v, x, y, w, h, key, s = r
                best = (v, x0 + x + w // 2, y0 + y + h // 2, key)
        return best

    def mark_area(self, cl, player):
        """Где искать поплавок после первого заброса: между игроком и точкой заброса и чуть дальше."""
        s = self.scale
        cx, cy = self.cast_point
        x0 = max(cl[0], min(player[0], cx) - int(120 * s))
        x1 = min(cl[2], max(player[0], cx) + int(160 * s))
        y0 = max(cl[1], min(player[1], cy) - int(160 * s))
        y1 = min(cl[3], max(player[1], cy) + int(120 * s))
        if x1 - x0 < 3 * self.tw or y1 - y0 < 3 * self.th:
            return None
        return {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}

    def auto_mark(self, sct, cl, player):
        """Первый заброс: найти поплавок самому по картинкам поплавков с Вики — между игроком
        и точкой заброса (и чуть дальше). Возвращает центр или None (тогда попросим отметить)."""
        if not AUTO_MARK or self.bobber_sprites is None:
            return None
        s, tw, th = self.scale, self.tw, self.th
        area = self.mark_area(cl, player)
        if area is None:
            return None
        x0, y0 = area["left"], area["top"]
        frame = grab(sct, area)
        before = self.mark_before
        if before is not None and before.shape != frame.shape:
            before = None
        # сам игрок, удочка у него в руках и курсор (он над головой игрока) — не поплавок
        for (px, py), hx, hy in ((player, int(28 * s), int(45 * s)), (self.park, int(25 * s), int(25 * s))):
            px, py = px - x0, py - y0
            for img in (frame, before):
                if img is not None:
                    img[max(0, py - hy):max(0, py + hy), max(0, px - hx):max(0, px + hx)] = frame[0, 0]
        best = None
        if before is not None:
            # главное: поплавок появился только после заброса. Пирс, столбы, NPC и прочее
            # яркое стоят на месте — среди изменившегося их нет
            changed = np.abs(frame - before).max(2) > 30
            best = self.sprite_search(frame, changed=changed, n=10)
        if best is None or best[0] < SPRITE_MIN:
            # снимка до заброса нет или новое не похоже на поплавок — ищем среди всего яркого,
            # но строже (там больше похожего)
            other = self.sprite_search(frame)
            if other is not None and other[0] >= SPRITE_MIN + 0.05 and (best is None or other[0] > best[0]):
                best = other
        self.n += 1
        self.save_dbg("%03d_avto_poisk.png" % self.n, frame, scale=2,
                      rects=[(best[1] - tw // 2, best[2] - th // 2, tw, th,
                              (0, 255, 0) if best[0] >= SPRITE_MIN else (0, 0, 255))] if best else [])
        if best is None or best[0] < SPRITE_MIN:
            if best is not None:
                self.log(tr("Похожее на поплавок: %s, совпадение %.2f — мало.")
                         % (self.bobber_sprites.title(best[3]), best[0]))
            return None
        v, bx, by, key = best
        # уточняем место так же, как при отметке курсором
        snap = self.snap
        center = (x0 + bx, y0 + by)
        near = rect_around(center, tw // 2 + snap, th // 2 + snap)
        nx0, ny0 = max(cl[0], near["left"]), max(cl[1], near["top"])     # у края окна — обрезаем
        nx1 = min(cl[2], near["left"] + near["width"])
        ny1 = min(cl[3], near["top"] + near["height"])
        if nx1 - nx0 < tw or ny1 - ny0 < th:
            return None
        near = {"left": nx0, "top": ny0, "width": nx1 - nx0, "height": ny1 - ny0}
        near_frame = grab(sct, near)
        corner = snap_adaptive(near_frame, tw, th, self.min_bobber_px)
        if corner is None:                         # пятно не выделилось — берём место по картинке
            corner = (int(np.clip(center[0] - nx0 - tw // 2, 0, near["width"] - tw)),
                      int(np.clip(center[1] - ny0 - th // 2, 0, near["height"] - th)))
        self.bobber_kind = key
        self.adopt_bobber(near, near_frame, *corner)
        self.gear_changed()
        self.log(tr("Поплавок нашёлся сам: %s (совпадение %.2f), %s. Дальше — автоматически.")
                 % (self.bobber_sprites.title(key), v, self.mark), "good")
        return self.mark

    def search(self, sct, cl, center, half_x, half_y, wide=False, strict=False, update=True):
        """Ищет поплавок в зоне вокруг center. Возвращает (центр или None, непохожесть).
        Обычный поиск — по текущему образцу. Широкий (wide) — ещё и по образцу, который
        отметил игрок, и просто по цветам поплавка."""
        tw, th = self.tw, self.th
        zone = rect_around(center, half_x + tw // 2, half_y + th // 2)
        zone["left"], zone["top"] = max(cl[0], zone["left"]), max(cl[1], zone["top"])
        zone["width"] = min(cl[2], zone["left"] + zone["width"]) - zone["left"]
        zone["height"] = min(cl[3], zone["top"] + zone["height"]) - zone["top"]
        if zone["width"] < tw + 2 or zone["height"] < th + 2:
            return None, float("inf")
        frame = grab(sct, zone)
        best_err, hit, blob = float("inf"), None, False
        templates = [self.bobber]
        if wide and self.bobber0 is not None:
            templates.append(self.bobber0)
        for tmpl in templates:
            y, x, err = match(frame, tmpl)
            best_err = min(best_err, err)
            # Непохожесть растёт, когда меняется небо (закат, рассвет), хотя поплавок на месте.
            # Поэтому главное — есть ли в найденном месте сплошное яркое пятно поплавка.
            m = 6
            y0, x0 = max(0, y - m), max(0, x - m)
            corner = snap_adaptive(frame[y0:y + th + m, x0:x + tw + m], tw, th, self.min_bobber_px)
            if corner is not None:
                cand = (x0 + corner[0], y0 + corner[1])
                # в широкой зоне бывает яркое и не поплавок (доски пирса, факелы) — сверяем цвета
                if not wide or any(same_colors(frame[cand[1]:cand[1] + th, cand[0]:cand[0] + tw], r)
                                   for r in (self.bobber, self.bobber0) if r is not None):
                    hit, blob = cand, True
                    break
            if err <= NOT_FOUND_ERR and not strict:
                hit = (x, y)
                break
        if hit is None and wide:
            corner = snap_adaptive(frame, tw, th, self.min_bobber_px)
            ref = self.bobber0 if self.bobber0 is not None else self.bobber
            patch = frame[corner[1]:corner[1] + th, corner[0]:corner[0] + tw] if corner is not None else None
            # похоже и цветом, и силуэтом (отражения, факелы и доски бывают того же цвета)
            if (corner is not None and same_colors(patch, ref) and
                    bobber_likeness(patch, ref) >= SIMILAR_MIN):
                hit, blob = corner, True
        self.n += 1
        if hit:
            self.save_dbg("%03d_poisk%s.png" % (self.n, "_shiroko" if wide else ""), frame, scale=4,
                          rects=[(hit[0], hit[1], tw, th, (0, 255, 0))])
        else:
            self.save_dbg("%03d_poisk%s_net.png" % (self.n, "_shiroko" if wide else ""), frame, scale=4)
        if hit is None:
            return None, best_err
        x, y = hit
        if blob and update:
            self.bobber = frame[y:y + th, x:x + tw].copy()   # обновляем образец под текущее освещение
        pos = (zone["left"] + x + tw // 2, zone["top"] + y + th // 2)
        if self.debug:
            self.log(tr("Поплавок: %s, непохожесть %.0f, пятно поплавка: %s%s")
                     % (pos, best_err, tr("есть") if blob else tr("нет"), tr(" (широкий поиск)") if wide else ""))
        return pos, best_err

    def similarity(self, sct, pos):
        """Насколько силуэт в месте pos похож на запомненный поплавок (лучшее из текущего и
        исходного образца)."""
        patch = grab(sct, rect_around(pos, self.tw // 2, self.th // 2))
        refs = [r for r in (self.bobber, self.bobber0, getattr(self, "bobber_ref", None))
                if r is not None and r.shape == patch.shape]
        return max((bobber_likeness(patch, r) for r in refs), default=0.0)

    def bobber_in_water(self, sct, cl):
        """Лежит ли поплавок в воде прямо сейчас (например, продолжаем после паузы). Засчитываем,
        только если найденное похоже на запомненный поплавок и стоит на месте на двух снимках
        подряд: только что заброшенный (ещё летящий) поплавок ждём, пока не сядет."""
        last = None
        end = time.perf_counter() + SETTLE_TIME + 1.5
        while time.perf_counter() < end:
            # образец не обновляем, пока не убедились, что это поплавок, а не что-то похожее рядом
            pos, _ = self.search(sct, cl, self.mark, self.zone_x, self.zone_y, strict=True, update=False)
            ok = pos is not None and self.similarity(sct, pos) >= SIMILAR_MIN
            if ok and last is not None and max(abs(pos[0] - last[0]), abs(pos[1] - last[1])) <= 4:
                return pos
            if not ok and last is None and pos is None:
                return None                      # с первого взгляда ничего нет — поплавка нет
            last = pos if ok else None
            if not self.wait(0.4):
                return None
        return None

    def locate(self, sct, cl):
        """Найти поплавок после заброса. Если его нет на обычном месте — подождать (вдруг
        ещё не упал) и поискать шире вокруг места, которое отметил игрок."""
        pos, err = self.search(sct, cl, self.mark, self.zone_x, self.zone_y)
        if pos:
            return pos, err
        self.state("search", tr("Ищу поплавок"), tr("На обычном месте его нет — ищу вокруг отметки"))
        if not self.wait(1.0):
            return None, err
        pos, err = self.search(sct, cl, self.mark, self.zone_x, self.zone_y)
        if pos:
            return pos, err
        self.log(tr("Поплавка нет на обычном месте — ищу шире вокруг отметки…"))
        home = self.mark0 or self.mark
        pos, err2 = self.search(sct, cl, home, self.zone_x * 3, self.zone_y * 3, wide=True)
        if pos is None and self.bobber_kind and self.bobber_sprites is not None:
            pos = self.sprite_locate(sct, cl, home)
        if pos is None:
            return None, min(err, err2)
        if max(abs(pos[0] - self.mark[0]), abs(pos[1] - self.mark[1])) > self.zone_x // 2:
            self.mark = pos
            self.log(tr("Нашёл поплавок в стороне %s — теперь ищу его там.") % (pos,))
        else:
            self.log(tr("Нашёл поплавок."))
        return pos, err2

    def sprite_locate(self, sct, cl, home):
        """Поплавок не узнали по образцу (сильно сменилось освещение) — ищем по картинке
        этого вида поплавка с Вики вокруг отметки. Нашли — обновляем образец."""
        zone = rect_around(home, self.zone_x * 3 + self.tw, self.zone_y * 3 + self.th)
        zone["left"], zone["top"] = max(cl[0], zone["left"]), max(cl[1], zone["top"])
        zone["width"] = min(cl[2], zone["left"] + zone["width"]) - zone["left"]
        zone["height"] = min(cl[3], zone["top"] + zone["height"]) - zone["top"]
        if zone["width"] < 3 * self.tw or zone["height"] < 3 * self.th:
            return None
        frame = grab(sct, zone)
        best = self.sprite_search(frame, only=[self.bobber_kind])
        if best is None or best[0] < SPRITE_MIN:
            return None
        tw, th = self.tw, self.th
        x = int(np.clip(best[1] - tw // 2, 0, frame.shape[1] - tw))
        y = int(np.clip(best[2] - th // 4 - th // 2, 0, frame.shape[0] - th))   # как при отметке
        self.bobber = frame[y:y + th, x:x + tw].copy()
        self.log(tr("Узнал поплавок по картинке (%s, совпадение %.2f).")
                 % (self.bobber_sprites.title(self.bobber_kind), best[0]))
        return zone["left"] + x + tw // 2, zone["top"] + y + th // 2

    # ---------- основной цикл ----------
    def worker(self):
        with (getattr(mss, "MSS", None) or mss.mss)() as sct:
            while not self.quit.is_set():
                if not self.running.is_set():
                    self.watch_focus()
                    time.sleep(0.05)
                    continue
                try:
                    self.cycle(sct)
                except Exception as e:  # чтобы поток не умер молча
                    self.errors += 1
                    self.log(tr("Ошибка: %r") % e, "bad")
                    if AUTO_RECOVER and self.errors <= 3:
                        self.log(tr("Попробую продолжить через 5 с."))
                        self.wait(5)
                        continue
                    self.errors = 0
                    self.emit("notify", title=tr("Ошибка"), text=repr(e))
                    self.pause(tr("ошибка"))

    def watch_focus(self):
        """На паузе из-за другого окна: как только игрок пару секунд снова в игре — продолжаем."""
        if not (self.resume_on_focus and AUTO_RESUME and self.has_points()):
            self.focus_since = None
            return
        if not terraria_window():
            self.focus_since = None
            return
        now = time.perf_counter()
        if self.focus_since is None:
            self.focus_since = now
        elif now - self.focus_since >= RESUME_AFTER:
            self.resume_on_focus = False
            self.focus_since = None
            self.log(tr("Вы вернулись в игру — продолжаю."), "good")
            self.on_toggle()

    # ---------- зелья ----------
    def check_buffs(self, sct, cl, force=False):
        """Есть ли нужные баффы. Нет — нажать быстрый бафф и проверить, получилось ли."""
        if self.buffs is None or not (BUFFS_ON or force):
            return None
        now = time.time()
        if not force and now - self.last_buff_check < BUFF_CHECK_EVERY:
            return None
        self.last_buff_check = now
        region = {"left": cl[0], "top": cl[1], "width": min(cl[2] - cl[0], 900),
                  "height": min(cl[3] - cl[1], 360)}
        want = [n for n in self.buffs.icons if BUFF_WANT.get(n)]
        have = self.buffs.find(grab(sct, region))
        status = {n: have[n] >= BUFF_THRESHOLD() for n in want}
        self.emit("buffs", status=status)
        if force:
            return status
        missing = [n for n in want if not status[n] and now >= self.buff_backoff.get(n, 0)]
        if not missing:
            return status
        press_key(BUFF_KEY)
        time.sleep(0.9)
        have = self.buffs.find(grab(sct, region))
        for n in missing:
            if have[n] >= BUFF_THRESHOLD():
                self.log(tr("Выпил: %s.") % tr(BUFF_NAMES[n]), "good")
            else:
                self.buff_backoff[n] = now + BUFF_BACKOFF
                self.log(tr("Не вижу баффа «%s» и после быстрого баффа — кончились зелья?") % tr(BUFF_NAMES[n]),
                         "bad")
                self.emit("notify", title=tr("Зелья"),
                          text=tr("Не получается выпить: %s. Кончились зелья?") % tr(BUFF_NAMES[n]))
        status = {n: have[n] >= BUFF_THRESHOLD() for n in want}
        self.emit("buffs", status=status)
        return status

    def cycle(self, sct):
        hwnd = terraria_window()
        if not hwnd:
            self.pause_window()
            return
        cl = client_rect(hwnd)
        cx, cy = self.cast_point
        player = ((cl[0] + cl[2]) // 2, (cl[1] + cl[3]) // 2)  # камера держит игрока в центре
        # пока ждём — курсор над головой персонажа, подальше от поплавка
        self.park = (player[0] + (10 if cx >= player[0] else -10),
                     max(cl[1] + 30, player[1] - int(130 * self.scale)))

        # 0. Удочка в руках? (если игрок переключал предметы — берём её обратно)
        if self.ensure_rod(sct, cl):
            # сменили предмет — игра убирает поплавок из воды, следить не за чем
            self.phase, self.watched = "idle", None
            if not self.wait(0.2):
                return
        # Зелья: нет баффа — выпить (быстрым баффом)
        self.check_buffs(sct, cl)

        # Поплавок уже в воде (например, продолжаем после паузы)? Тогда не забрасываем —
        #    клик по воде вытащил бы его — а сразу следим за ним.
        pos = None
        set_cursor(*self.park)
        if self.phase == "watching" and self.watched is not None:
            # Пауза была во время ожидания поклёвки: лежит ли поплавок там же, где был?
            # Смотрим на силуэт и цвет самого поплавка (небо и вода в сравнении не участвуют).
            wpos, wframe = self.watched
            self.bobber_ref = wframe[self.track_ry:self.track_ry + self.th, self.track_rx:self.track_rx + self.tw]
            region = rect_around(wpos, self.tw // 2, self.th // 2)
            if inside(region, cl) and self.similarity(sct, wpos) >= SIMILAR_MIN:
                pos = wpos
                self.log(tr("Поплавок уже в воде — продолжаю следить за ним."))
            else:
                self.phase, self.watched = "unknown", None
        if pos is None and self.phase == "unknown" and self.bobber is not None and self.mark is not None:
            pos = self.bobber_in_water(sct, cl)
            if self.stopped():
                return
            if pos:
                self.log(tr("Поплавок уже в воде — продолжаю следить за ним."))
            else:
                self.phase = "idle"

        # 1. заброс
        if pos is None:
            self.state("cast", tr("Заброс"), tr("Мышь не трогайте"))
            self.mark_before = None
            if self.bobber is None and AUTO_MARK and self.bobber_sprites is not None:
                # снимок до заброса: потом поплавок найдётся среди того, что появилось
                area = self.mark_area(cl, player)
                if area is not None:
                    set_cursor(*self.park)
                    time.sleep(0.05)
                    self.mark_before = grab(sct, area)
            click(cx, cy)
            self.phase, self.watched = "unknown", None     # заброшен, но ещё не нашли
            self.casts += 1
            self.stats()
            if self.bobber is None:
                pos = None
                if AUTO_MARK and self.bobber_sprites is not None:
                    set_cursor(*self.park)
                    self.state("search", tr("Ищу поплавок"), tr("Мышь не трогайте"))
                    if not self.wait(SETTLE_TIME):
                        return
                    pos = self.auto_mark(sct, cl, player)
                    if pos is None and not self.stopped():
                        self.log(tr("Сам поплавок не нашёл — покажите его, пожалуйста."))
                if pos is None:
                    pos = self.ask_mark(sct, cl)
                if pos is None:
                    if not self.stopped():
                        self.pause(tr("поплавок не отмечен"))
                    return
            else:
                set_cursor(*self.park)
                if not self.wait(SETTLE_TIME):
                    return
                self.state("search", tr("Ищу поплавок"), tr("Мышь не трогайте"))
                pos, err = self.locate(sct, cl)
                if pos is None:
                    if self.stopped():          # поставили на паузу во время поиска — это не неудача
                        return
                    self.fail(tr("Поплавок не найден (непохожесть %.0f).") % err)
                    return

        # 2. ждём поклёвку: следим, сколько поплавка видно над водой
        tw, th, rx, ry = self.tw, self.th, self.track_rx, self.track_ry
        watch = rect_around(pos, tw // 2 + rx, th // 2 + ry)
        if not inside(watch, cl):
            self.reel(tr("Поплавок у края окна — перезаброс."))
            return
        first = grab(sct, watch)
        side = 1 if pos[0] >= player[0] else -1
        palette = bobber_palette(first, (rx, ry, tw, th), side)
        det = BiteDetector(palette, debug=self.debug)
        base = det.visible(first) if len(palette) else 0
        k = light_factor(first)
        if base < self.min_bobber_px and k < 0.95:      # темно (ночь, пещера) — смягчаем пороги
            palette = bobber_palette(first, (rx, ry, tw, th), side, k)
            det = BiteDetector(palette, debug=self.debug)
            base = det.visible(first) if len(palette) else 0
        for ref in (self.bobber, self.bobber0):          # запасной путь: цвета из образца поплавка
            for kk in (1.0, k):
                if base >= self.min_bobber_px or ref is None:
                    break
                palette = template_palette(ref, first, side, kk)
                det = BiteDetector(palette, debug=self.debug)
                base = det.visible(first) if len(palette) else 0
        det.ratio = self.sink_ratio()
        if base < self.min_bobber_px:
            self.fail(tr("Поплавок почти не виден (%d пикс.).") % base)
            return
        self.fails = self.recover_round = self.errors = 0
        self.phase, self.watched = "watching", (pos, first)
        self.stats()
        if self.record:
            while not self.clicks.empty():
                self.clicks.get_nowait()
            self.log(tr("Ждите поклёвку и подсекайте сами (курсор к поплавку не подводите)."), "ask")
            self.state("wait", tr("Подсекайте сами"), tr("Клюнуло — кликните мышью (не наводя на поплавок)"))
        else:
            self.state("wait", tr("Жду поклёвку"), tr("Мышь не трогайте. %s — пауза") % self.key_name)
        samples, frames = [], deque(maxlen=120)
        calm = []                       # (t, доля видимого поплавка) — для автокалибровки
        auto_t = auto_why = None
        max_wait = 120.0 if self.record else MAX_WAIT
        start = last_live = time.perf_counter()
        while True:
            if self.stopped():
                return
            if not terraria_window():
                self.pause_window()
                return
            now = time.perf_counter()
            if now - start > max_wait:
                self.learn(calm, now - start + 1.0)
                self.reel(tr("Нет поклёвки %d с — перезаброс.") % max_wait)
                return
            if self.record:
                try:
                    t_click = self.clicks.get_nowait() - start
                except queue.Empty:
                    pass
                else:
                    self.phase, self.watched = "idle", None
                    self.learn(calm, t_click)
                    self.report(det, samples, frames, first, t_click, auto_t, auto_why)
                    self.wait(REEL_DELAY)
                    return

            frame = grab(sct, watch)
            t = now - start
            why = det.feed(frame, t)
            if det.ref and not det.flash and det.seen >= det.ref * 0.8:
                self.watched = (pos, frame)          # спокойный кадр — таким место и запомним
            if det.ref and not det.flash and t >= CALIB_TIME:
                calm.append((t, det.seen / det.ref))
            if now - last_live > 0.1:
                last_live = now
                self.emit("live", seen=det.seen, ref=det.ref, ratio=det.ratio, frame=frame,
                          t=t, max_wait=max_wait, flash=det.flash, auto=AUTO_CALIB and
                          len(self.calm_floors) >= CALIB_MIN_CASTS)
            if self.record:
                if why and auto_t is None:
                    auto_t, auto_why = t, why
                samples.append((t, det.seen, det.ref))
                frames.append((t, frame))
            elif why:
                self.hooks += 1
                self.stats()
                self.state("hook", tr("Поклёвка!"), tr("Подсекаю…"))
                self.emit("hook", why=why, waited=t)
                self.save_dbg("%03d_poklevka.png" % self.n, np.concatenate([first, frame], axis=1), scale=6)
                self.learn(calm, t)
                self.reel(tr("Поклёвка (%s)! Подсекаю. Подсечек: %d (ждали %.1f с)")
                          % (why, self.hooks, t), "good")
                return
            time.sleep(POLL)

    # ---------- режим записи ----------
    def on_click(self, x, y, button, pressed, injected=False):
        # клики самой программы (injected) не считаем
        if (self.record and pressed and not injected and button == mouse.Button.left
                and self.running.is_set()):
            self.clicks.put(time.perf_counter())

    def report(self, det, samples, frames, first, t_click, auto_t, auto_why):
        self.hooks += 1
        self.stats()
        if not det.ref:
            self.log(tr("Подсечка №%d через %.1f с — слишком рано, программа ещё делала замер (%.1f с).")
                     % (self.hooks, t_click, CALIB_TIME))
            return
        quiet = [s[1] / s[2] for s in samples if s[2] and s[0] < t_click - 1.0]
        last = [s[1] / s[2] for s in samples if s[2] and s[0] >= t_click - 1.0]
        fmt = lambda v: (tr("видно от %d%% до %d%% поплавка") % (100 * min(v), 100 * max(v))) if v else tr("нет данных")
        if auto_t is None:
            auto = tr("НЕ сработал бы")
        elif auto_t < t_click - 1.0:
            auto = tr("сработал бы РАНЬШЕ, на %.1f с (%s) — ложное срабатывание?") % (auto_t, auto_why)
        else:
            auto = tr("сработал бы на %.2f с (%s) — верно") % (auto_t, auto_why)
        lines = [
            tr("Подсечка №%d через %.1f с после заброса (обычно видно %.0f пикс. поплавка, порог %d%%)")
            % (self.hooks, t_click, det.ref, 100 * det.ratio),
            tr("  Спокойно (до последней секунды): ") + fmt(quiet),
            tr("  Последняя секунда перед подсечкой: ") + fmt(last),
            tr("  Автомат: ") + auto,
        ]
        for line in lines:
            self.log(line)

        os.makedirs(RECORD_DIR, exist_ok=True)
        path = os.path.join(RECORD_DIR, "%03d" % self.n)
        with open(path + ".txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + tr("\n\nt, видно пикселей, обычно\n"))
            for t, seen, ref in samples:
                f.write("%.3f, %d, %.0f\n" % (t, seen, ref))
        # кадры: в начале и за 0.8 … 0 с до подсечки
        shots = [first]
        for back in (0.8, 0.6, 0.4, 0.2, 0.0):
            cand = [fr for t, fr in frames if t <= t_click - back]
            if cand:
                shots.append(cand[-1])
        save_png(np.concatenate(shots, axis=1), path + "_kadry.png", scale=6)
        self.log(tr("  Сохранено: record/%03d.txt и record/%03d_kadry.png") % (self.n, self.n))

    # ---------- запуск ----------
    def on_press(self, key):
        if key == self.toggle_key:
            self.on_toggle()
        elif self.reset_key is not None and key == self.reset_key and not self.marking.is_set():
            self.reset_points()
        elif self.exit_key is not None and key == self.exit_key:
            self.shutdown()
            return False

    def start(self):
        """Запускает рабочий поток и перехват клавиш/мыши. Не блокирует."""
        threading.Thread(target=self.worker, daemon=True).start()
        for listener in (keyboard.Listener(on_press=self.on_press), mouse.Listener(on_click=self.on_click)):
            listener.daemon = True
            listener.start()
            self.listeners.append(listener)
        if self.points_path and self.load_points():
            self.log(tr("Точки с прошлого запуска загружены. %s — продолжить.") % self.key_name, "good")
            self.emit("bobber", img=self.bobber)
            self.points_changed()
        self.state("idle", tr("Готов"), self.idle_hint())

    def shutdown(self):
        self.save_points()
        self.running.clear()
        self.marking.clear()
        self.quit.set()
        for listener in self.listeners:
            listener.stop()

    def run(self):
        """Консольная версия."""
        k = self.key_name
        if self.record:
            log(tr("Terraria AutoFish — РЕЖИМ ЗАПИСИ (забрасывает программа, подсекаете вы)."))
        else:
            log(tr("Terraria AutoFish готов.%s") % (tr("  [DEBUG: картинки в папке debug]") if self.debug else ""))
        log(tr("  1) Возьмите удочку, наживка в инвентаре, поплавок не заброшен."))
        log(tr("  2) Наведите курсор на воду (в 5+ блоках от персонажа) и нажмите %s.") % k)
        log(tr("  3) Программа забросит. Наведите курсор на поплавок и снова нажмите %s.") % k)
        if self.record:
            log(tr("  4) Увидели поклёвку — кликните сами. Сделайте так 5–10 раз."))
        else:
            log(tr("  4) Дальше всё само. %s — пауза / продолжить с теми же точками.") % k)
        log(tr("  %s — выбрать новые точки.") % self.reset_name)
        log(tr("  %s — выход.") % (self.exit_key and EXIT_KEY.upper()))
        self.start()
        try:
            while not self.quit.is_set():
                self.quit.wait(0.2)
        except KeyboardInterrupt:
            self.shutdown()
        log(tr("Выход. Подсечек за сессию: %d") % self.hooks)


def main():
    global SCALE
    ap = argparse.ArgumentParser(description=tr("Автоматическая рыбалка для Terraria"))
    ap.add_argument("--debug", action="store_true", help=tr("печатать замеры и сохранять картинки"))
    ap.add_argument("--record", action="store_true", help=tr("режим записи: подсекаете вы, программа записывает"))
    ap.add_argument("--scale", type=float, help=tr("Zoom в игре (1.0 = 100%%, 2.0 = 200%%)"))
    args = ap.parse_args()
    if args.scale:
        SCALE = args.scale
    Fisher(debug=args.debug, record=args.record, exit_key=EXIT_KEY, reset_key=RESET_KEY).run()


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit(tr("Работает только в Windows."))
    main()
