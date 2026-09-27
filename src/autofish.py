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
from pynput import keyboard, mouse

import chat  # noqa: E402,F401  (события в чате)
import i18n
from i18n import tr

i18n.set_lang("auto")

# ============================ НАСТРОЙКИ ============================
TOGGLE_KEY = "home"   # старт / отметить поплавок / пауза (имя клавиши из pynput: home, insert, f6 ...)
EXIT_KEY = "end"      # выход из консольной версии
RESET_KEY = "delete"  # выбрать новые точки (в приложении с окном — настраивается)

SCALE = 1.0           # «Масштаб» (Zoom) в настройках игры: 100% -> 1.0, 150% -> 1.5, 200% -> 2.0

SETTLE_TIME = 1.6     # сек. после заброса, дольше которых поплавок точно уже в воде
SETTLE_MIN = 0.6      # сек. после заброса, раньше которых поплавок не ищем (ещё летит)
CALIB_TIME = 0.3      # сек. замера, сколько поплавка видно обычно
MAX_WAIT = 45.0       # сек. без поклёвки -> вытащить и забросить заново
REEL_DELAY = 0.7      # сек. после подсечки до нового заброса
POLL = 1 / 60.0       # сек. между снимками при ожидании поклёвки (игра рисует 60 кадров в секунду)

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
CALIB_MARGIN = 0.15   #   порог = «спокойный минимум» (сколько поплавка видно на волнах) минус столько
CALIB_MAX = 0.8       #   ...но не выше этого
CALIB_MIN = 0.55      #   ...и не ниже этого: поклёвки часто уводят поплавок только до 50–75 %
CALIB_SKIP = 0.6      #   первые столько секунд слежения поплавок ещё покачивается после приводнения —
                      #   для калибровки их не берём
CALIB_PCT = 10        #   «спокойный минимум» — такой процентиль (а не самый низкий кадр)
JUMP_DROP = 0.25      # поклёвка ещё и так: поплавок резко (за JUMP_WINDOW с) потерял столько
JUMP_WINDOW = 0.25    #   своей видимой части — даже если до порога подсечки не дошёл
JUMP_CONFIRM = 2      #   ...и так на стольких снимках подряд
CALIB_MIN_CASTS = 1   #   после стольких забросов порог подбирается по прошлым забросам
CALIB_NOW = 1.0       #   а до того — по текущему: через столько секунд спокойной воды

AUTO_RECOVER = True   # после сбоев не вставать на паузу сразу, а пробовать продолжить
RECOVER_EVERY = 2.0   # сколько секунд ждать перед каждым новым кругом попыток (без конца)
AUTO_RESUME = True    # пауза из-за переключения в другое окно — продолжить, когда вернётесь в игру
RESUME_AFTER = 2.0    #   ...через столько секунд в игре

BUFFS_ON = False      # следить за зельями и пить их (клавишей быстрого баффа)
BUFF_WANT = {"fishing": True, "crate": True, "sonar": False, "calm": False}   # какие баффы держать
BUFF_KEY = "b"        # клавиша быстрого баффа в Terraria (по умолчанию B)
BUFF_METHOD = "hotbar"    # как пить: "hotbar" — нужное зелье из хотбара (цифра слота + клик),
                          #   "quick" — быстрым баффом (выпивает все зелья-баффы из инвентаря)
