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


def bobber_palette(frame, box, far_side):
    """Цвета надводной части поплавка: насыщенные пиксели в рамке box (x, y, w, h) выше
    линии воды, которых нет в фоне. Фон — верхние строки (небо), нижние (вода) и
    3 столбца с края far_side (-1 левый, +1 правый) — со стороны, противоположной леске:
    там небо, вода и блики у линии воды. По краю же находим линию воды."""
    edge = frame[:, :3] if far_side < 0 else frame[:, -3:]
    sky = np.median(frame[:3].reshape(-1, 3), 0)
    water = np.median(frame[-3:].reshape(-1, 3), 0)
    rows = np.median(edge, 1)
    wet = np.abs(rows - water).max(1) < np.abs(rows - sky).max(1)
    waterline = int(np.argmax(wet)) if wet.any() else frame.shape[0]
    bg = np.concatenate([edge.reshape(-1, 3), frame[:3].reshape(-1, 3), frame[-3:].reshape(-1, 3)])
    bg = np.unique((bg // 4) * 4, axis=0)
    x, y, w, h = box
    px = frame[y:min(y + h, waterline + 1), x:x + w].reshape(-1, 3)
    if not len(px):
        return px
    far = np.abs(px[:, None] - bg[None]).max(2).min(1) > BG_DIST
    vivid = (px.max(1) - px.min(1)) > SAT_MIN
    return np.unique((px[far & vivid] // 4) * 4, axis=0)


def snap_bobber(frame, w, h, min_px):
    """Ищет в кадре место w x h с наибольшим числом ярких насыщенных пикселей, не похожих
    на небо (верхние строки) и воду (нижние). Возвращает (x, y) левого верхнего угла или None."""
    sky = np.median(frame[:3].reshape(-1, 3), 0)
    water = np.median(frame[-3:].reshape(-1, 3), 0)
    far = np.minimum(np.abs(frame - sky).max(2), np.abs(frame - water).max(2)) > BG_DIST
    vivid = (frame.max(2) - frame.min(2)) > SAT_MIN
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
      hook     {why, waited}                  — подсечка
      notify   {title, text}                  — важное: пауза не по вашей команде, ошибка
    """

    def __init__(self, debug=False, record=False, events=None, toggle_key=None, exit_key=None,
                 reset_key=None):
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
        self.calm_floors = deque(maxlen=8)  # автокалибровка: «спокойный минимум» по последним забросам
        self.hooks = self.casts = self.fails = 0
        self.started = None                # когда начали рыбачить (для «подсечек в час»)
        self.n = 0
        self.listeners = []
        self.set_hotkey(toggle_key or TOGGLE_KEY)
        self.exit_key = key_from_name(exit_key) if exit_key else None
        self.set_reset_key(reset_key)
        self.set_scale(SCALE)

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
        if self.running.is_set():
            self.stop_fishing(tr("Пауза (по вашей команде)."), notify=False)
            return
        if not terraria_window():
            self.log(tr("Сначала переключитесь в окно Terraria."), "ask")
            self.state("idle", tr("Нужно окно Terraria"), tr("Переключитесь в игру и нажмите %s") % self.key_name)
            return
        self.fails = 0
        if self.started is None:
            self.started = time.time()
        if self.has_points():
            self.log(tr("Продолжаю: точка заброса и поплавок прежние."), "good")
        else:
            self.cast_point = get_cursor()
            self.mark = self.bobber = self.mark0 = self.bobber0 = None
            self.calm_floors.clear()      # новое место — калибруемся заново
            self.log(tr("Старт. Точка заброса: %s.%s") % (self.cast_point, tr(" Подсекаете вы.") if self.record else ""),
                     "good")
        self.running.set()
        self.points_changed()
        self.stats()
        beep(880)

    def reset_points(self):
        """Забыть точку заброса и поплавок: следующий старт — с выбором новых."""
        self.stop_fishing(tr("Пауза: выбираем новые точки."), notify=False)
        self.cast_point = self.mark = self.bobber = self.mark0 = self.bobber0 = None
        self.calm_floors.clear()
        self.calib_changed()
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
        self.stop_fishing(tr("Пауза: ") + reason)

    def forget_bobber(self):
        """Забыть поплавок — при следующем забросе программа попросит отметить его снова."""
        self.bobber = self.bobber0 = self.mark0 = None
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
        click(*self.cast_point)
        set_cursor(*self.park)
        self.log(msg, kind)
        self.wait(REEL_DELAY)

    def fail(self, msg):
        """Неудачный заброс: вытащить (если поплавок всё же в воде) и, если так уже
        MAX_FAILS раз подряд, встать на паузу."""
        self.fails += 1
        self.stats()
        self.reel("%s (%d/%d)" % (msg, self.fails, MAX_FAILS), "bad")
        if self.fails >= MAX_FAILS:
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
            corner = snap_bobber(frame, tw, th, self.min_bobber_px)
            if corner is None:
                self.log(tr("Рядом с курсором не видно поплавка — наведите точнее, прямо на него."), "ask")
                hint = tr("Рядом с курсором нет поплавка. Наведите прямо на него и нажмите %s") % self.key_name
                self.n += 1
                self.save_dbg("%03d_ne_poplavok.png" % self.n, frame, scale=6)
                continue
            x, y = corner
            self.mark = (area["left"] + x + tw // 2, area["top"] + y + th // 2)
            self.bobber = frame[y:y + th, x:x + tw].copy()
            self.mark0, self.bobber0 = self.mark, self.bobber.copy()
            self.emit("bobber", img=self.bobber)
            self.points_changed()
            self.n += 1
            self.save_dbg("%03d_poplavok.png" % self.n, self.bobber, scale=8)
            self.log(tr("Поплавок запомнен: %s. Дальше — автоматически.") % (self.mark,), "good")
            return self.mark

    def search(self, sct, cl, center, half_x, half_y, wide=False):
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
            corner = snap_bobber(frame[y0:y + th + m, x0:x + tw + m], tw, th, self.min_bobber_px)
            if corner is not None:
                hit, blob = (x0 + corner[0], y0 + corner[1]), True
                break
            if err <= NOT_FOUND_ERR:
                hit = (x, y)
                break
        if hit is None and wide:
            corner = snap_bobber(frame, tw, th, self.min_bobber_px)
            if corner is not None and same_colors(frame[corner[1]:corner[1] + th, corner[0]:corner[0] + tw],
                                                   self.bobber0 if self.bobber0 is not None else self.bobber):
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
        if blob:
            self.bobber = frame[y:y + th, x:x + tw].copy()   # обновляем образец под текущее освещение
        pos = (zone["left"] + x + tw // 2, zone["top"] + y + th // 2)
        if self.debug:
            self.log(tr("Поплавок: %s, непохожесть %.0f, пятно поплавка: %s%s")
                     % (pos, best_err, tr("есть") if blob else tr("нет"), tr(" (широкий поиск)") if wide else ""))
        return pos, best_err

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
        if pos is None:
            return None, min(err, err2)
        if max(abs(pos[0] - self.mark[0]), abs(pos[1] - self.mark[1])) > self.zone_x // 2:
            self.mark = pos
            self.log(tr("Нашёл поплавок в стороне %s — теперь ищу его там.") % (pos,))
        else:
            self.log(tr("Нашёл поплавок."))
        return pos, err2

    # ---------- основной цикл ----------
    def worker(self):
        with (getattr(mss, "MSS", None) or mss.mss)() as sct:
            while not self.quit.is_set():
                if not self.running.is_set():
                    time.sleep(0.05)
                    continue
                try:
                    self.cycle(sct)
                except Exception as e:  # чтобы поток не умер молча
                    self.log(tr("Ошибка: %r") % e, "bad")
                    self.emit("notify", title=tr("Ошибка"), text=repr(e))
                    self.pause(tr("ошибка"))

    def cycle(self, sct):
        hwnd = terraria_window()
        if not hwnd:
            self.pause(tr("окно Terraria не активно"))
            return
        cl = client_rect(hwnd)
        cx, cy = self.cast_point
        player = ((cl[0] + cl[2]) // 2, (cl[1] + cl[3]) // 2)  # камера держит игрока в центре
        # пока ждём — курсор над головой персонажа, подальше от поплавка
        self.park = (player[0] + (10 if cx >= player[0] else -10),
                     max(cl[1] + 30, player[1] - int(130 * self.scale)))

        # 1. заброс
        self.state("cast", tr("Заброс"), tr("Мышь не трогайте"))
        click(cx, cy)
        self.casts += 1
        self.stats()
        if self.bobber is None:
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
                self.fail(tr("Поплавок не найден (непохожесть %.0f).") % err)
                return

        # 2. ждём поклёвку: следим, сколько поплавка видно над водой
        tw, th, rx, ry = self.tw, self.th, self.track_rx, self.track_ry
        watch = rect_around(pos, tw // 2 + rx, th // 2 + ry)
        if not inside(watch, cl):
            self.reel(tr("Поплавок у края окна — перезаброс."))
            return
        first = grab(sct, watch)
        palette = bobber_palette(first, (rx, ry, tw, th), 1 if pos[0] >= player[0] else -1)
        det = BiteDetector(palette, debug=self.debug)
        det.ratio = self.sink_ratio()
        base = det.visible(first) if len(palette) else 0
        if base < self.min_bobber_px:
            self.fail(tr("Поплавок почти не виден (%d пикс.).") % base)
            return
        self.fails = 0
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
                self.pause(tr("окно Terraria не активно"))
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
                    self.learn(calm, t_click)
                    self.report(det, samples, frames, first, t_click, auto_t, auto_why)
                    self.wait(REEL_DELAY)
                    return

            frame = grab(sct, watch)
            t = now - start
            why = det.feed(frame, t)
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
        self.state("idle", tr("Готов"), self.idle_hint())

    def shutdown(self):
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