POTION_MIN = 0.6      # зелье в слоте хотбара узнаём, если картинка с Вики совпала хотя бы так
POTION_MIN_SINGLE = 0.7   # ...а в слоте без числа (зелье одно — игра число не пишет) — хотя бы так
POTION_RETRY = 60.0   # зелья нет в хотбаре — снова смотреть через столько секунд
POTION_REMIND = True  # напоминать, что нужного зелья нет в хотбаре
POTION_NAG_EVERY = 600.0  # ...одно и то же напоминание — не чаще, чем раз в столько секунд
BUFF_CHECK_EVERY = 20.0   # как часто проверять баффы, секунд
BUFF_BACKOFF = 300.0  # если выпить не получилось (кончились зелья) — не пробовать столько секунд
SONAR_FILTER = False  # выбирать улов по зелью сонара: подсекать только отмеченное в списках улова
CATCH_WANT = {}       # что ловить: {группа (биом, "crates", "rare", "junk"): множество id}; пусто — всё
CATCH_BIOME = "auto"  # где рыбачим: ключ биома или "auto" — угадывать по тому, что клюёт
SONAR_SKIP_PAUSE = 1.0    # пропустили ненужный улов — столько секунд не считать поклёвкой
SKIP_MIN_RATIO = 0.6  # отпускать улов, только если название прочитано уверенно: похожесть не ниже
SKIP_MIN_MARGIN = 0.15    #   ...и отрыв от второго по похожести названия не меньше (иначе — подсекаем)
LEARN_MIN_RATIO = 0.6     # название прочитано так уверенно — запомнить, как оно выглядит (память надписей)
LEARN_MIN_MARGIN = 0.2
READ_PICKUP = True    # после подсечки читать над персонажем, что поймано (биом, учёт улова)
SONAR_TEXT_BITE = True    # с выбором улова по сонару поклёвка — ещё и появление надписи над поплавком
SONAR_TEXT_EVERY = 0.05   #   ...смотреть на место надписи раз в столько секунд
BOBBER_PARTS = (0.55, 0.4)   # какая доля поплавка сверху видна: в воде / в лаве (она непрозрачная)
GAME_NAMES = True     # названия улова брать из установленной игры (Terraria.exe), а не только с Вики
QUEST_FISH = None     # рыба для задания рыбака (id): поймали — пауза и уведомление
MARK_CANDIDATES = 16   # автопоиск поплавка: столько самых заметных мест проверять (ночью поплавок тусклый)
NEAR_PENALTY = 0.15    # автопоиск поплавка: место у игрока или позади него — оценка ниже на столько
THROW_BEYOND = 420     # быстрые удочки бросают дальше курсора: искать поплавок и за ним на столько пикселей
AUTO_ZOOM = True      # при первом автопоиске поплавка узнать Zoom игры по размеру поплавка
ZOOMS = (1.0, 1.25, 1.5, 1.75, 2.0)   # какие бывают (игра не мельче 100 %)
EVENTS_STOP = True        # событие в чате (луны, затмение, вторжения, боссы) — вытащить поплавок и переждать
DEATH_STOP = True         # персонаж погиб — остановить рыбалку совсем (без самопродолжения)
CHAT_EVERY = 2.0          # как часто смотреть в чат, секунд
RECENT_PICTURES = 60  # сколько последних картинок помнить для кнопки «Что-то не так»
NO_BITE_RESET = 3     # столько перезабросов подряд без поклёвки — вернуться к исходному образцу поплавка
FOLLOW_SHIFT = True   # вся картинка сдвинулась (персонажа сдвинуло) — перенести точки на столько же
SHIFT_MIN = 3         #   ...если сдвиг хотя бы столько пикселей
ROD_KEY_WAITS = (0.3, 0.5, 0.8)   # взять удочку: попыток нажать цифру слота и сколько ждать после каждой
ROD_RETRY_AFTER = 120.0   # не получилось трижды — снова пробовать через столько секунд
INV_FULL_STOP = True  # улов перестал подбираться (инвентарь полон) — остановиться
INV_FULL_HOOKS = 3    #   ...если после стольких подсечек подряд нет надписи о подборе
PICKUP_TEXT_LIFE = 3.0   # столько секунд без надписи о подборе — место над персонажем уже чистое
PICKUP_MERGE_MAX = 10.0  # старая надпись (к ней игра прибавляет число) висит не дольше стольких секунд
AUTO_ROD = True       # перед забросом брать удочку в руки (клавишей её слота в хотбаре)
AUTO_MARK = True      # после первого заброса искать поплавок самому (по картинкам поплавков с Вики)
SPRITE_MIN = 0.75     # насколько картинка на экране должна совпасть с поплавком с Вики
ROD_SLOT = None       # слот удочки: None — запоминать самому (по удачному забросу), 0..9 — задан вручную
ROD_HINT_MIN = 0.45       # пока слот неизвестен: удочка — слот с числом наживки, похожий на удочку хотя бы так
ROD_HINT_MARGIN = 0.1     # ...и лучше других слотов с числом (зелья, стопки) хотя бы на столько
HEALTH_GUARD = True   # персонаж получает урон — вытащить поплавок и встать на паузу
HEALTH_DROP = 0.08    #   урон — когда сердечек стало меньше на эту долю (одно сердце из 20 — 5 %)
HEALTH_EVERY = 0.5    #   как часто смотреть на сердечки, секунд
BAIT_WATCH = True     # следить за наживкой: мало — предупредить, кончилась — остановиться
STOP_AFTER_MIN = 0    # остановиться через столько минут рыбалки (0 — не останавливаться)
STOP_AFTER_HOOKS = 0  # ...или после стольких подсечек (0 — не останавливаться)
SHUTDOWN_AFTER = False    # после такой остановки выключить компьютер (через SHUTDOWN_DELAY секунд)
SHUTDOWN_DELAY = 60
SOUND = True          # пищать при старте, отметке, паузе
# ==================================================================

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # реальные пиксели при масштабе Windows 125/150%
except Exception:
    user32.SetProcessDPIAware()

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
# Папки: SRC — исходники (src), ROOT — корень проекта, HERE — папка программы (где .exe; из
# исходников — корень проекта). Всё, что программа пишет сама (журналы, отладочные картинки,
# записи, снимки хотбара, отчёты), — в одной папке DATA_DIR рядом с ней.
SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ROOT
DATA_DIR = os.path.join(HERE, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
# картинки (иконки баффов): внутри .exe — во временной папке PyInstaller, иначе — рядом со скриптом
ASSET_DIR = os.path.join(getattr(sys, "_MEIPASS", ROOT), "assets")
RECORD_DIR = os.path.join(DATA_DIR, "record")


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


_exe_names = {}   # pid -> имя .exe (окно игры проверяется на каждом снимке — не спрашиваем Windows зря)


def window_exe(hwnd):
    """Имя .exe процесса, которому принадлежит окно (в нижнем регистре), и его pid."""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in _exe_names:
        return _exe_names[pid.value], pid.value
    name = ""
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wt.DWORD(520)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value).lower()
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    if name:
        if len(_exe_names) > 200:
            _exe_names.clear()
        _exe_names[pid.value] = name
    return name, pid.value


def is_game_window(hwnd):
    """Окно самой игры: Terraria или tModLoader. Не окна этой программы («Terraria AutoFish»
    тоже начинается с «Terraria») и не консоль сервера."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    if not looks_like_game(buf.value, "", 0):
        return False                          # по заголовку — точно не игра (процесс не проверяем)
    exe, pid = window_exe(hwnd)
    return looks_like_game(buf.value, exe, pid)


def looks_like_game(title, exe, pid):
    """По заголовку окна, имени .exe и pid: игра ли это (Terraria / tModLoader)."""
    title = title.lower()
    if not (title.startswith("terraria") or title.startswith("tmodloader")) or "autofish" in title:
        return False
    return not (pid == os.getpid() or "server" in exe or "autofish" in exe)


def terraria_window():
    """hwnd активного окна, если это Terraria / tModLoader, иначе None."""
    hwnd = user32.GetForegroundWindow()
    if hwnd and is_game_window(hwnd):
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


BUFF_NAMES = {"fishing": "зелье рыбалки", "crate": "ящичное зелье", "sonar": "зелье сонара",
              "calm": "успокоительное зелье"}


def schedule_shutdown(seconds):
    """Выключить компьютер через seconds секунд (отменить: cancel_shutdown или shutdown /a)."""
    import subprocess
    subprocess.Popen(["shutdown", "/s", "/t", str(int(seconds)), "/c", "Terraria AutoFish"],
                     creationflags=0x08000000)


def cancel_shutdown():
    import subprocess
    subprocess.Popen(["shutdown", "/a"], creationflags=0x08000000)


def BUFF_THRESHOLD():
    import buffs
    return buffs.THRESHOLD


def find_terraria():
    """Окно Terraria, даже если оно сейчас не активно (для проверки баффов из окна программы)."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd) and is_game_window(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(each, 0)
    return found[0] if found else None


# --- части движка в отдельных модулях (им нужен уже определённый autofish) ---
sys.modules.setdefault("autofish", sys.modules[__name__])
from vision import (BiteDetector, _background, _pick_colors, bobber_likeness, bobber_mask,  # noqa: E402,F401  (нужны и другим модулям — через A.имя)
                    bobber_palette, color_match, heart_mask, heart_rows, inside, light_factor, match,
                    patch_similarity, rect_around, same_colors, shape_similarity, snap_adaptive, snap_bobber,
                    template_palette)
from fisher_gear import GearMixin  # noqa: E402
from fisher_search import SearchMixin  # noqa: E402
from fisher_extras import ExtrasMixin  # noqa: E402
from fisher_catch import CatchMixin  # noqa: E402


class Fisher(GearMixin, SearchMixin, ExtrasMixin, CatchMixin):
    """Движок рыбалки. События для интерфейса отправляет в events(kind, data):
      log      {text, kind}                   — строка журнала (kind: info, good, bad, ask)
      state    {state, title, hint}           — что сейчас происходит
      stats    {hooks, casts, fails, started} — счётчики
      live     {seen, ref, ratio, frame, t, max_wait, flash} — живые замеры (~10 раз в секунду)
      bobber   {img}                          — запомненный поплавок
      points   {saved}                        — сохранены ли точка заброса и поплавок
      calib    {ratio, casts, auto}           — порог подсечки (автокалибровка)
      buffs    {status}                       — какие баффы есть: {"fishing": True, ...}
      gear     {rod_slot, manual, bobber}     — слот удочки (0..9 или None), задан ли он вручную, вид поплавка
      bait     {digits}                       — сколько цифр в числе наживки на удочке (0 — нет наживки)
      catch    {id, name, wanted, biome}      — сонар: что клюнуло и ловим ли
      shutdown {seconds}                      — компьютер выключится через seconds секунд (0 — отменено)
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
        self.skipped = 0                   # сколько поклёвок пропустили по сонару (не нужный улов)
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
        self.absent_potions = ()           # каких нужных зелий нет в хотбаре (о чём уже сказали)
        self.absent_told = 0.0             # когда последний раз напоминали
        try:                               # удочки и поплавки с Вики (для хотбара и поиска поплавка)
            import hotbar
            import sprites
            self.rods = hotbar.RodFinder(os.path.join(ASSET_DIR, "rods"))
            try:                           # образцы цифр — читать число наживки на удочке
                self.digit_reader = hotbar.DigitReader(os.path.join(ASSET_DIR, "digits.npz"))
            except Exception:
                self.digit_reader = None
            self.potions = hotbar.ItemFinder(os.path.join(ASSET_DIR, "potions"), need_count=False)
            self.bobber_sprites = sprites.SpriteSet(os.path.join(ASSET_DIR, "bobbers"), part=BOBBER_PARTS,
                                                    names=sprites.BOBBER_NAMES)
        except Exception:
            self.rods = self.bobber_sprites = self.potions = self.digit_reader = None
        try:                               # что ловится в каждом биоме (для выбора улова по сонару)
            import catches
            self.catches = catches.Catches(os.path.join(ASSET_DIR, "fishing", "catches.json"))
        except Exception:
            self.catches = None
        if self.catches is not None and GAME_NAMES:
            try:                           # русские названия — как пишет сама игра, а не как на Вики
                import gamenames
                self.catches.use_game_names(gamenames.load())
            except Exception:
                pass
        self.recent_catch = deque(maxlen=12)   # что клевало в последнее время (id) — чтобы угадать биом
        self.heat_hinted = False
        self.pickup_clean = None           # (область, снимок) места над персонажем без надписи о подборе
        self.pickup_last = 0.0             # когда последний раз видели надпись о подборе
        self.pickup_last_id = None         # что тогда было подобрано           # подсказали про «Искажение от тепла» (надписи над лавой)
        self.ocr_ok = None                 # доступно ли распознавание текста Windows
        try:                               # память надписей: как выглядят названия уже узнанного улова
            import textmemory
            self.memory = textmemory.TextMemory(
                os.path.join(os.path.dirname(points_path), "names.npz") if points_path else None)
        except Exception:
            self.memory = None
        self.caught = {}                   # что поймано (по надписи о подборе): id -> сколько раз
        self.caught_unknown = 0            # подсечки, после которых улов не узнали
        self.pickup_seen = False           # надпись о подборе хоть раз была (значит, её видно)
        self.no_pickup = 0                 # подсечек подряд без надписи о подборе
        self.sonar_buff_warned = 0.0       # когда последний раз предупреждали, что баффа сонара нет
        self.last_sonar_check = 0.0
        self.rod_slot = None               # в каком слоте хотбара удочка (0..9) — запоминаем по удачному забросу
        self.hotbar_u = None               # масштаб интерфейса, при котором видели хотбар
        self.rod_misses = 0                # сколько раз подряд не получилось взять удочку
        self.scene = None                  # снимок места рыбалки (см. follow_shift)
        self.no_bite = 0                   # перезабросов подряд без поклёвки
        self.recent_dbg = deque(maxlen=RECENT_PICTURES)   # последние картинки поиска и поклёвок
        self.zoom_probe = False            # идёт первый автопоиск — пробуем все масштабы
        self.shifts = 0                    # сколько раз переносили точки за сдвигом картинки
        self.rod_miss_time = 0.0            # когда не получилось взять удочку клавишей
        self.cast_slot = None              # какой слот был выбран при последнем забросе
        self.switched = False              # на этом круге сами переключили слот
        self.bobber_kind = None            # какой поплавок (ключ картинки) или None — не узнали
        self.mark_before = None            # снимок места до первого заброса (для поиска поплавка)
        self.hp_base = None                # сколько «сердечных» пикселей при полном (обычном) здоровье
        self.hp_band = None                # строки, где сердечки
        self.hp_low = 0                    # сколько проверок подряд здоровья меньше обычного
        self.hp_last = 0.0
        self.chat_last = 0.0               # когда смотрели в чат
        self.chat_ignore_until = 0.0       # это сообщение уже учли
        self.chat_seen = None              # последняя замеченная строка событий (записываем один раз)
        self.resume_at = None              # когда продолжить самим (пережидаем событие)
        self.event = None                  # какое событие пережидаем (ключ chat.EVENTS)
        self.alive_hp, self.dead_checks = 0, 0   # сердечки живого персонажа / проверок «погиб» подряд
        self.bait_digits = None            # сколько цифр наживки видно на удочке (None — не смотрели)
        self.bait_count = None             # само число наживки (если прочиталось уверенно)
        self.bait_warned = False
        self.calib_logged = 0.0            # какой порог по текущему забросу уже сообщали
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
        self.emit("stats", hooks=self.hooks, casts=self.casts, fails=self.fails, started=self.started,
                  skipped=self.skipped)

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
            with np.load(self.points_path) as d:             # with — чтобы файл не оставался открытым
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
            return float(np.clip(np.median(self.calm_floors) - CALIB_MARGIN, CALIB_MIN, CALIB_MAX))
        return SINK_RATIO

    def calib_changed(self):
        self.emit("calib", ratio=self.sink_ratio(), casts=len(self.calm_floors), auto=AUTO_CALIB)

    def learn(self, calm, end_t):
        """Запомнить, сколько поплавка было видно в спокойные моменты заброса (без последней
        секунды перед подсечкой): низкий процентиль — это то, как сильно поплавок «проседает»
        на волнах и под дождём. Порог подсечки ставится ниже этого уровня."""
        ratios = [r for t, r in calm if CALIB_SKIP <= t < end_t - 1.0]
        if len(ratios) < 20:
            return
        old = self.sink_ratio()
        self.calm_floors.append(float(np.percentile(ratios, CALIB_PCT)))
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
        self.resume_at, self.event = None, None   # игрок сам решил — таймер больше не нужен
        if self.running.is_set():
            self.stop_fishing(tr("Пауза (по вашей команде)."), notify=False)
            return
        if not terraria_window():
            self.log(tr("Сначала переключитесь в окно Terraria."), "ask")
            self.state("idle", tr("Нужно окно Terraria"), tr("Переключитесь в игру и нажмите %s") % self.key_name)
            return
        self.fails = self.recover_round = self.errors = self.rod_misses = 0
        self.hp_base = self.hp_band = None
        self.hp_low = 0
        self.bait_digits = None
        if self.started is None:
            self.started = time.time()
        if self.has_points():
            self.log(tr("Продолжаю: точка заброса и поплавок прежние."), "good")
        else:
            self.cast_point = get_cursor()
            self.mark = self.bobber = self.mark0 = self.bobber0 = None
            self.bobber_kind = None
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
        self.bobber_kind = None
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
        if self.cast_point is not None:
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
        if BAIT_WATCH and self.bait_digits == 0:
            # на удочке в руках нет числа наживки — ждать и пробовать снова бесполезно
            self.phase, self.watched = "unknown", None
            self.log("%s" % msg, "bad")
            self.pause(tr("кончилась наживка (на удочке нет числа наживки)"))
            return
        if self.switched and ROD_SLOT is None and self.rod_slot is not None:
            self.log(tr("Переключился на слот %d, но поплавка нет — может, удочка теперь в другом слоте? "
                        "Забыл этот слот: возьмите удочку в руки, запомню заново.") % ((self.rod_slot + 1) % 10), "bad")
            self.rod_slot = None
            self.save_gear()
            self.gear_changed()
        # Не кликаем вслепую: клик мог бы и вытащить, и забросить. Где поплавок — посмотрим
        # на следующем круге и тогда решим.
        self.phase, self.watched = "unknown", None
        self.log("%s (%d/%d)" % (msg, self.fails, MAX_FAILS), "bad")
        self.wait(REEL_DELAY)
        if self.fails < MAX_FAILS or self.stopped():
            return
        if AUTO_RECOVER:
            # Не сдаёмся: по кругу — подождать, вернуться к исходной отметке и пробовать снова
            self.recover_round += 1
            self.fails = 0
            if self.mark0 is not None:
                self.mark = self.mark0
            if self.bobber0 is not None:
                self.bobber = self.bobber0.copy()
            self.log(tr("Не получается %d раз подряд — попробую снова через %d с (круг %d).")
                     % (MAX_FAILS, RECOVER_EVERY, self.recover_round), "bad")
            if self.recover_round == 10:
                self.emit("notify", title=tr("Рыбалка"),
                          text=tr("Уже %d кругов неудачных забросов — загляните в игру.") % self.recover_round)
            self.state("search", tr("Восстанавливаюсь…"), tr("Попробую снова через %d с") % RECOVER_EVERY)
            self.wait(RECOVER_EVERY)
            return
        self.recover_round = 0
        self.pause(tr("не получается %d раз подряд. Нет наживки?") % MAX_FAILS)

    def save_dbg(self, name, img, **kw):
        # последние картинки помним всегда — для кнопки «Что-то не так» (даже без отладки)
        self.recent_dbg.append((name, np.array(img, np.float32, copy=True), kw))
        if self.debug or self.record:
            save_png(img, os.path.join(RECORD_DIR if self.record else DEBUG_DIR, name), **kw)

    def save_mistake(self, sct, folder, log_lines, extra=None):
        """«Что-то не так»: в один архив — последние картинки поиска и поклёвок, снимок окна игры
        сейчас, конец журнала и настройки движка. Путь к архиву."""
        import io as _io
        import zipfile
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, time.strftime("mistake_%Y%m%d_%H%M%S.zip"))
        tmp = os.path.join(folder, "_mistake_tmp.png")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, img, kw in list(self.recent_dbg):
                save_png(img, tmp, **kw)
                z.write(tmp, "pictures/" + name)
            hwnd = find_terraria()
            if hwnd and sct is not None:
                cl = client_rect(hwnd)
                shot = grab(sct, {"left": cl[0], "top": cl[1], "width": cl[2] - cl[0], "height": cl[3] - cl[1]})
                save_png(shot, tmp)
                z.write(tmp, "game.png")
            z.writestr("log.txt", "\n".join(log_lines))
            state = {"cast_point": self.cast_point, "mark": self.mark, "mark0": self.mark0, "phase": self.phase,
                     "bobber_kind": self.bobber_kind, "scale": self.scale, "hooks": self.hooks,
                     "fails": self.fails, "event": self.event}
            z.writestr("state.txt", "\n".join("%s=%s" % kv for kv in state.items()))
            if self.bobber is not None:
                save_png(self.bobber, tmp, scale=6)
                z.write(tmp, "bobber_now.png")
            if self.bobber0 is not None:
                save_png(self.bobber0, tmp, scale=6)
                z.write(tmp, "bobber_start.png")
            for name, data in (extra or {}).items():
                z.writestr(name, data)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return path


    # ---------- основной цикл ----------
    def worker(self):
        with (getattr(mss, "MSS", None) or mss.mss)() as sct:
            while not self.quit.is_set():
                if not self.running.is_set():
                    self.watch_event(sct)
                    self.watch_focus()
                    time.sleep(0.05)
                    continue
                try:
                    self.cycle(sct)
                except Exception as e:  # чтобы поток не умер молча
                    self.errors += 1
                    self.log(tr("Ошибка: %r") % e, "bad")
                    if AUTO_RECOVER and self.errors <= 3:
                        self.log(tr("Попробую продолжить через 2 с."))
                        self.wait(2)
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


    def cycle(self, sct):
        hwnd = terraria_window()
        if not hwnd:
            self.pause_window()
            return
        cl = client_rect(hwnd)
        if self.cast_point is None:          # точки сбросили, пока шёл круг
            return
        cx, cy = self.cast_point
        player = ((cl[0] + cl[2]) // 2, (cl[1] + cl[3]) // 2)  # камера держит игрока в центре
        # пока ждём — курсор над головой персонажа, подальше от поплавка
        self.park = (player[0] + (10 if cx >= player[0] else -10),
                     max(cl[1] + 30, player[1] - int(130 * self.scale)))

        # Лимит сессии (по времени или подсечкам) и здоровье персонажа
        if self.session_over():
            return
        if self.check_death(sct, cl) or self.check_health(sct, cl):
            return
        if self.check_chat(sct, cl):
            return
        # 0. Удочка в руках? (если игрок переключал предметы — берём её обратно)
        if self.ensure_rod(sct, cl):
            # сменили предмет — игра убирает поплавок из воды, следить не за чем
            self.phase, self.watched = "idle", None
            if not self.wait(0.2):
                return
        # Зелья: нет баффа — выпить (быстрым баффом)
        self.check_buffs(sct, cl)
        self.check_sonar_buff(sct, cl)
        if self.stopped() or self.cast_point is None:
            return                            # пока пили зелья, поставили на паузу или сбросили точки

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
                        if AUTO_ROD and self.rod_target() is None and self.reset_name:
                            self.log(tr("Если в руках не удочка — возьмите её, нажмите %s и начните заново "
                                        "(%s на воде). Слот удочки запомню сам или задайте его на вкладке "
                                        "«Автоматика».") % (self.reset_name, self.key_name), "ask")
                if pos is None:
                    pos = self.ask_mark(sct, cl)
                if pos is None:
                    if not self.stopped():
                        self.pause(tr("поплавок не отмечен"))
                    return
            else:
                set_cursor(*self.park)
                self.state("search", tr("Ищу поплавок"), tr("Мышь не трогайте"))
                pos, err = self.settle(sct, cl)
                if pos is None and not self.stopped():
                    pos, err = self.locate(sct, cl)
                if pos is None:
                    if self.stopped():          # поставили на паузу во время поиска — это не неудача
                        return
                    if self.follow_shift(sct, cl):
                        return                  # картинка сдвинулась — точки перенесли, забросим снова
                    self.fail(tr("Поплавок не найден (непохожесть %.0f).") % err)
                    return

        self.remember_scene(sct, cl, player, pos)   # чтобы заметить, если персонажа сдвинет

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
        if len(det.palette):
            det.fit_top(first)                        # небо над поплавком не считаем (надпись сонара)
        if base < self.min_bobber_px:
            if self.bobber0 is not None:
                self.bobber, self.mark = self.bobber0.copy(), self.mark0   # образец мог «переучиться» на фон
            self.fail(tr("Поплавок почти не виден (%d пикс.).") % base)
            return
        self.fails = self.recover_round = self.errors = 0
        self.phase, self.watched = "watching", (pos, first)
        self.learn_rod()
        self.stats()
        if self.record:
            while not self.clicks.empty():
                self.clicks.get_nowait()
            self.log(tr("Ждите поклёвку и подсекайте сами (курсор к поплавку не подводите)."), "ask")
            self.state("wait", tr("Подсекайте сами"), tr("Клюнуло — кликните мышью (не наводя на поплавок)"))
        else:
            self.state("wait", tr("Жду поклёвку"), tr("Мышь не трогайте. %s — пауза") % self.key_name)
        samples, frames = [], deque(maxlen=120)
        det.auto = AUTO_CALIB
        calm = det.calm                 # (t, доля видимого поплавка) — для автокалибровки
        auto_t = auto_why = None
        max_wait = 120.0 if self.record else MAX_WAIT
        start = last_live = time.perf_counter()
        live_min = None                 # самое малое «видно» между обновлениями полоски
        rd = self.sonar_reader(sct, cl, pos)       # надпись зелья сонара (или None)
        last_base, ignore_until = start, 0.0
        text_on, last_text = False, start          # надпись сонара уже висит / когда смотрели
        while True:
            if self.stopped():
                return
            if not terraria_window():
                self.pause_window()
                return
            now = time.perf_counter()
            if now - self.hp_last >= HEALTH_EVERY:
                if self.check_death(sct, cl) or self.check_health(sct, cl, watching=True):
                    return
            if now - self.chat_last >= CHAT_EVERY:
                if self.check_chat(sct, cl, watching=True):
                    return
            if now - start > max_wait:
                self.learn(calm, now - start + 1.0)
                self.reel(tr("Нет поклёвки %d с — перезаброс.") % max_wait)
                self.no_bite += 1
                if self.no_bite >= NO_BITE_RESET and (self.bobber0 is not None or self.mark0 is not None):
                    # так долго без поклёвок обычно не бывает: вероятно, следим не за поплавком
                    # (образец «переучился» на фон) — возвращаемся к исходным образцу и отметке
                    self.no_bite = 0
                    if self.bobber0 is not None:
                        self.bobber = self.bobber0.copy()
                    if self.mark0 is not None:
                        self.mark = self.mark0
                    self.log(tr("%d раза подряд без поклёвки — вернулся к исходному образцу и отметке поплавка.")
                             % NO_BITE_RESET, "bad")
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
            if rd is not None and SONAR_FILTER and SONAR_TEXT_BITE and now - last_text >= SONAR_TEXT_EVERY:
                # над поплавком появилась надпись сонара — это поклёвка, даже если поплавок ещё не нырнул
                last_text = now
                tw_, th_ = self.tw, self.th
                bx, by = pos[0] - rd.reg["left"], pos[1] - rd.reg["top"]
                present = rd.extract(grab(sct, rd.reg), (bx - tw_ // 2 - 6, by - th_ // 2 - 6,
                                                         bx + tw_ // 2 + 6, by + th_ // 2 + 6)) is not None
                if present and not text_on and not why and t >= CALIB_TIME:
                    why = tr("надпись сонара")
                text_on = present
            if why and t < ignore_until:
                why = None                           # это всё ещё пропущенный (ненужный) улов
            if rd is not None and not why and now - last_base > 1.0 and det.ref and not det.flash \
                    and det.seen >= det.ref * 0.9:
                self.sonar_refresh(sct, rd)          # всё спокойно — обновить снимок фона надписи
                last_base = now
            if det.ref and not det.flash and det.seen >= det.ref * 0.8:
                self.watched = (pos, frame)          # спокойный кадр — таким место и запомним
            if det.raised:                          # порог подняли на лету — сообщаем, если заметно
                det.raised = False
                if abs(det.ratio - self.calib_logged) >= 0.05:
                    self.calib_logged = det.ratio
                    self.log(tr("Автокалибровка по этому забросу: подсекаю, когда видно меньше %d%% поплавка.")
                             % round(100 * det.ratio))
            if not det.flash:
                live_min = det.seen if live_min is None else min(live_min, det.seen)
            if now - last_live > 0.1:
                last_live = now
                # на полоске — самое малое за это время: короткий нырок поплавка тоже будет виден
                self.emit("live", seen=live_min if live_min is not None else det.seen, ref=det.ref,
                          ratio=det.ratio, frame=frame, t=t, max_wait=max_wait, flash=det.flash,
                          auto=AUTO_CALIB)
                live_min = None
            if self.record:
                if why and auto_t is None:
                    auto_t, auto_why = t, why
                    if rd is not None:
                        self.sonar_decide(sct, rd, pos)      # в записи — только прочитать и сохранить
                samples.append((t, det.seen, det.ref))
                frames.append((t, frame))
            elif why:
                dec = self.sonar_decide(sct, rd, pos) if rd is not None else None
                if SONAR_FILTER and dec is not None and not dec[1]:
                    # клюёт то, что не отмечено: не подсекаем, ждём следующую поклёвку
                    self.skipped += 1
                    self.stats()
                    det.hits = det.jumps = 0
                    ignore_until = t + SONAR_SKIP_PAUSE
                    self.log(tr("Сонар: клюёт «%s» — не отмечено, пропускаю.") % self.catch_name(dec[0]))
                    time.sleep(POLL)
                    continue
                if dec is not None:
                    why = "%s, %s" % (self.catch_name(dec[0]), why)
                hooked_id = dec[0] if dec is not None else None
                self.hooks += 1
                self.no_bite = 0
                self.stats()
                self.state("hook", tr("Поклёвка!"), tr("Подсекаю…"))
                self.emit("hook", why=why, waited=t)
                self.save_dbg("%03d_poklevka.png" % self.n, np.concatenate([first, frame], axis=1), scale=6)
                self.learn(calm, t)
                pk = self.pickup_start(sct, cl, player)
                self.reel(tr("Поклёвка (%s)! Подсекаю. Подсечек: %d (ждали %.1f с)")
                          % (why, self.hooks, t), "good")
                caught_id = None
                if pk is not None and not self.stopped():
                    caught_id = self.pickup_read(sct, pk)    # что поймано — для учёта и биома
                self.check_quest(caught_id or hooked_id)
                return
            # ровный шаг: не чаще 60 снимков в секунду (чаще игра кадр не меняет — только нагрузка)
            time.sleep(max(0.0, now + POLL - time.perf_counter()))


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
        if self.points_path:
            self.load_gear()
            self.gear_changed()
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
