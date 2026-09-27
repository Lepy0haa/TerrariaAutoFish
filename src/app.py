"""
Terraria AutoFish — приложение с окном, оверлеем поверх игры и уведомлениями Windows.
Вся логика рыбалки — в autofish.py.
"""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import webbrowser
import time
import winsound
import zlib

import tkinter as tk
from tkinter import ttk

import numpy as np

import autofish as af
import i18n
from i18n import tr

APP = "Terraria AutoFish"
VERSION = "1.6.3"
# Портативная версия: рядом с программой лежит portable.txt — всё хранится в папке программы
PORTABLE = os.path.exists(os.path.join(af.HERE, "portable.txt"))
CFG_DIR = (os.path.join(af.HERE, "settings") if PORTABLE
           else os.path.join(os.environ.get("APPDATA") or af.HERE, "TerrariaAutoFish"))
CFG_PATH = os.path.join(CFG_DIR, "settings.json")
LOG_DIR = os.path.join(af.DATA_DIR, "logs")   # журналы — в data рядом с программой, как debug и record
LOG_DAYS = 14                              # столько дней журналы хранятся
DEFAULTS = {
    "hotkey": "home", "reset_key": "end", "scale": 1.0, "sink_ratio": 0.55, "max_wait": 45,
    "overlay": True, "overlay_pos": None, "toasts": True, "toast_hooks": False,
    "sound": True, "hook_sound": False, "debug": False, "record": False, "win_pos": None,
    "lang": "auto", "auto_calib": True, "auto_recover": True, "auto_resume": True,
    "buffs_on": False, "buff_fishing": True, "buff_crate": True, "buff_key": "b", "buff_method": "hotbar",
    "auto_rod": True, "auto_mark": True, "rod_slot": "auto",
    "buff_sonar": False, "buff_calm": False, "health_guard": True, "bait_watch": True,
    "stop_after_min": 0, "stop_after_hooks": 0, "shutdown_after": False,
    "sonar_filter": False, "catch_biome": "auto", "catch_want": {}, "quest_fish": None,
    "update_checked": 0, "wizard_done": False, "tray": True, "inv_full_stop": True,
    "potion_remind": True, "events_stop": True, "death_stop": True,
    "update_check": True, "donate_nudged": 0,
    "overlay_alpha": 90, "overlay_font": "normal", "overlay_mode": True, "overlay_hide_paused": False,
}
LANGS = [("auto", tr("Авто / Auto")), ("ru", tr("Русский")), ("en", "English")]
HOTKEYS = ["home", "end", "insert", "delete", "page_up", "page_down", "pause", "scroll_lock",
           "f6", "f7", "f8", "f9"]
ZOOMS = ["100%", "125%", "150%", "175%", "200%"]
BUFF_KEYS = list("bvngcxzqhjklmuyt") + list("1234567890")

C = {
    "bg": "#14161b", "panel": "#1c2028", "panel2": "#242a35", "line": "#2e3544",
    "text": "#e8eaed", "muted": "#8f99a6", "green": "#3ecf8e", "yellow": "#f5c542",
    "red": "#ef5350", "blue": "#4aa3ff", "orange": "#ff9f43",
}
STATE_COLOR = {"idle": C["muted"], "cast": C["blue"], "search": C["blue"], "mark": C["yellow"],
               "wait": C["green"], "hook": C["orange"], "pause": C["red"]}
FONT = "Segoe UI"
DONATE_NUDGES = (100, 500, 1000, 2500, 5000, 10000, 25000, 50000)   # на этих числах улова — напомнить

# Уведомления Windows показываем через встроенный PowerShell (без сторонних библиотек)
AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def toast(title, text):
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;").replace("'", "&apos;"))
    xml = ('<toast><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text>'
           '</binding></visual></toast>' % (esc(title), esc(text)))
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
          "ContentType = WindowsRuntime] > $null;"
          "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
          "ContentType = WindowsRuntime] > $null;"
          "$d = New-Object Windows.Data.Xml.Dom.XmlDocument; $d.LoadXml('%s');"
          "$t = [Windows.UI.Notifications.ToastNotification]::new($d);"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show($t)"
          % (xml, AUMID))
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()

    def run():
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                           creationflags=0x08000000, capture_output=True, timeout=20)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def beep_async(freq, ms):
    threading.Thread(target=lambda: winsound.Beep(freq, ms), daemon=True).start()


# ---------- картинки без сторонних библиотек ----------
def png_bytes(img):
    """numpy HxWx3 (RGB) или HxWx4 (RGBA), uint8 -> PNG."""
    img = np.ascontiguousarray(img.astype(np.uint8))
    h, w, ch = img.shape
    raw = b"".join(b"\x00" + img[r].tobytes() for r in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6 if ch == 4 else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def photo(img_rgb, scale=1):
    if scale > 1:
        img_rgb = img_rgb.repeat(scale, 0).repeat(scale, 1)
    return tk.PhotoImage(data=base64.b64encode(png_bytes(img_rgb)))


def bgr_to_rgb(frame):
    return frame[:, :, ::-1].clip(0, 255).astype(np.uint8)


def icon_rgba(n):
    """Значок: поплавок (красный верх, белый низ) над волной, на тёмном скруглённом квадрате."""
    k = 4
    N = n * k
    y, x = (np.mgrid[0:N, 0:N] + 0.5) / N
    img = np.zeros((N, N, 4), np.float32)
    r = 0.2
    cx, cy = np.clip(x, r, 1 - r), np.clip(y, r, 1 - r)
    bgmask = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    img[bgmask] = (22, 30, 44, 255)
    water = bgmask & (y > 0.62 + 0.03 * np.sin(x * 12))
    img[water] = (38, 110, 200, 255)
    d = (x - 0.5) ** 2 + (y - 0.5) ** 2
    ring = d <= 0.26 ** 2
    img[ring] = (15, 15, 20, 255)
    body = d <= 0.22 ** 2
    img[body & (y < 0.5)] = (230, 57, 70, 255)
    img[body & (y >= 0.5)] = (245, 245, 245, 255)
    stick = (np.abs(x - 0.5) < 0.035) & (y > 0.12) & (y < 0.3)
    img[stick] = (15, 15, 20, 255)
    return img.reshape(n, k, n, k, 4).mean((1, 3)).astype(np.uint8)


def write_version_info(path, description, filename):
    """Сведения о файле для PyInstaller (--version-file): название, версия, автор. Без них .exe
    выглядит для антивирусов подозрительнее."""
    v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
    text = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(v)r, prodvers=%(v)r, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Lepy0haa'),
      StringStruct('FileDescription', %(desc)r),
      StringStruct('FileVersion', %(ver)r),
      StringStruct('InternalName', 'TerrariaAutoFish'),
      StringStruct('LegalCopyright', 'Lepy0haa, https://github.com/Lepy0haa/TerrariaAutoFish'),
      StringStruct('OriginalFilename', %(file)r),
      StringStruct('ProductName', 'Terraria AutoFish'),
      StringStruct('ProductVersion', %(ver)r)])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % {"v": v, "desc": description, "ver": VERSION, "file": filename}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    pngs = [png_bytes(icon_rgba(s)) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, p in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(p), offset)
        offset += len(p)
    with open(path, "wb") as f:
        f.write(head + entries + b"".join(pngs))


# ---------- настройки ----------
def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


SELFTEST = False                           # самопроверка сборки: настройки игрока не трогаем


def on_screen(x, y):
    """Есть ли монитор в точке (x, y) рабочего стола (мониторов может быть несколько, левый —
    с отрицательными координатами)."""
    try:
        return bool(ctypes.windll.user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 0))   # 0 — не искать ближайший
    except Exception:
        return True


def ghost(win):
    """Окно самопроверки: невидимое, клики проходят сквозь него, фокус не забирает. Пока идёт
    самопроверка, игрок может рыбачить: окно не должно мешать ни игре, ни кликам рыбалки."""
    try:
        u = ctypes.windll.user32
        hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
        ex = u.GetWindowLongW(hwnd, -20)
        u.SetWindowLongW(hwnd, -20, ex | 0x80000 | 0x20 | 0x08000000)   # LAYERED | TRANSPARENT | NOACTIVATE
        win.attributes("-alpha", 0.0)
    except Exception:
        pass


def save_cfg(cfg):
    if SELFTEST:
        return
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fmt_left(seconds):
    """Сколько осталось: «1 ч 20 мин» / «35 мин» / «меньше минуты»."""
    m = int(seconds // 60)
    if m < 1:
        return tr("меньше минуты")
    if m < 60:
        return tr("%d мин") % m
    return tr("%d ч %d мин") % (m // 60, m % 60)


def fmt_time(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60)


class Bar(tk.Canvas):
    """Шкала «сколько поплавка видно» с отметкой порога подсечки."""

    def __init__(self, parent, width=300, height=26):
        super().__init__(parent, width=width, height=height, bg=C["panel2"], highlightthickness=0, bd=0)
        self.w, self.h = width, height
        self.set(None, 0.55)

    def set(self, frac, thr, flash=False):
        self.delete("all")
        top = 1.5  # шкала до 150 %
        if frac is not None:
            fill = max(0.0, min(frac, top)) / top * self.w
            color = C["muted"] if flash else (C["green"] if frac >= thr else C["orange"])
            self.create_rectangle(0, 0, fill, self.h, fill=color, width=0)
        tx = thr / top * self.w
        self.create_line(tx, 0, tx, self.h, fill=C["red"], width=2)
        x100 = 1 / top * self.w
        self.create_line(x100, 0, x100, self.h, fill=C["line"], width=1, dash=(2, 2))
        text = tr("ждём замер…") if frac is None else (tr("вспышка — пропускаю") if flash else "%d%%" % (100 * frac))
        self.create_text(6, self.h / 2, text=text, anchor="w", fill=C["text"], font=(FONT, 8, "bold"))


class Overlay(tk.Toplevel):
    """Маленькое окошко поверх игры: что происходит и сколько поймано."""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", max(0.3, min(1.0, int(app.cfg.get("overlay_alpha", 90)) / 100.0)))
        k = {"small": 0.85, "large": 1.25}.get(app.cfg.get("overlay_font"), 1.0)
        big, mid, small = round(11 * k), round(9 * k), round(8 * k)
        self.configure(bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
        top = tk.Frame(self, bg=C["panel"])
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.dot = tk.Canvas(top, width=12, height=12, bg=C["panel"], highlightthickness=0)
        self.dot.pack(side="left")
        self.title = tk.Label(top, text=tr("Готов"), bg=C["panel"], fg=C["text"], font=(FONT, big, "bold"))
        self.title.pack(side="left", padx=6)
        self.count = tk.Label(top, text=tr("Подсечек: 0"), bg=C["panel"], fg=C["text"], font=(FONT, big, "bold"))
        self.count.pack(side="right")
        self.hint = tk.Label(self, text="", bg=C["panel"], fg=C["muted"], font=(FONT, mid),
                             wraplength=round(250 * k), justify="left", anchor="w")
        self.hint.pack(fill="x", padx=10)
        self.bar = Bar(self, width=round(250 * k), height=10)
        self.bar.pack(padx=10, pady=(4, 8))
        # режим работы: что ловим, зелья, что отслеживается, когда остановиться
        self.mode = tk.Label(self, text="", bg=C["panel"], fg=C["muted"], font=(FONT, small),
                             wraplength=round(250 * k), justify="left", anchor="w")
        for w in (self, top, self.title, self.hint, self.count, self.dot, self.mode):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag)
            w.bind("<ButtonRelease-1>", self.drag_end)
        self.update_idletasks()
        pos = app.cfg.get("overlay_pos")
        if not pos or not on_screen(pos[0] + 20, pos[1] + 10):
            pos = (20, self.winfo_screenheight() - 170)
        self.geometry("+%d+%d" % tuple(pos))
        if app.selftest:
            self.after(1, lambda: ghost(self))
        self.after(50, self.no_activate)

    def no_activate(self):
        # окошко не забирает фокус у игры, даже если по нему кликнуть
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)
        except Exception:
            pass

    def drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def drag(self, e):
        self.geometry("+%d+%d" % (e.x_root - self._dx, e.y_root - self._dy))

    def drag_end(self, e):
        self.app.cfg["overlay_pos"] = [self.winfo_x(), self.winfo_y()]
        save_cfg(self.app.cfg)

    def set_mode(self, lines):
        if lines:
            self.mode.config(text="\n".join(lines))
            self.mode.pack(fill="x", padx=10, pady=(0, 8))
        else:
            self.mode.pack_forget()

    def set_state(self, state, title, hint):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 11, 11, fill=STATE_COLOR.get(state, C["muted"]), width=0)
        self.title.config(text=title)
        self.hint.config(text=hint)


class App:
    def __init__(self, selftest=None, lang=None):
        self.first_run = not os.path.exists(CFG_PATH)      # на этом компьютере ещё не запускали
        self.cfg = load_cfg()
        self.selftest = selftest
        if selftest:
            global SELFTEST
            SELFTEST = True
            # снимки для README: показательные настройки, а не настройки игрока
            self.cfg = dict(DEFAULTS, sonar_filter=True, quest_fish=2479, buffs_on=True, buff_fishing=True,
                            buff_crate=True, buff_sonar=True, stop_after_min=120)
        if lang:
            self.cfg["lang"] = lang
        self.apply_engine_cfg()
        self.q = queue.Queue()
        self.live = None
        self.stats = {"hooks": 0, "casts": 0, "fails": 0, "started": None}
        self.state = "idle"
        self.countdown = 0
        self.log_lines = []               # (время, текст, тип) — чтобы пересоздать журнал при смене языка
        self.gear = {"rod_slot": None, "manual": False, "bobber": None}
        self.bait = None                  # сколько цифр наживки видно на удочке
        self.bait_count = None            # само число наживки (если прочиталось)
        import history
        self.history = history.History(None if selftest else os.path.join(CFG_DIR, "catch_history.json"))
        self.report_period = "session"    # за какой период показывать отчёт об улове
        self.catch_info = None            # последнее, что прочитал сонар
        self.last_caught = None           # название последнего подобранного улова
        self.absent = []                  # каких нужных зелий нет в хотбаре
        self.tray = None                  # значок в трее
        self.update_url = None
        self.update_info = None           # (версия, страница, установщик) — если вышла новая версия
        self.calib = {"ratio": af.SINK_RATIO, "casts": 0, "auto": af.AUTO_CALIB}
        self.fisher = None

        prev_fg = ctypes.windll.user32.GetForegroundWindow()
        self.root = tk.Tk()
        if selftest:
            self.root.attributes("-alpha", 0.0)   # самопроверка невидима — см. ghost()
        self.root.title("%s %s" % (APP, VERSION))
        self.root.configure(bg=C["bg"])
        self.root.resizable(True, True)
        self.icon = tk.PhotoImage(data=base64.b64encode(png_bytes(icon_rgba(64))))
        self.root.iconphoto(True, self.icon)
        self.style()
        self.build()
        self.root.after(10, self.dark_titlebar)
        self.place_window()
        if selftest:
            self.root.after(1, lambda: (ghost(self.root), ctypes.windll.user32.SetForegroundWindow(prev_fg)))

        self.fisher = af.Fisher(debug=self.cfg["debug"], record=self.cfg["record"],
                                events=lambda k, d: self.q.put((k, d)), toggle_key=self.cfg["hotkey"],
                                reset_key=self.cfg["reset_key"],
                                points_path=None if selftest else os.path.join(CFG_DIR, "points.npz"))
        self.fisher.set_scale(self.cfg["scale"])
        self.overlay = None
        self.toggle_overlay()
        self.root.after(3000, self.check_updates)
        if selftest:
            # самопроверка не слушает клавиши и мышь (HOME в игре не должен запускать её рыбалку)
            self.fisher.state("idle", tr("Готов"), self.fisher.idle_hint())
        else:
            self.start_log_file()
            self.fisher.start()
            self.start_tray()
            if self.first_run and not self.cfg["wizard_done"]:
                self.root.after(800, self.show_wizard)
        self.root.bind("<F1>", lambda e: self.show_wizard())

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self.pump)
        self.root.after(1000, self.tick)
        if selftest:
            self.root.after(900, lambda: self.snapshot(selftest.replace(".png", "_start.png"),
                                                        close=False, overlay=False))
            self.root.after(1200, self.demo)
            self.root.after(2600, lambda: self.snapshot(selftest, close=False))
            self.root.after(2800, lambda: self.nb.select(1))
            self.root.after(3200, lambda: self.snapshot(selftest.replace(".png", "_settings.png"),
                                                        close=False, overlay=False))
            self.root.after(3400, lambda: self.nb.select(2))
            self.root.after(3800, lambda: self.snapshot(selftest.replace(".png", "_auto.png"),
                                                        close=False, overlay=False))
            self.root.after(4000, lambda: self.nb.select(3))
            self.root.after(4400, lambda: self.snapshot(selftest.replace(".png", "_away.png"),
                                                        close=False, overlay=False))
            self.root.after(4600, lambda: self.nb.select(4))
            self.root.after(5000, lambda: self.snapshot(selftest.replace(".png", "_catch.png"), overlay=False))

    def place_window(self):
        """Открыть окно там, где его оставили, но не за краем экрана."""
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        pos = self.cfg.get("win_pos")
        # оставили на мониторе, которого сейчас нет (отключили), — открываем на основном
        if not pos or not on_screen(pos[0] + 40, pos[1] + 10):
            pos = ((sw - w) // 2, max(0, (sh - h) // 3))
        self.root.geometry("+%d+%d" % (int(pos[0]), int(pos[1])))

    def dark_titlebar(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
            if not self.selftest:   # самопроверка не должна забирать фокус у игры
                self.root.withdraw()
                self.root.deiconify()   # чтобы Windows перерисовал заголовок
        except Exception:
            pass

    # ---------- настройки движка ----------
    def apply_engine_cfg(self):
        i18n.set_lang(self.cfg["lang"])
        af.AUTO_CALIB = bool(self.cfg["auto_calib"])
        af.AUTO_RECOVER = bool(self.cfg["auto_recover"])
        af.AUTO_RESUME = bool(self.cfg["auto_resume"])
        af.AUTO_ROD = bool(self.cfg["auto_rod"])
        slot = str(self.cfg["rod_slot"])
        af.ROD_SLOT = (int(slot) - 1) % 10 if slot.isdigit() else None
        af.AUTO_MARK = bool(self.cfg["auto_mark"])
        af.BUFFS_ON = bool(self.cfg["buffs_on"])
        af.BUFF_WANT = {n: bool(self.cfg["buff_" + n]) for n in ("fishing", "crate", "sonar", "calm")}
        af.HEALTH_GUARD = bool(self.cfg["health_guard"])
        af.BAIT_WATCH = bool(self.cfg["bait_watch"])
        af.STOP_AFTER_MIN = int(self.cfg["stop_after_min"])
        af.STOP_AFTER_HOOKS = int(self.cfg["stop_after_hooks"])
        af.SHUTDOWN_AFTER = bool(self.cfg["shutdown_after"])
        af.INV_FULL_STOP = bool(self.cfg["inv_full_stop"])
        af.SONAR_FILTER = bool(self.cfg["sonar_filter"])
        af.CATCH_BIOME = self.cfg["catch_biome"]
        af.CATCH_WANT = {k: set(v) for k, v in (self.cfg["catch_want"] or {}).items()}
        af.QUEST_FISH = self.cfg.get("quest_fish")
        af.BUFF_KEY = self.cfg["buff_key"]
        af.BUFF_METHOD = self.cfg["buff_method"]
        af.POTION_REMIND = bool(self.cfg["potion_remind"])
        af.EVENTS_STOP = bool(self.cfg["events_stop"])
        af.DEATH_STOP = bool(self.cfg["death_stop"])
        self.refresh_mode()
        af.SINK_RATIO = float(self.cfg["sink_ratio"])
        af.MAX_WAIT = float(self.cfg["max_wait"])
        af.SOUND = bool(self.cfg["sound"])

    # ---------- оформление ----------
    def style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=C["bg"], foreground=C["text"], font=(FONT, 9),
                    fieldbackground=C["panel2"], bordercolor=C["line"], lightcolor=C["line"],
                    darkcolor=C["line"], troughcolor=C["panel2"], focuscolor=C["blue"])
        s.configure("TFrame", background=C["bg"])
        s.configure("Card.TFrame", background=C["panel"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])
        s.configure("Card.TLabel", background=C["panel"])
        s.configure("Muted.TLabel", background=C["panel"], foreground=C["muted"], font=(FONT, 8))
        s.configure("Big.TLabel", background=C["panel"], font=(FONT, 14, "bold"))
        s.configure("TNotebook", background=C["bg"], borderwidth=0, bordercolor=C["line"],
                    lightcolor=C["bg"], darkcolor=C["bg"], tabmargins=(0, 0, 0, 0))
        s.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], padding=(10, 3),
                    font=(FONT, 9, "bold"), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", C["panel2"]), ("active", C["panel2"])],
              foreground=[("selected", C["text"])], lightcolor=[("selected", C["panel2"])],
              bordercolor=[("selected", C["line"])])
        s.configure("TButton", background=C["panel2"], foreground=C["text"], padding=(7, 3),
                    borderwidth=0, font=(FONT, 9, "bold"))
        s.map("TButton", background=[("active", C["line"]), ("disabled", C["panel"])],
              foreground=[("disabled", C["muted"])])
        s.configure("Accent.TButton", background=C["green"], foreground="#0d1a13")
        s.map("Accent.TButton", background=[("active", "#35b87d"), ("disabled", C["panel"])])
        s.configure("Donate.TButton", background=C["orange"], foreground="#1f1305", font=(FONT, 9, "bold"))
        s.map("Donate.TButton", background=[("active", "#ffb468")])
        s.configure("TCheckbutton", background=C["panel"], foreground=C["text"], padding=1)
        s.map("TCheckbutton", background=[("active", C["panel"])],
              indicatorcolor=[("selected", C["green"]), ("!selected", C["panel2"])])
        s.configure("TCombobox", arrowcolor=C["text"], foreground=C["text"], padding=2)
        s.map("TCombobox", fieldbackground=[("readonly", C["panel2"])], foreground=[("readonly", C["text"])])
        s.configure("Horizontal.TScale", background=C["panel"], troughcolor=C["panel2"])
        s.configure("TSpinbox", arrowcolor=C["text"], foreground=C["text"], padding=2)
        self.root.option_add("*TCombobox*Listbox.background", C["panel2"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["blue"])

    def card(self, parent, **pack):
        f = ttk.Frame(parent, style="Card.TFrame", padding=8)
        f.pack(**pack)
        return f

    def build(self):
        r = self.root
        # --- шапка: что происходит и что делать
        head = tk.Frame(r, bg=C["panel"])
        head.pack(fill="x")
        inner = tk.Frame(head, bg=C["panel"])
        inner.pack(fill="x", padx=10, pady=6)
        self.dot = tk.Canvas(inner, width=18, height=18, bg=C["panel"], highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        import donate
        if donate.LINKS:                          # поддержать автора — на виду, на любой вкладке
            ttk.Button(inner, text=tr("☕ Поддержать автора"), style="Donate.TButton",
                       command=self.show_donate).pack(side="right", padx=(8, 0))
        col = tk.Frame(inner, bg=C["panel"])
        col.pack(side="left", fill="x", expand=True)
        self.state_lbl = tk.Label(col, text=tr("Готов"), bg=C["panel"], fg=C["text"], font=(FONT, 12, "bold"),
                                  anchor="w")
        self.state_lbl.pack(fill="x")
        self.hint_lbl = tk.Label(col, text="", bg=C["panel"], fg=C["muted"], font=(FONT, 9), anchor="w",
                                 justify="left", wraplength=390)
        self.hint_lbl.pack(fill="x")

        nb = self.nb = ttk.Notebook(r)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        main = ttk.Frame(nb, padding=(0, 6, 0, 0))
        sett = ttk.Frame(nb, padding=(0, 6, 0, 0))
        auto = ttk.Frame(nb, padding=(0, 6, 0, 0))
        nb.add(main, text=tr(" Рыбалка "))
        nb.add(sett, text=tr(" Настройки "))
        nb.add(auto, text=tr(" Автоматика "))
        away = ttk.Frame(nb, padding=(0, 6, 0, 0))
        nb.add(away, text=tr(" Без присмотра "))
        catch = ttk.Frame(nb, padding=(0, 6, 0, 0))
        nb.add(catch, text=tr(" Улов "))
        self.build_main(main)
        self.build_settings(sett)
        self.build_auto(auto)
        self.build_away(away)
        self.build_catch(catch)

    def build_main(self, p):
        top = ttk.Frame(p)
        top.pack(fill="x")
        # поплавок: живая картинка и запомненный шаблон
        pv = self.card(top, side="left", fill="y")
        # пустая картинка нужного размера: без картинки Tk мерил бы width/height в символах
        self.blank = tk.PhotoImage(width=76, height=116)
        self.preview = tk.Label(pv, bg=C["panel2"], image=self.blank, bd=0)
        self.preview.pack()
        self.tmpl_lbl = tk.Label(pv, bg=C["panel"], fg=C["muted"], font=(FONT, 7), text=tr("поплавок\nне отмечен"),
                                 compound="left", justify="left")
        self.tmpl_lbl.pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(top)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        st = self.card(right, fill="x")
        grid = ttk.Frame(st, style="Card.TFrame")
        grid.pack(fill="x")
        self.stat_lbls = {}
        for i, (key, name) in enumerate((("hooks", tr("подсечек")), ("casts", tr("забросов")),
                                         ("rate", tr("в час")), ("time", tr("в работе")))):
            cell = ttk.Frame(grid, style="Card.TFrame")
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 22))
            lbl = ttk.Label(cell, text="0", style="Big.TLabel")
            lbl.pack(side="left")
            ttk.Label(cell, text=name, style="Muted.TLabel").pack(side="left", padx=(4, 0), pady=(5, 0))
            self.stat_lbls[key] = lbl
        self.fails_lbl = ttk.Label(st, text="", style="Muted.TLabel")
        self.fails_lbl.pack(anchor="w")
        self.buff_lbl = ttk.Label(st, text="", style="Muted.TLabel")
        self.buff_lbl.pack(anchor="w")
        self.show_buffs(None)
        self.gear_lbl = ttk.Label(st, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.show_gear({"rod_slot": None, "manual": False, "bobber": None})

        vis = self.card(right, fill="x", pady=(6, 0))
        ttk.Label(vis, text=tr("Видно поплавка над водой (красная черта — порог)"),
                  style="Muted.TLabel").pack(anchor="w")
        self.bar = Bar(vis, width=250, height=18)
        self.bar.pack(anchor="w", pady=(3, 2))
        self.wait_lbl = ttk.Label(vis, text=" ", style="Muted.TLabel")
        self.wait_lbl.pack(anchor="w")

        btns = ttk.Frame(p)
        btns.pack(fill="x", pady=(6, 0))
        self.start_btn = ttk.Button(btns, text=tr("▶ Старт (5 с)"), style="Accent.TButton", command=self.start_countdown)
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(btns, text=tr("⏸ Пауза"), command=self.pause)
        self.pause_btn.pack(side="left", padx=6)
        ttk.Button(btns, text=tr("↺ Новые точки"), command=self.new_points).pack(side="left")
        # что-то пошло не так — сохранить всё для разбора одним архивом
        ttk.Button(btns, text=tr("⚑ Что-то не так"), command=self.report_mistake).pack(side="left", padx=6)
        ttk.Button(btns, text=tr("Папка"), command=self.open_data).pack(side="right")

        # журнал
        lg = self.card(p, fill="both", expand=True, pady=(6, 0))
        self.log_txt = tk.Text(lg, height=6, width=10, bg=C["panel2"], fg=C["text"], bd=0, highlightthickness=0,
                               font=("Consolas", 8), wrap="word", padx=6, pady=4)
        self.log_txt.pack(fill="both", expand=True)
        for tag, color in (("time", C["muted"]), ("good", C["green"]), ("bad", C["red"]),
                           ("ask", C["yellow"]), ("info", C["text"])):
            self.log_txt.tag_config(tag, foreground=color)
        self.log_txt.config(state="disabled")

    def build_settings(self, p):
        box = self.card(p, fill="both", expand=True)
        row = 0

        def label(text, sub=None):
            nonlocal row
            ttk.Label(box, text=text, style="Card.TLabel", font=(FONT, 9, "bold")).grid(
                row=row, column=0, sticky="w", pady=(4, 0))
            if sub:
                ttk.Label(box, text=sub, style="Muted.TLabel", wraplength=250, justify="left").grid(
                    row=row + 1, column=0, sticky="w")
            else:
                ttk.Frame(box, style="Card.TFrame", height=1).grid(row=row + 1, column=0)

        label(tr("Язык / Language"))
        self.lang_var = tk.StringVar(value=dict(LANGS)[self.cfg["lang"]])
        cb = ttk.Combobox(box, textvariable=self.lang_var, values=[n for k, n in LANGS],
                          state="readonly", width=12)
        cb.grid(row=row, column=1, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_lang())
        row += 2

        label(tr("Клавиша: старт, пауза, продолжить"))
        self.hotkey_var = tk.StringVar(value=self.cfg["hotkey"].upper())
        cb = ttk.Combobox(box, textvariable=self.hotkey_var, values=[h.upper() for h in HOTKEYS],
                          state="readonly", width=10)
        cb.grid(row=row, column=1, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_hotkey())
        row += 2

        label(tr("Клавиша: выбрать новые точки"))
        self.reset_var = tk.StringVar(value=self.cfg["reset_key"].upper())
        cb = ttk.Combobox(box, textvariable=self.reset_var, values=[h.upper() for h in HOTKEYS],
                          state="readonly", width=10)
        cb.grid(row=row, column=1, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_hotkey())
        row += 2

        label(tr("Масштаб (Zoom) — как в игре"))
        self.zoom_var = tk.StringVar(value="%d%%" % round(100 * self.cfg["scale"]))
        cb = ttk.Combobox(box, textvariable=self.zoom_var, values=ZOOMS, state="readonly", width=10)
        cb.grid(row=row, column=1, rowspan=2, sticky="e")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_zoom())
        row += 2

        label(tr("Чувствительность"), tr("Подсекать, когда видно меньше этой доли поплавка. "
                                 "Выше — раньше, но чаще зря"))
        sens = ttk.Frame(box, style="Card.TFrame")
        sens.grid(row=row, column=1, rowspan=2, sticky="e")
        self.sens_var = tk.DoubleVar(value=round(100 * self.cfg["sink_ratio"]))
        self.sens_lbl = ttk.Label(sens, text="", style="Card.TLabel", width=4)
        ttk.Scale(sens, from_=30, to=80, variable=self.sens_var, length=90,
                  command=lambda v: self.set_sens()).pack(side="left")
        self.sens_lbl.pack(side="left", padx=(4, 0))
        self.set_sens(save=False)
        row += 2

        self.auto_var = tk.BooleanVar(value=bool(self.cfg["auto_calib"]))
        ttk.Checkbutton(box, text=tr("Автокалибровка: порог подбирается сам по вашей воде и погоде"),
                        variable=self.auto_var, command=self.set_auto).grid(row=row, column=0, columnspan=2,
                                                                             sticky="w", pady=(2, 0))
        row += 1
        self.calib_lbl = ttk.Label(box, text="", style="Muted.TLabel")
        self.calib_lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=(22, 0))
        row += 1
        self.show_calib()

        label(tr("Ждать поклёвку, сек"), tr("Потом вытащить и забросить заново"))
        self.wait_var = tk.IntVar(value=int(self.cfg["max_wait"]))
        sp = ttk.Spinbox(box, from_=10, to=180, increment=5, textvariable=self.wait_var, width=8,
                         command=self.set_wait)
        sp.grid(row=row, column=1, rowspan=2, sticky="e")
        sp.bind("<FocusOut>", lambda e: self.set_wait())
        row += 2

        ttk.Separator(box).grid(row=row, column=0, columnspan=2, sticky="ew", pady=6)
        row += 1
        self.checks = {}
        for key, text in (("overlay", tr("Окошко поверх игры (перетаскивается мышью)")),
                          ("toasts", tr("Уведомления Windows: пауза, нет наживки, ошибки")),
                          ("toast_hooks", tr("Уведомление о каждой подсечке")),
                          ("sound", tr("Звуки: старт, отметка, пауза")),
                          ("hook_sound", tr("Звук при подсечке")),
                          ("debug", tr("Сохранять отладочные картинки (папка data\\debug)")),
                          ("record", tr("Режим записи: подсекаю я сам")),
                          ("update_check", tr("Раз в сутки проверять, не вышла ли новая версия (GitHub)"))):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(box, text=text, variable=var, command=lambda k=key: self.set_check(k)).grid(
                row=row, column=0, columnspan=2, sticky="w")
            self.checks[key] = var
            row += 1
            if key == "overlay":
                row = self.build_overlay_opts(box, row)
        bf = ttk.Frame(box, style="Card.TFrame")
        bf.grid(row=row, column=0, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(bf, text=tr("Проверить уведомление"), command=lambda: toast(
            APP, tr("Так выглядят уведомления программы"))).pack(side="left")
        # всё, что нужно для рыбалки, — одной проверкой, с подсказками, что исправить
        ttk.Button(bf, text=tr("Диагностика"), command=self.run_diagnostics).pack(side="left", padx=(6, 0))
        # всё для разбора проблемы — одним архивом: журнал, настройки, отладочные картинки
        ttk.Button(bf, text=tr("Собрать отчёт"), command=self.make_report).pack(side="right")
        self.update_btn = ttk.Button(bf, text=tr("Обновления"), command=self.on_update_btn)
        self.update_btn.pack(side="right", padx=(0, 6))
        self.show_update_btn()
        row += 1
        box.columnconfigure(0, weight=1)

    def build_auto(self, p):
        box = self.card(p, fill="both", expand=True)

        def check(key, text, cmd=None, pad=0):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(box, text=text, variable=var,
                            command=lambda: (self.set_auto_opt(key, var.get()), cmd and cmd())).pack(
                anchor="w", padx=(pad, 0))
            return var

        ttk.Label(box, text=tr("Удочка и поплавок"), style="Card.TLabel",
                  font=(FONT, 9, "bold")).pack(anchor="w")
        check("auto_rod", tr("Сам брать удочку в руки (если выбран другой слот хотбара)"))
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", padx=(22, 0))
        ttk.Label(row, text=tr("Слот удочки"), style="Card.TLabel").pack(side="left")
        slots = [tr("Авто (запомню)")] + [str(i) for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 0)]
        self.rodslot_var = tk.StringVar(value=slots[0] if self.cfg["rod_slot"] == "auto" else str(self.cfg["rod_slot"]))
        cb = ttk.Combobox(row, textvariable=self.rodslot_var, values=slots, state="readonly", width=19)
        cb.pack(side="left", padx=(8, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_auto_opt(
            "rod_slot", "auto" if self.rodslot_var.get() == slots[0] else self.rodslot_var.get()))
        # снимок хотбара — для настройки распознавания удочек; подпись появляется только после нажатия
        ttk.Button(row, text=tr("Снимок хотбара"), command=self.snap_hotbar).pack(side="right")
        self.hb_row = row
        self.hb_lbl = ttk.Label(box, text="", style="Muted.TLabel", wraplength=390, justify="left")
        check("auto_mark", tr("Сам находить поплавок после первого заброса (по картинкам с Terraria Wiki)"))
        ttk.Separator(box).pack(fill="x", pady=8)

        ttk.Label(box, text=tr("Если что-то пошло не так"), style="Card.TLabel",
                  font=(FONT, 9, "bold")).pack(anchor="w")
        check("auto_recover", tr("Не сдаваться: после сбоев пробовать снова каждые 2 с, без остановки"))
        check("auto_resume", tr("Сам продолжать, когда я вернусь в игру из другого окна"))
        ttk.Separator(box).pack(fill="x", pady=8)

        ttk.Label(box, text=tr("Зелья"), style="Card.TLabel", font=(FONT, 9, "bold")).pack(anchor="w")
        check("buffs_on", tr("Следить за баффами и пить зелья, когда бафф закончился"))
        grid = ttk.Frame(box, style="Card.TFrame")
        grid.pack(fill="x", padx=(22, 0))
        for i, (key, text) in enumerate((("buff_fishing", tr("Рыбалка")), ("buff_crate", tr("Ящики")),
                                         ("buff_sonar", tr("Сонар")), ("buff_calm", tr("Спокойствие")))):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(grid, text=text, variable=var,
                            command=lambda k=key, v=var: self.set_auto_opt(k, v.get())).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 30))
        check("potion_remind", tr("Напоминать, если нужного зелья нет в хотбаре (не чаще раза в 10 мин)"))
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=tr("Пить"), style="Card.TLabel").pack(side="left")
        methods = [("hotbar", tr("из хотбара")), ("quick", tr("быстрым баффом"))]
        self.method_var = tk.StringVar(value=dict(methods).get(self.cfg["buff_method"], methods[0][1]))
        cb = ttk.Combobox(row, textvariable=self.method_var, values=[t for _, t in methods],
                          state="readonly", width=16)
        cb.pack(side="left", padx=(8, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: (
            self.set_auto_opt("buff_method", {t: k for k, t in methods}[self.method_var.get()]),
            self.method_hint.config(text=self.method_text())))
        self.buffkey_var = tk.StringVar(value=self.cfg["buff_key"].upper())
        kb = ttk.Combobox(row, textvariable=self.buffkey_var, values=[k.upper() for k in BUFF_KEYS],
                          state="readonly", width=5)
        kb.pack(side="right")
        kb.bind("<<ComboboxSelected>>", lambda e: self.set_auto_opt("buff_key", self.buffkey_var.get().lower()))
        ttk.Label(row, text=tr("клавиша быстрого баффа"), style="Muted.TLabel").pack(side="right", padx=(0, 6))
        self.method_hint = ttk.Label(box, text=self.method_text(), style="Muted.TLabel", wraplength=390,
                                     justify="left")
        self.method_hint.pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text=tr("Проверить баффы сейчас"), command=self.test_buffs).pack(side="left")
        self.buff_test_lbl = ttk.Label(box, text=tr("Игра должна быть видна на экране (окно программы не должно её закрывать)."),
                                       style="Muted.TLabel", wraplength=390, justify="left")
        self.buff_test_lbl.pack(anchor="w", pady=(4, 0))

    def method_text(self):
        if self.cfg["buff_method"] == "hotbar":
            return tr("Из хотбара: программа находит нужное зелье в хотбаре, берёт его цифрой слота, пьёт "
                      "и снова берёт удочку. Положите зелья в хотбар.")
        return tr("Быстрый бафф выпивает все зелья-баффы из инвентаря, чьих баффов сейчас нет. "
                  "Держите в инвентаре только нужные зелья.")

    def build_catch(self, p):
        """Вкладка «Улов»: что ловить в каждом биоме (по надписи зелья сонара)."""
        box = self.card(p, fill="both", expand=True)
        try:
            import catches
            self.catch_data = catches.Catches(os.path.join(af.ASSET_DIR, "fishing", "catches.json"))
            if af.GAME_NAMES:
                import gamenames
                self.catch_data.use_game_names(gamenames.load())      # названия как в игре
        except Exception:
            self.catch_data = None
            ttk.Label(box, text=tr("Нет данных об улове."), style="Card.TLabel").pack(anchor="w")
            return
        c, ru = self.catch_data, i18n.LANG == "ru"
        var = tk.BooleanVar(value=bool(self.cfg["sonar_filter"]))
        top = ttk.Frame(box, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Checkbutton(top, text=tr("Выбирать улов по зелью сонара"), variable=var,
                        command=lambda: self.set_auto_opt("sonar_filter", var.get())).pack(side="left")
        ttk.Button(top, text=tr("Отчёт об улове"), command=self.show_catch_report).pack(side="right")
        ttk.Label(box, text=tr("Зелье сонара пишет над поплавком, что клюнуло. Программа читает надпись и "
                               "подсекает только отмеченное, остальное пропускает. Не прочитала — подсекает."),
                  style="Muted.TLabel", wraplength=390, justify="left").pack(anchor="w", padx=(22, 0))

        def row(text):
            r = ttk.Frame(box, style="Card.TFrame")
            r.pack(fill="x", pady=(6, 0))
            ttk.Label(r, text=text, style="Card.TLabel", width=15).pack(side="left")
            return r
        # задание рыбака: поймали нужную рыбу — пауза и уведомление
        quest = [(None, tr("(нет задания)"))] + sorted({it["id"]: (it["id"], it["ru"] if ru else it["en"])
                                              for g in c.groups for it in g["items"] if it.get("quest")}.values(),
                                             key=lambda x: x[1])
        self.quest_var = tk.StringVar(value=dict(quest).get(self.cfg.get("quest_fish"), quest[0][1]))
        qb = ttk.Combobox(row(tr("Задание рыбака")), textvariable=self.quest_var, values=[t for _, t in quest],
                          state="readonly", width=30)
        qb.pack(side="left")
        qb.bind("<<ComboboxSelected>>", lambda e: self.set_auto_opt(
            "quest_fish", {t: k for k, t in quest}[self.quest_var.get()]))
        biomes = [("auto", tr("Авто (по улову)"))] + [(g["key"], g["ru"] if ru else g["en"])
                                                                 for g in c.biomes()]
        self.biome_var = tk.StringVar(value=dict(biomes).get(self.cfg["catch_biome"], biomes[0][1]))
        cb = ttk.Combobox(row(tr("Где рыбачу")), textvariable=self.biome_var, values=[t for _, t in biomes],
                          state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_auto_opt(
            "catch_biome", {t: k for k, t in biomes}[self.biome_var.get()]))

        groups = [(g["key"], g["ru"] if ru else g["en"]) for g in c.groups]
        r = row(tr("Список"))
        self.group_var = tk.StringVar(value=groups[0][1])
        gb = ttk.Combobox(r, textvariable=self.group_var, values=[t for _, t in groups], state="readonly", width=22)
        gb.pack(side="left")
        ttk.Button(r, text=tr("Ничего"), command=lambda: self.set_group_all(False)).pack(side="right")
        ttk.Button(r, text=tr("Всё"), command=lambda: self.set_group_all(True)).pack(side="right", padx=(0, 4))

        # список предметов выбранной группы: две колонки, с прокруткой
        wrap = ttk.Frame(box, style="Card.TFrame")
        wrap.pack(fill="both", expand=True, pady=(6, 0))
        canvas = tk.Canvas(wrap, bg=C["panel"], highlightthickness=0, height=200)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        self.catch_list = ttk.Frame(canvas, style="Card.TFrame")
        self.catch_list.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.catch_list, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
                        if str(e.widget).startswith(str(canvas)) else None)
        self.catch_canvas = canvas
        self.group_keys = {t: k for k, t in groups}
        gb.bind("<<ComboboxSelected>>", lambda e: self.show_group())
        self.show_group()

    # ---------- отчёт об улове ----------
    def catch_totals(self, period="session"):
        """Улов за период: за эту сессию — из движка, за день / неделю / всё время — из истории."""
        if period == "session":
            f = self.fisher
            return {"hooks": f.hooks, "unknown": f.caught_unknown, "skipped": f.skipped,
                    "items": dict(f.caught), "days": 0,
                    "hours": (time.time() - f.started) / 3600.0 if f.started else 0.0}
        return self.history.totals(period)

    def catch_rows(self, period="session"):
        """[(название, сколько, где ловится)] пойманного (по надписям о подборе), по убыванию."""
        c, ru = self.catch_data, i18n.LANG == "ru"
        rows = []
        for item_id, n in sorted(self.catch_totals(period)["items"].items(), key=lambda kv: -kv[1]):
            it = c.items.get(item_id, {"ru": str(item_id), "en": str(item_id)})
            where = ", ".join((c.group[k]["ru"] if ru else c.group[k]["en"]) for k in c.where.get(item_id, []))
            rows.append((it["ru"] if ru else it["en"], n, where))
        return rows

    def catch_summary(self, period="session"):
        t = self.catch_totals(period)
        text = tr("Подсечек: %d · узнано: %d · не узнано: %d · пропущено сонаром: %d") % (
            t["hooks"], sum(t["items"].values()), t["unknown"], t["skipped"])
        if t.get("hours", 0) > 0.01:
            text += tr(" · в час: %.0f") % (t["hooks"] / t["hours"])
        if period != "session":
            text += tr(" · дней с рыбалкой: %d") % t["days"]
        return text

    def show_catch_report(self):
        win = tk.Toplevel(self.root)
        win.title(tr("Отчёт об улове"))
        win.configure(bg=C["bg"])
        win.transient(self.root)
        frame = tk.Frame(win, bg=C["panel"], padx=10, pady=10)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        top = tk.Frame(frame, bg=C["panel"])
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text=tr("За"), style="Card.TLabel").pack(side="left")
        periods = [("session", tr("эту рыбалку")), ("today", tr("сегодня")), ("week", tr("7 дней")),
                   ("all", tr("всё время"))]
        period_var = tk.StringVar(value=dict(periods)[self.report_period])
        pcb = ttk.Combobox(top, textvariable=period_var, values=[t for _, t in periods], state="readonly", width=14)
        pcb.pack(side="left", padx=(6, 0))
        cols = (tr("Улов"), tr("Сколько"), tr("Где ловится"))
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (180, 70, 220)):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w" if c != cols[1] else "center")
        tree.pack(fill="both", expand=True)
        summary = ttk.Label(frame, style="Muted.TLabel", wraplength=470, justify="left")
        summary.pack(anchor="w", pady=(8, 0))
        charts = tk.Canvas(frame, width=470, height=150, bg=C["panel"], highlightthickness=0)
        charts.pack(fill="x", pady=(8, 0))
        bar = tk.Frame(win, bg=C["bg"])
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text=tr("Закрыть"), command=win.destroy).pack(side="right")
        ttk.Button(bar, text=tr("Сохранить CSV"), command=self.save_catch_csv).pack(side="right", padx=(0, 6))
        import donate
        if donate.LINKS:
            ttk.Button(bar, text=tr("☕ Поддержать автора"), style="Donate.TButton",
                       command=self.show_donate).pack(side="left")

        def refresh():
            if not win.winfo_exists():
                return
            tree.delete(*tree.get_children())
            rows = self.catch_rows(self.report_period)
            for row in rows:
                tree.insert("", "end", values=row)
            if not rows:
                tree.insert("", "end", values=(tr("пока ничего не узнано"), "", ""))
            summary.config(text=self.catch_summary(self.report_period) + "\n" + self.catch_highlights(
                self.report_period) + "\n" + tr("Улов узнаётся по надписи о подборе над персонажем после каждой подсечки."))
            self.draw_charts(charts, self.report_period)
            win.after(2000, refresh)

        def set_period(_e=None):
            self.report_period = {t: k for k, t in periods}[period_var.get()]
        pcb.bind("<<ComboboxSelected>>", set_period)
        refresh()
        self.catch_win = win

    def catch_highlights(self, period):
        """Сколько ящиков и редкого, лучший биом — за период."""
        c, ru = self.catch_data, i18n.LANG == "ru"
        if c is None:
            return ""
        items = self.catch_totals(period)["items"]
        crates = sum(n for i, n in items.items() if "crates" in c.where.get(i, []))
        rare = sum(n for i, n in items.items() if "rare" in c.where.get(i, []))
        biomes = {}
        for i, n in items.items():
            homes = [k for k in c.where.get(i, []) if k not in ("crates", "rare", "junk")]
            for k in homes:
                biomes[k] = biomes.get(k, 0) + n / float(len(homes))
        text = tr("Ящиков: %d · редкого: %d") % (crates, rare)
        if biomes:
            best = max(biomes, key=biomes.get)
            g = c.group[best]
            text += tr(" · больше всего из биома: %s") % (g["ru"] if ru else g["en"])
        return text

    def draw_charts(self, cv, period):
        """Два столбчатых графика: улов по дням (14 дней) и по часам суток (за период)."""
        cv.delete("all")
        w, h = int(cv.winfo_width()) if cv.winfo_width() > 10 else 470, 150
        half = w // 2 - 8
        days = self.history.by_day(14)
        hours = self.history.by_hour("today" if period == "session" else period)

        def chart(x0, title, values, labels, every):
            cv.create_text(x0, 8, text=title, anchor="w", fill=C["muted"], font=(FONT, 8))
            top, bottom = 22, h - 16
            peak = max(values) or 1
            bw = half / float(len(values))
            for k, v in enumerate(values):
                bx = x0 + k * bw
                by = bottom - (bottom - top) * v / float(peak)
                cv.create_rectangle(bx + 1, by, bx + bw - 1, bottom, fill=C["green"] if v else C["line"], width=0)
                if k % every == 0:
                    cv.create_text(bx + bw / 2, h - 7, text=labels[k], fill=C["muted"], font=(FONT, 7))
            cv.create_text(x0 + half, 8, text=tr("макс. %d") % max(values), anchor="e", fill=C["muted"],
                           font=(FONT, 7))

        chart(0, tr("Улов по дням (14 дней)"), [n for _, n in days], [d.strftime("%d") for d, _ in days], 2)
        chart(w // 2 + 8, tr("По часам суток"), hours, [str(k) for k in range(24)], 3)

    def report_mistake(self):
        """«Что-то не так»: последние картинки, снимок игры, конец журнала — одним архивом в data."""
        lines = self.log_txt.get("1.0", "end").strip().split("\n")[-300:]
        extra = {"settings.json": json.dumps(self.cfg, ensure_ascii=False, indent=2),
                 "system.txt": self.system_info()}

        def work():
            import mss
            try:
                with (getattr(mss, "MSS", None) or mss.mss)() as sct:
                    path = self.fisher.save_mistake(sct, os.path.join(af.DATA_DIR, "reports"), lines, extra)
            except Exception as e:
                self.q.put(("log", {"text": tr("Не удалось сохранить: %r") % e, "kind": "bad"}))
                return
            self.q.put(("log", {"text": tr("Сохранил для разбора: %s — пришлите этот файл автору.") % path,
                                "kind": "good"}))
            try:
                subprocess.Popen(["explorer", "/select,", path])
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def run_diagnostics(self):
        """Диагностика через 3 с (чтобы переключиться в игру): результат — в окне и в data."""
        self.add_log(tr("Диагностика: переключитесь в игру — проверка через 3 с…"), "ask")

        def work():
            import mss
            import diagnose
            time.sleep(3)
            hwnd = af.find_terraria()
            active = bool(af.terraria_window())
            try:
                with (getattr(mss, "MSS", None) or mss.mss)() as sct:
                    results = diagnose.run(self.fisher, sct, hwnd, active)
            except Exception as e:
                results = [(diagnose.BAD, tr("Ошибка диагностики: %r") % e)]
            try:
                path = diagnose.save(results, af.DATA_DIR)
            except Exception:
                path = None
            self.q.put(("diagnostics", {"results": results, "path": path}))
        threading.Thread(target=work, daemon=True).start()

    def show_diagnostics(self, d):
        import diagnose
        results = d["results"]
        bad = sum(1 for s, _ in results if s != diagnose.OK)
        self.add_log(tr("Диагностика: всё в порядке.") if not bad else
                     tr("Диагностика: есть что исправить (%d).") % bad, "good" if not bad else "bad")
        win = tk.Toplevel(self.root)
        win.title(tr("Диагностика"))
        win.configure(bg=C["bg"])
        win.transient(self.root)
        frame = tk.Frame(win, bg=C["panel"], padx=14, pady=12)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        colors = {diagnose.OK: C["green"], diagnose.WARN: C["yellow"], diagnose.BAD: C["red"]}
        for state, text in results:
            row = tk.Frame(frame, bg=C["panel"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=diagnose.MARK[state], bg=C["panel"], fg=colors.get(state, C["text"]),
                     font=(FONT, 10, "bold"), width=2).pack(side="left", anchor="n")
            tk.Label(row, text=text, bg=C["panel"], fg=C["text"], font=(FONT, 9), wraplength=420,
                     justify="left", anchor="w").pack(side="left", fill="x")
        if d.get("path"):
            ttk.Label(frame, text=tr("Сохранено: %s") % d["path"], style="Muted.TLabel", wraplength=440,
                      justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Button(win, text=tr("Закрыть"), command=win.destroy).pack(anchor="e", padx=8, pady=(0, 8))

    def donate_nudge(self):
        """Круглое число пойманного за всё время (100, 500, 1000…) — одна строка в журнале и одно
        уведомление: можно поддержать автора. На каждое число — один раз."""
        import donate
        if not donate.LINKS or self.selftest:
            return
        t = self.history.totals("all")
        total = sum(t["items"].values()) + t["unknown"]
        done = int(self.cfg.get("donate_nudged") or 0)
        reached = [m for m in DONATE_NUDGES if done < m <= total]
        if not reached:
            return
        self.cfg["donate_nudged"] = reached[-1]
        save_cfg(self.cfg)
        text = tr("Программа поймала для вас уже %d рыб и предметов! Если она помогает — поддержите автора: "
                  "кнопка «☕ Поддержать автора» вверху.") % reached[-1]
        self.add_log(text, "good")
        if self.cfg["toasts"]:
            toast(APP, text)

    def show_donate(self):
        """Поддержать автора: короткое спасибо и кнопки страниц пожертвований (открываются в браузере)."""
        import donate
        win = tk.Toplevel(self.root)
        win.title(tr("Поддержать автора"))
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.resizable(False, False)
        frame = tk.Frame(win, bg=C["panel"], padx=16, pady=14)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Label(frame, text=tr("Спасибо, что пользуетесь Terraria AutoFish!"), style="Card.TLabel",
                  font=(FONT, 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=tr("Программа бесплатная. Если она вам помогла, можно оставить автору «на чай» — "
                                 "это добровольно и ни на что в программе не влияет."),
                  style="Muted.TLabel", wraplength=340, justify="left").pack(anchor="w", pady=(6, 10))
        for name, url, note, _lang in donate.ordered(i18n.LANG):
            ttk.Button(frame, text=tr(name), command=lambda u=url: webbrowser.open(u)).pack(fill="x", pady=(4, 0))
            ttk.Label(frame, text=tr(note), style="Muted.TLabel").pack(anchor="w")
        ttk.Button(win, text=tr("Закрыть"), command=win.destroy).pack(anchor="e", padx=8, pady=(0, 8))

    def open_data(self):
        """Папка data: журналы, отладочные картинки, снимки хотбара, отчёты."""
        os.makedirs(af.DATA_DIR, exist_ok=True)
        os.startfile(af.DATA_DIR)

    def save_catch_csv(self):
        import csv
        os.makedirs(af.DATA_DIR, exist_ok=True)
        path = os.path.join(af.DATA_DIR, time.strftime("catch_%Y%m%d_%H%M%S.csv"))
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow([tr("Улов"), tr("Сколько"), tr("Где ловится")])
                for row in self.catch_rows(self.report_period):
                    w.writerow(row)
                w.writerow([])
                w.writerow([self.catch_summary(self.report_period)])
        except Exception as e:
            self.add_log(tr("Не удалось сохранить отчёт об улове: %r") % e, "bad")
            return
        self.add_log(tr("Отчёт об улове сохранён: %s") % path, "good")
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

    def group_want(self, key):
        want = self.cfg.get("catch_want") or {}
        if key in want:
            return set(want[key])
        return {it["id"] for it in self.catch_data.group[key]["items"]}      # не настроено — ловим всё

    def show_group(self):
        for w in self.catch_list.winfo_children():
            w.destroy()
        key = self.group_keys[self.group_var.get()]
        want = self.group_want(key)
        ru = i18n.LANG == "ru"
        self.catch_vars = {}
        for n, it in enumerate(self.catch_data.group[key]["items"]):
            var = tk.BooleanVar(value=it["id"] in want)
            text = it["ru"] if ru else it["en"]
            if it.get("hardmode"):
                text += tr(" (хардмод)")
            ttk.Checkbutton(self.catch_list, text=text, variable=var,
                            command=lambda k=key: self.save_group(k)).grid(
                row=n // 2, column=n % 2, sticky="w", padx=(0, 10))
            self.catch_vars[it["id"]] = var
        self.catch_canvas.yview_moveto(0)

    def save_group(self, key):
        want = dict(self.cfg.get("catch_want") or {})
        want[key] = sorted(i for i, v in self.catch_vars.items() if v.get())
        self.set_auto_opt("catch_want", want)

    def set_group_all(self, on):
        for v in self.catch_vars.values():
            v.set(on)
        self.save_group(self.group_keys[self.group_var.get()])

    def build_away(self, p):
        """Вкладка «Без присмотра»: защита персонажа, когда закончить рыбалку."""
        box = self.card(p, fill="both", expand=True)

        def check(parent, key, text, **pack):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(parent, text=text, variable=var,
                            command=lambda: self.set_auto_opt(key, var.get())).pack(anchor="w", **pack)

        def head(text):
            ttk.Label(box, text=text, style="Card.TLabel", font=(FONT, 9, "bold")).pack(anchor="w")

        head(tr("Защита"))
        check(box, "health_guard", tr("Персонаж получает урон — вытащить поплавок и встать на паузу"))
        check(box, "bait_watch", tr("Наживка: мало — предупредить, кончилась — остановиться"))
        check(box, "inv_full_stop", tr("Улов перестал подбираться (инвентарь полон) — остановиться"))
        check(box, "events_stop", tr("События в чате (кровавая луна, вторжения, боссы) — переждать и продолжить"))
        check(box, "death_stop", tr("Персонаж погиб — остановить рыбалку совсем"))
        ttk.Separator(box).pack(fill="x", pady=6)

        head(tr("Когда закончить"))

        def spin(key, text, top):
            row = ttk.Frame(box, style="Card.TFrame")
            row.pack(fill="x", pady=(2, 0))
            ttk.Label(row, text=text, style="Card.TLabel").pack(side="left")
            var = tk.IntVar(value=int(self.cfg[key]))

            def save(*_):
                try:
                    v = max(0, min(top, int(var.get())))
                except (tk.TclError, ValueError):
                    v = 0
                var.set(v)
                self.set_auto_opt(key, v)
            sp = ttk.Spinbox(row, from_=0, to=top, increment=10 if top > 100 else 5, textvariable=var,
                             width=8, command=save)
            sp.pack(side="right")
            sp.bind("<FocusOut>", save)
            sp.bind("<Return>", save)
        spin("stop_after_min", tr("Остановиться через, мин (0 — нет)"), 1440)
        spin("stop_after_hooks", tr("…или после стольких подсечек (0 — нет)"), 100000)
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", pady=(2, 0))
        check(row, "shutdown_after", tr("Потом выключить компьютер (через 60 с)"), side="left")
        self.cancel_btn = ttk.Button(row, text=tr("Отменить выключение"), command=self.cancel_shutdown)
        self.cancel_btn.pack(side="right")
        self.cancel_btn.state(["disabled"])
    def cancel_shutdown(self):
        try:
            af.cancel_shutdown()
            self.add_log(tr("Выключение компьютера отменено."), "good")
        except Exception as e:
            self.add_log(tr("Не получилось отменить выключение: %r") % e, "bad")
        self.cancel_btn.state(["disabled"])

    def set_auto_opt(self, key, value):
        self.cfg[key] = value
        save_cfg(self.cfg)
        self.apply_engine_cfg()
        if key.startswith("buff"):
            self.fisher.last_buff_check = 0          # проверить при ближайшем забросе
            self.show_buffs(None)
        if key in ("auto_rod", "rod_slot"):
            self.fisher.rod_misses = 0
            self.fisher.gear_changed()

    def mode_lines(self):
        """Режим работы для окошка поверх игры: что ловим, где, зелья, что отслеживается, когда стоп."""
        c, ru = self.cfg, i18n.LANG == "ru"
        lines = []
        if c.get("record"):
            lines.append(tr("Режим записи: подсекаете вы, программа записывает"))
        data = getattr(self, "catch_data", None)

        def group(key):
            g = data.group.get(key) if data else None
            return (g["ru"] if ru else g["en"]) if g else key

        if c["sonar_filter"]:
            if c["catch_biome"] != "auto":
                where = group(c["catch_biome"])
            else:
                b = (self.catch_info or {}).get("biome")
                where = (group(b) + tr(" (авто)")) if b else tr("биом определяю")
            lines.append(tr("Улов: только отмеченное (сонар) · %s") % where)
        else:
            lines.append(tr("Улов: всё подряд"))
        quest = c.get("quest_fish")
        if quest is not None and data and quest in data.items:
            it = data.items[quest]
            lines.append(tr("Задание рыбака: %s") % (it["ru"] if ru else it["en"]))
        if c["buffs_on"]:
            names = {"fishing": tr("рыбалки"), "crate": tr("ящиков"), "sonar": tr("сонара"),
                     "calm": tr("спокойствия")}
            on = [names[n] for n in ("fishing", "crate", "sonar", "calm") if c["buff_" + n]]
            how = tr("из хотбара") if c["buff_method"] == "hotbar" else tr("быстрым баффом")
            lines.append(tr("Зелья: %s (%s)") % (", ".join(on) or tr("не выбраны"), how))
            if self.absent:
                lines.append(tr("  нет в хотбаре: %s") % ", ".join(names.get(n, n) for n in self.absent))
        watch = [t for k, t in (("health_guard", tr("урон")), ("bait_watch", tr("наживка")),
                                ("inv_full_stop", tr("полный инвентарь")),
                                ("events_stop", tr("события")), ("death_stop", tr("смерть"))) if c.get(k)]
        if watch:
            lines.append(tr("Слежу: %s") % ", ".join(watch))
        stop = []
        if int(c["stop_after_min"]):
            stop.append(tr("через %d мин") % int(c["stop_after_min"]))
        if int(c["stop_after_hooks"]):
            stop.append(tr("после %d подсечек") % int(c["stop_after_hooks"]))
        if stop:
            lines.append(tr("Стоп: %s") % tr(" или ").join(stop) + (tr(", потом выключу ПК") if c["shutdown_after"] else ""))
        if self.bait is not None and c["bait_watch"]:
            lines.append(tr("Наживка: %s") % self.bait_text())
        if self.last_caught:
            lines.append(tr("Последний улов: %s") % self.last_caught)
        return lines

    def bait_text(self):
        """Наживка: само число и на сколько хватит (по среднему времени между подсечками) или хотя бы
        порядок числа."""
        if self.bait_count is None:
            return {0: tr("нет"), 1: tr("меньше 10"), 2: "10–99"}.get(self.bait, "100+")
        text = str(self.bait_count)
        f = self.fisher
        if f is not None and f.started and f.hooks >= 3 and self.bait_count:
            left = self.bait_count * (time.time() - f.started) / f.hooks
            text += tr(" (хватит на ~%s)") % fmt_left(left)
        return text

    def refresh_mode(self):
        if getattr(self, "overlay", None) is not None:
            self.overlay.set_mode(self.mode_lines() if self.cfg.get("overlay_mode", True) else [])

    def build_overlay_opts(self, box, row):
        """Под «Окошко поверх игры»: прозрачность, размер текста, режим работы, прятать на паузе."""
        opts = ttk.Frame(box, style="Card.TFrame")
        opts.grid(row=row, column=0, columnspan=2, sticky="w", padx=(22, 0))
        ttk.Label(opts, text=tr("непрозрачность"), style="Muted.TLabel").pack(side="left")
        alphas = ["100%", "90%", "80%", "70%", "60%", "50%"]
        av = tk.StringVar(value="%d%%" % int(self.cfg["overlay_alpha"]))
        cb = ttk.Combobox(opts, textvariable=av, values=alphas, state="readonly", width=5)
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_overlay_opt("overlay_alpha", int(av.get().rstrip("%"))))
        ttk.Label(opts, text=tr("текст"), style="Muted.TLabel").pack(side="left")
        fonts = [("small", tr("мелкий")), ("normal", tr("обычный")), ("large", tr("крупный"))]
        fv = tk.StringVar(value=dict(fonts).get(self.cfg["overlay_font"], fonts[1][1]))
        cb = ttk.Combobox(opts, textvariable=fv, values=[t for _, t in fonts], state="readonly", width=9)
        cb.pack(side="left", padx=(4, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_overlay_opt(
            "overlay_font", {t: k for k, t in fonts}[fv.get()]))
        row += 1
        opts2 = ttk.Frame(box, style="Card.TFrame")
        opts2.grid(row=row, column=0, columnspan=2, sticky="w", padx=(22, 0))
        for key, text in (("overlay_mode", tr("режим работы")), ("overlay_hide_paused", tr("прятать на паузе"))):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(opts2, text=text, variable=var,
                            command=lambda k=key, v=var: self.set_overlay_opt(k, v.get())).pack(side="left", padx=(0, 12))
        return row + 1

    def set_overlay_opt(self, key, value):
        self.cfg[key] = value
        save_cfg(self.cfg)
        if self.overlay is not None:              # размер текста — заново построить окошко
            self.overlay.destroy()
            self.overlay = None
        self.toggle_overlay()

    def buff_text(self, status):
        names = {"fishing": tr("рыбалки"), "crate": tr("ящиков"), "sonar": tr("сонара"), "calm": tr("спокойствия")}
        parts = ["%s %s" % (names[n], "✓" if ok else "✗") for n, ok in status.items()]
        return tr("Зелья: ") + " · ".join(parts)

    def show_gear(self, d):
        self.gear = d
        parts = []
        if d.get("rod_slot") is not None:
            parts.append(tr("Удочка: слот %d") % ((d["rod_slot"] + 1) % 10) +
                         (tr(" (задан)") if d.get("manual") else ""))
        if d.get("bobber"):
            parts.append(tr("поплавок: %s") % d["bobber"])
        if self.catch_info and self.cfg["sonar_filter"] and self.catch_data:
            b = self.catch_info.get("biome")
            if b:
                g = self.catch_data.group[b]
                parts.append(tr("биом: %s") % (g["ru"] if i18n.LANG == "ru" else g["en"]) +
                             (tr(" (авто)") if self.cfg["catch_biome"] == "auto" else ""))
        if self.bait is not None and self.cfg["bait_watch"]:
            parts.append(tr("наживка: %s") % self.bait_text())
        self.gear_lbl.config(text=" · ".join(parts))
        if parts:                          # пустую строку не показываем — окно не растёт зря
            self.gear_lbl.pack(anchor="w")
        else:
            self.gear_lbl.pack_forget()

    def show_buffs(self, status):
        if not self.cfg["buffs_on"]:
            self.buff_lbl.config(text=tr("Зелья: не слежу (вкладка «Автоматика»)"))
        elif status is None:
            self.buff_lbl.config(text=tr("Зелья: проверю при забросе"))
        else:
            self.buff_lbl.config(text=self.buff_text(status))

    def test_buffs(self):
        self.buff_test_lbl.config(text=tr("Проверяю…"))

        def work():
            import mss
            hwnd = af.find_terraria()
            if not hwnd:
                self.q.put(("buff_test", {"text": tr("Окно Terraria не найдено — игра запущена?")}))
                return
            with (getattr(mss, "MSS", None) or mss.mss)() as sct:
                cl = af.client_rect(hwnd)
                status = self.fisher.check_buffs(sct, cl, force=True) or {}
                slots = self.fisher.potion_slots(self.fisher.hotbar_frame(sct, cl))
            want = {n: ok for n, ok in status.items()}
            text = self.buff_text(want) if want else tr("Не выбрано ни одного зелья.")
            names = {"fishing": tr("рыбалки"), "crate": tr("ящиков"), "sonar": tr("сонара"), "calm": tr("спокойствия")}
            text += "\n" + (tr("В хотбаре: ") + ", ".join(tr("%s — слот %d") % (names[n], (j + 1) % 10)
                                                          for n, j in sorted(slots.items(), key=lambda x: x[1]))
                            if slots else tr("В хотбаре зелий не нашёл."))
            self.q.put(("buff_test", {"text": text}))
        threading.Thread(target=work, daemon=True).start()

    def show_hb(self, text):
        self.hb_lbl.config(text=text)
        self.hb_lbl.pack(anchor="w", padx=(22, 0), after=self.hb_row)

    def snap_hotbar(self):
        """Сохранить хотбар из игры как есть (пиксель в пиксель) — по таким снимкам настраивается
        распознавание удочек. 3 секунды — чтобы переключиться в игру и окно программы не мешало."""
        self.show_hb(tr("Переключитесь в игру — снимок через 3 с…"))

        def work():
            import mss
            import hotbar
            time.sleep(3)
            hwnd = af.find_terraria()
            if not hwnd:
                self.q.put(("hb_test", {"text": tr("Окно Terraria не найдено — игра запущена?")}))
                return
            with (getattr(mss, "MSS", None) or mss.mss)() as sct:
                frame = self.fisher.hotbar_frame(sct, af.client_rect(hwnd))
            folder = os.path.join(af.DATA_DIR, "hotbar")
            name = time.strftime("hotbar_%Y%m%d_%H%M%S")
            try:
                af.save_png(frame, os.path.join(folder, name + ".png"))
            except Exception as e:
                self.q.put(("hb_test", {"text": tr("Не удалось сохранить снимок: %r") % e}))
                return
            sel = hotbar.selected_slot(frame)
            if sel is None:
                text = tr("Сохранено: %s. Выбранный (жёлтый) слот не виден — закройте инвентарь "
                          "и повторите.") % os.path.join("hotbar", name + ".png")
            else:
                text = tr("Сохранено: %s. Выбран слот %d.") % (os.path.join("hotbar", name + ".png"),
                                                               (sel[0] + 1) % 10)
                rods = self.fisher.rods
                r = rods.scores(frame) if rods else None
                if r:
                    found = rods.find(frame, af.ROD_HINT_MIN, af.ROD_HINT_MARGIN)
                    text += " " + (tr("Удочка узнаётся в слоте %d (%.2f).") % ((found[0] + 1) % 10, found[2])
                                   if found else tr("Удочку уверенно не узнал."))
                    try:
                        with open(os.path.join(folder, name + ".txt"), "w", encoding="utf-8") as fh:
                            fh.write("selected=%d scale=%.2f\n" % ((sel[0] + 1) % 10, sel[1]))
                            for i, (v, k, cnt) in enumerate(r[1]):
                                fh.write("slot %d: count=%s score=%.3f %s\n" % ((i + 1) % 10, cnt, v, k))
                            fh.write("rod=%s\n" % (found and (found[0] + 1) % 10))
                    except Exception:
                        pass
            self.q.put(("hb_test", {"text": text}))
        threading.Thread(target=work, daemon=True).start()

    # ---------- действия ----------
    def set_hotkey(self):
        name, reset = self.hotkey_var.get().lower(), self.reset_var.get().lower()
        if name == reset:   # одна клавиша на два действия — нельзя, возвращаем как было
            self.hotkey_var.set(self.cfg["hotkey"].upper())
            self.reset_var.set(self.cfg["reset_key"].upper())
            self.add_log(tr("Клавиши управления и «новые точки» должны быть разными."))
            return
        self.cfg["hotkey"], self.cfg["reset_key"] = name, reset
        self.fisher.set_hotkey(name)
        self.fisher.set_reset_key(reset)
        save_cfg(self.cfg)
        if not self.fisher.running.is_set():
            self.set_state("idle", tr("Готов"), self.fisher.idle_hint())

    def set_lang(self):
        code = {n: k for k, n in LANGS}[self.lang_var.get()]
        self.cfg["lang"] = code
        save_cfg(self.cfg)
        i18n.set_lang(code)
        self.rebuild()

    def rebuild(self):
        """Пересоздать окно на новом языке, сохранив всё остальное."""
        for w in self.root.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self.build()
        self.nb.select(1)
        lines, self.log_lines = self.log_lines, []
        for stamp, text, kind in lines:
            self.add_log(text, kind, stamp)
        self.show_stats()
        if self.fisher.bobber is not None:
            self.on_event("bobber", {"img": self.fisher.bobber})
        self.on_event("points", {"saved": self.fisher.has_points()})
        self.fisher.gear_changed()
        running = self.fisher.running.is_set()
        self.set_state(self.state, self.state_title(self.state), "" if running else self.fisher.idle_hint())
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
        self.toggle_overlay()

    def state_title(self, state):
        return {"idle": tr("Готов"), "cast": tr("Заброс"), "search": tr("Ищу поплавок"),
                "mark": tr("Отметьте поплавок"), "wait": tr("Жду поклёвку"), "hook": tr("Поклёвка!"),
                "pause": tr("Пауза")}.get(state, "")

    def set_auto(self):
        self.cfg["auto_calib"] = bool(self.auto_var.get())
        af.AUTO_CALIB = self.cfg["auto_calib"]
        save_cfg(self.cfg)
        self.fisher.calib_changed()

    def show_calib(self):
        c = self.calib
        if not self.cfg["auto_calib"]:
            text = tr("Выключена — порог берётся с ползунка")
        elif c["casts"] < af.CALIB_MIN_CASTS:
            text = tr("Учусь: нужно ещё забросов — %d (пока порог с ползунка)") % (af.CALIB_MIN_CASTS - c["casts"])
        else:
            text = tr("Сейчас порог %d%% (подобран по %d забросам)") % (round(100 * c["ratio"]), c["casts"])
        self.calib_lbl.config(text=text)

    def set_zoom(self):
        s = int(self.zoom_var.get().rstrip("%")) / 100
        self.cfg["scale"] = s
        save_cfg(self.cfg)
        self.fisher.reset_points()           # другой масштаб — другой размер поплавка
        self.fisher.set_scale(s)

    def set_sens(self, save=True):
        v = int(round(self.sens_var.get()))
        self.sens_lbl.config(text="%d%%" % v)
        self.cfg["sink_ratio"] = v / 100
        af.SINK_RATIO = v / 100
        if save:
            save_cfg(self.cfg)

    def set_wait(self):
        try:
            v = max(10, min(180, int(self.wait_var.get())))
        except Exception:
            return
        self.cfg["max_wait"] = v
        af.MAX_WAIT = float(v)
        save_cfg(self.cfg)

    def set_check(self, key):
        self.cfg[key] = bool(self.checks[key].get())
        save_cfg(self.cfg)
        if key == "overlay":
            self.toggle_overlay()
        elif key == "sound":
            af.SOUND = self.cfg["sound"]
        elif key == "debug":
            self.fisher.debug = self.cfg["debug"]
        elif key == "record":
            self.fisher.stop_fishing(tr("Режим изменён — начните заново."), notify=False)
            self.fisher.record = self.cfg["record"]
        self.refresh_mode()

    def toggle_overlay(self):
        if self.cfg["overlay"] and self.overlay is None:
            self.overlay = Overlay(self)
            self.overlay.set_state(self.state, self.state_lbl.cget("text"), self.hint_lbl.cget("text"))
            self.refresh_mode()
        elif not self.cfg["overlay"] and self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    def start_countdown(self):
        if self.fisher.running.is_set():
            return
        self.countdown = 5
        self.start_btn.state(["disabled"])
        self.countdown_step()

    def countdown_step(self):
        if self.countdown <= 0:
            self.start_btn.state(["!disabled"])
            self.fisher.on_toggle()        # как нажатие клавиши: берёт точку под курсором
            return
        if self.fisher.has_points():
            self.set_state("cast", tr("Продолжаю через %d…") % self.countdown,
                           tr("Переключитесь в игру — продолжу с прежними точками"))
        else:
            self.set_state("cast", tr("Старт через %d…") % self.countdown,
                           tr("Переключитесь в игру и наведите курсор на воду, куда забрасывать"))
        self.countdown -= 1
        self.root.after(1000, self.countdown_step)

    def pause(self):
        self.countdown = 0
        self.fisher.stop_fishing(tr("Пауза (из окна программы)."), notify=False)

    def new_points(self):
        self.countdown = 0
        self.fisher.reset_points()

    # ---------- события движка ----------
    def pump(self):
        live = None
        try:
            while True:
                kind, d = self.q.get_nowait()
                if kind == "live":
                    live = d
                else:
                    self.on_event(kind, d)
        except queue.Empty:
            pass
        if live:
            self.on_live(live)
        self.root.after(50, self.pump)

    def on_event(self, kind, d):
        if kind == "log":
            self.add_log(d["text"], d.get("kind", "info"))
        elif kind == "buffs":
            self.show_buffs(d["status"])
        elif kind == "gear":
            self.show_gear(d)
        elif kind == "catch":
            self.catch_info = d
            if d.get("caught"):
                self.history.add_catch(d.get("id"))
                self.donate_nudge()
            elif not d.get("wanted", True):
                self.history.add_skip()           # отпустили по сонару
            if d.get("caught") and d.get("name"):
                self.last_caught = d["name"]
            self.show_gear(self.gear)
            self.refresh_mode()
        elif kind == "zoom":                         # Zoom игры узнан по размеру поплавка
            self.cfg["scale"] = d["scale"]
            save_cfg(self.cfg)
            if getattr(self, "zoom_var", None) is not None:
                self.zoom_var.set("%d%%" % round(100 * d["scale"]))
        elif kind == "absent":
            self.absent = d["potions"]
            self.refresh_mode()
        elif kind == "bait":
            if d.get("count") is not None:
                self.bait_count = d["count"]
            elif d["digits"] != self.bait:
                self.bait_count = None             # число сменилось, а прочитать не вышло
            self.bait = d["digits"]
            self.show_gear(self.gear)
            self.refresh_mode()
        elif kind == "shutdown":
            self.cancel_btn.state(["!disabled"] if d["seconds"] else ["disabled"])
            if d["seconds"] and self.cfg["toasts"]:
                toast(tr("Выключение компьютера"),
                      tr("Рыбалка закончена. Компьютер выключится через %d с.") % d["seconds"])
        elif kind == "tray":
            self.on_tray(d["cmd"])
        elif kind == "update":
            self.on_update(d)
        elif kind == "diagnostics":
            self.show_diagnostics(d)
        elif kind == "update_progress":
            self.update_btn.config(text=tr("Скачиваю… %d%%") % round(100 * d["p"]))
        elif kind == "update_ready":
            self.show_update_btn()
            self.on_update_ready(d)
        elif kind == "hb_test":
            self.show_hb(d["text"])
        elif kind == "buff_test":
            self.buff_test_lbl.config(text=d["text"])
        elif kind == "calib":
            self.calib = d
            self.show_calib()
        elif kind == "state":
            self.set_state(d["state"], d["title"], d["hint"])
        elif kind == "stats":
            self.stats = d
            self.show_stats()
        elif kind == "bobber":
            img = bgr_to_rgb(d["img"])
            self.tmpl_photo = photo(img, 2)
            self.tmpl_lbl.config(image=self.tmpl_photo, text=tr(" запомнен"))
        elif kind == "points":
            self.start_btn.config(text=tr("▶ Продолжить (5 с)") if d["saved"] else tr("▶ Старт (5 с)"))
            if not d["saved"] and self.fisher.bobber is None:
                self.tmpl_lbl.config(image="", text=tr("поплавок\nне отмечен"))
        elif kind == "hook":
            self.history.add_hook()
            if self.cfg["toast_hooks"] and self.cfg["toasts"]:
                toast(tr("Поклёвка!"), tr("Подсечка №%d (ждали %.0f с)") % (self.stats["hooks"], d["waited"]))
            if self.cfg["hook_sound"]:
                beep_async(1000, 90)
        elif kind == "notify":
            if self.cfg["toasts"]:
                toast(d["title"], d["text"])

    def on_live(self, d):
        frac = d["seen"] / d["ref"] if d["ref"] else None
        self.bar.set(frac, d["ratio"], d["flash"])
        if self.overlay:
            self.overlay.bar.set(frac, d["ratio"], d["flash"])
        self.wait_lbl.config(text=tr("Жду поклёвку: %d с из %d · порог %d%%%s")
                                  % (d["t"], d["max_wait"], round(100 * d["ratio"]),
                                     tr(" (авто)") if d.get("auto") else ""))
        self.preview_photo = photo(bgr_to_rgb(d["frame"]), max(1, 116 // max(1, d["frame"].shape[0])))
        self.preview.config(image=self.preview_photo)

    def set_state(self, state, title, hint):
        self.state = state
        if self.tray is not None:
            self.tray.set_tip("%s — %s" % (APP, title))
        color = STATE_COLOR.get(state, C["muted"])
        self.dot.delete("all")
        self.dot.create_oval(2, 2, 16, 16, fill=color, width=0)
        self.state_lbl.config(text=title, fg=color if state in ("mark", "hook", "pause") else C["text"])
        self.hint_lbl.config(text=hint)
        thr = self.fisher.sink_ratio() if self.fisher else af.SINK_RATIO
        if state != "wait":
            self.bar.set(None, thr)
            self.wait_lbl.config(text=" ")
        running = self.fisher.running.is_set() if self.fisher else False
        self.pause_btn.state(["!disabled"] if running else ["disabled"])
        if self.overlay:
            self.overlay.set_state(state, title, hint)
            if state != "wait":
                self.overlay.bar.set(None, thr)
            # на паузе окошко можно прятать — чтобы не мешало играть самому
            if self.cfg.get("overlay_hide_paused") and state in ("pause", "idle"):
                self.overlay.withdraw()
            else:
                self.overlay.deiconify()

    def show_stats(self):
        s = self.stats
        self.stat_lbls["hooks"].config(text=str(s["hooks"]))
        self.stat_lbls["casts"].config(text=str(s["casts"]))
        parts = []
        if s["fails"]:
            parts.append(tr("Неудачных забросов подряд: %d из %d") % (s["fails"], af.MAX_FAILS))
        if s.get("skipped"):
            parts.append(tr("Пропущено по сонару: %d") % s["skipped"])
        if getattr(self, "cpu", None) is not None and self.fisher.running.is_set():
            parts.append(tr("процессор: %d%%") % self.cpu)
        self.fails_lbl.config(text=" · ".join(parts))
        if self.overlay:
            self.overlay.count.config(text=tr("Подсечек: %d") % s["hooks"])
        self.tick(reschedule=False)

    def tick(self, reschedule=True):
        started = self.stats.get("started")
        if started:
            up = time.time() - started
            self.stat_lbls["time"].config(text=fmt_time(up))
            rate = self.stats["hooks"] / (up / 3600) if up > 60 else 0
            self.stat_lbls["rate"].config(text="%d" % rate if up > 60 else "—")
        else:
            self.stat_lbls["time"].config(text="0:00:00")
            self.stat_lbls["rate"].config(text="—")
        if reschedule:
            # нагрузка на процессор (всей программы, в процентах одного ядра) — раз в 5 с
            now, cpu = time.perf_counter(), time.process_time()
            last = getattr(self, "cpu_mark", None)
            if last is None or now - last[0] >= 5:
                if last is not None:
                    self.cpu = round(100 * (cpu - last[1]) / (now - last[0]))
                    self.show_stats()
                self.cpu_mark = (now, cpu)
            self.root.after(1000, self.tick)

    def add_log(self, text, kind="info", stamp=None):
        if stamp is None:                          # новая строка (а не пересоздание журнала) — и в файл
            self.write_log_file(text, kind)
        stamp = stamp or time.strftime("%H:%M:%S  ")
        self.log_lines = (self.log_lines + [(stamp, text, kind)])[-300:]
        t = self.log_txt
        t.config(state="normal")
        t.insert("end", stamp, "time")
        t.insert("end", text.lstrip("> ") + "\n", kind if kind in ("good", "bad", "ask") else "info")
        if int(t.index("end-1c").split(".")[0]) > 500:
            t.delete("1.0", "100.0")
        t.see("end")
        t.config(state="disabled")

    # ---------- обновления ----------
    def check_updates(self, force=False):
        """Раз в сутки (или по кнопке) — нет ли на GitHub версии новее. Читает только публичные
        сведения о последнем релизе."""
        if self.selftest or (not force and (not self.cfg.get("update_check", True) or
                                            time.time() - float(self.cfg.get("update_checked") or 0) < 86400)):
            return

        def work():
            import updates
            try:
                found = updates.newer(VERSION)
            except Exception as e:
                self.q.put(("update", {"error": repr(e), "force": force}))
                return
            self.q.put(("update", {"found": found, "force": force}))
        threading.Thread(target=work, daemon=True).start()

    def on_update(self, d):
        self.cfg["update_checked"] = time.time()
        save_cfg(self.cfg)
        if d.get("error"):
            if d["force"]:
                self.add_log(tr("Не удалось проверить обновления: %s") % d["error"], "bad")
            return
        found = d.get("found")
        if not found:
            if d["force"]:
                self.add_log(tr("У вас последняя версия (%s).") % VERSION, "good")
            return
        version, url, files = found
        self.update_url = url
        self.update_info = found
        self.show_update_btn()
        self.root.title("%s %s — %s" % (APP, VERSION, tr("доступна %s") % version))
        self.add_log(tr("Вышла новая версия %s — %s") % (version, url), "good")
        if self.cfg["toasts"]:
            toast(APP, tr("Вышла новая версия %s. Обновить — кнопкой на вкладке «Настройки».") % version)
        if d["force"]:
            self.install_update()

    def show_update_btn(self):
        btn = getattr(self, "update_btn", None)
        if btn is not None and btn.winfo_exists():
            btn.config(text=tr("Обновить до %s") % self.update_info[0] if self.update_info else tr("Обновления"))

    def on_update_btn(self):
        if self.update_info:
            self.install_update()
        else:
            self.check_updates(force=True)

    def install_update(self):
        """Обновление в один клик: скачать новую версию и закрыться, чтобы её файлы можно было заменить.
        Установленная — запускается установщик; портативная — архив распаковывается, и после закрытия
        программы её файлы заменяются новыми, а программа запускается снова."""
        from tkinter import messagebox
        version, url, files = self.update_info
        portable = PORTABLE and getattr(sys, "frozen", False)
        asset = (files or {}).get("portable" if portable else "setup")
        if asset is None or getattr(self, "updating", False) or not getattr(sys, "frozen", False):
            try:
                os.startfile(url)
            except Exception:
                pass
            return
        question = (tr("Скачать и установить версию %s?\n\nПрограмма закроется, обновится и запустится "
                       "снова (настройки и точки сохранятся).") if portable else
                    tr("Скачать и установить версию %s?\n\nПрограмма закроется, а "
                       "установщик обновит её (настройки и точки сохранятся)."))
        if not messagebox.askyesno(APP, question % version, parent=self.root):
            return
        self.updating = True
        self.fisher.stop_fishing(tr("Обновление — рыбалка остановлена."), notify=False)
        self.add_log(tr("Скачиваю версию %s…") % version)

        def work():
            import tempfile
            import updates
            folder = os.path.join(tempfile.gettempdir(), "TerrariaAutoFish-update")
            try:
                path = updates.download(asset, folder, lambda p: self.q.put(("update_progress", {"p": p})))
                if portable:
                    src = updates.extract_portable(path, os.path.join(folder, "portable-" + version))
                    cmd = updates.portable_update_command(src, af.HERE, os.getpid())
                    self.q.put(("update_ready", {"cmd": cmd}))
                    return
            except Exception as e:
                self.q.put(("update_ready", {"error": repr(e)}))
                return
            self.q.put(("update_ready", {"path": path}))
        threading.Thread(target=work, daemon=True).start()

    def on_update_ready(self, d):
        self.updating = False
        if d.get("error"):
            self.add_log(tr("Не удалось скачать обновление: %s") % d["error"], "bad")
            return
        try:
            if d.get("cmd"):                      # портативная: заменит файлы, когда программа закроется
                subprocess.Popen(d["cmd"], close_fds=True, creationflags=0x08000000)   # CREATE_NO_WINDOW
            else:
                subprocess.Popen([d["path"]], close_fds=True)
        except Exception as e:
            self.add_log(tr("Не удалось запустить установщик: %r") % e, "bad")
            return
        self.close()                              # установщик заменит файлы, пока программа закрыта

    # ---------- журнал в файл и отчёт ----------
    def write_log_file(self, text, kind="info"):
        """Журнал пишется и в файл logs/autofish_ГГГГ-ММ-ДД.log рядом с программой."""
        if self.selftest:
            return
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            path = os.path.join(LOG_DIR, time.strftime("autofish_%Y-%m-%d.log"))
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("%s [%s] %s\n" % (time.strftime("%H:%M:%S"), kind, text.lstrip("> ")))
        except Exception:
            pass

    def start_log_file(self):
        """Новая запись в журнале при запуске; журналы старше LOG_DAYS дней удаляем."""
        if self.selftest:
            return
        try:
            now = time.time()
            for f in os.listdir(LOG_DIR) if os.path.isdir(LOG_DIR) else []:
                p = os.path.join(LOG_DIR, f)
                if f.endswith(".log") and now - os.path.getmtime(p) > LOG_DAYS * 86400:
                    os.remove(p)
        except Exception:
            pass
        self.write_log_file("===== %s %s: %s =====" % (APP, VERSION, tr("запуск")))

    def make_report(self):
        """Архив для разбора проблемы: журналы, настройки, последние отладочные картинки,
        снимки хотбара и сведения о системе. Открывает папку с архивом."""
        import zipfile

        def newest(folder, n, exts=(".png", ".txt", ".log")):
            try:
                files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
            except Exception:
                return []
            return sorted(files, key=os.path.getmtime)[-n:]

        os.makedirs(af.DATA_DIR, exist_ok=True)
        path = os.path.join(af.DATA_DIR, time.strftime("report_%Y%m%d_%H%M%S.zip"))
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for f in newest(LOG_DIR, 3, (".log",)):
                    z.write(f, "logs/" + os.path.basename(f))
                z.writestr("settings/settings.json", json.dumps(self.cfg, ensure_ascii=False, indent=2))
                for f in newest(af.DATA_DIR, 3, exts=(".txt",)):
                    z.write(f, "diagnostics/" + os.path.basename(f))
                for name in ("gear.json", "catch_history.json"):
                    f = os.path.join(CFG_DIR, name)
                    if os.path.exists(f):
                        z.write(f, "settings/" + name)
                for sub, n in (("debug", 40), ("record", 40), ("hotbar", 20)):
                    for f in newest(os.path.join(af.DATA_DIR, sub), n):
                        z.write(f, sub + "/" + os.path.basename(f))
                z.writestr("system.txt", self.system_info())
        except Exception as e:
            self.add_log(tr("Не удалось собрать отчёт: %r") % e, "bad")
            return
        self.add_log(tr("Отчёт сохранён: %s") % path, "good")
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

    def system_info(self):
        import platform
        lines = ["%s %s" % (APP, VERSION), "portable=%s frozen=%s" % (PORTABLE, getattr(sys, "frozen", False)),
                 "windows=%s" % platform.platform(), "python=%s" % platform.python_version(),
                 "screen=%dx%d" % (ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1))]
        try:
            hwnd = af.find_terraria()
            lines.append("terraria_client=%s" % (af.client_rect(hwnd),) if hwnd else "terraria_client=не найдена")
        except Exception:
            pass
        f = self.fisher
        lines.append("scale=%s rod_slot=%s manual_rod=%s bobber_kind=%s points=%s ratio=%.2f" % (
            f.scale, f.rod_slot, af.ROD_SLOT, f.bobber_kind, f.has_points(), f.sink_ratio()))
        lines.append("settings=" + json.dumps(self.cfg, ensure_ascii=False))
        return "\n".join(lines) + "\n"

    # ---------- мастер первого запуска ----------
    def show_wizard(self):
        import wizard
        if getattr(self, "wizard", None) is not None and self.wizard.winfo_exists():
            self.wizard.lift()
            return

        def done():
            self.cfg["wizard_done"] = True
            save_cfg(self.cfg)
            self.wizard = None
        self.wizard = wizard.Wizard(self.root, C, FONT, self.cfg["hotkey"].upper(), self.cfg["reset_key"].upper(), done)

    # ---------- значок в трее ----------
    def start_tray(self):
        """Значок в трее: клик — показать/спрятать окно, меню — пауза и выход. Свёрнутое окно
        прячется в трей."""
        try:
            import tray
            ico = os.path.join(CFG_DIR, "tray.ico")
            if not os.path.exists(ico):
                os.makedirs(CFG_DIR, exist_ok=True)
                write_ico(ico, sizes=(16, 32, 48))
            import donate
            menu = [("show", tr("Показать окно")), ("toggle", tr("Пауза / продолжить")), ("help", tr("Как начать"))]
            if donate.LINKS:
                menu.append(("donate", tr("☕ Поддержать автора")))
            menu += [None, ("quit", tr("Выход"))]
            self.tray = tray.Tray(APP, ico, menu, lambda c: self.q.put(("tray", {"cmd": c})))
            if not self.tray.start():
                self.tray = None
                return
            self.root.bind("<Unmap>", self.on_unmap)
        except Exception:
            self.tray = None

    def on_unmap(self, event):
        if event.widget is self.root and self.tray is not None and self.root.state() == "iconic":
            self.root.withdraw()                  # свернули — в трей

    def on_tray(self, cmd):
        if cmd in ("click", "show"):
            if cmd == "click" and self.root.state() == "normal":
                self.root.withdraw()
            else:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
        elif cmd == "toggle":
            self.fisher.on_toggle()
        elif cmd == "donate":
            self.show_donate()
        elif cmd == "help":
            self.root.deiconify()
            self.show_wizard()
        elif cmd == "quit":
            self.close()

    def close(self):
        self.cfg["win_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        if self.tray is not None:
            self.tray.stop()
        self.fisher.shutdown()
        if not self.selftest:                     # самопроверка не трогает настройки игрока
            save_cfg(self.cfg)
        self.root.destroy()

    # ---------- самопроверка (для сборки) ----------
    def demo(self):
        h, w = 58, 38
        img = np.zeros((h, w, 3), np.float32)
        img[:] = (60, 55, 50)
        img[34:] = (140, 70, 25)
        img[33:35] = (170, 160, 150)
        yy, xx = np.mgrid[0:h, 0:w]
        star = (np.abs(xx - 19) + np.abs(yy - 28) * 1.6 < 8)
        img[star] = (30, 170, 240)
        self.q.put(("bobber", {"img": img[17:39, 12:26]}))
        self.q.put(("stats", {"hooks": 12, "casts": 15, "fails": 1, "started": time.time() - 1520}))
        self.q.put(("state", {"state": "wait", "title": tr("Жду поклёвку"),
                              "hint": tr("Мышь не трогайте. HOME — пауза")}))
        self.q.put(("log", {"text": tr("Поклёвка (%s)! Подсекаю. Подсечек: %d (ждали %.1f с)")
                                    % (tr("видно 31% поплавка"), 12, 6.2), "kind": "good"}))
        self.q.put(("calib", {"ratio": 0.49, "casts": 6, "auto": True}))
        self.q.put(("gear", {"rod_slot": 4, "manual": False, "bobber": "Glowing Fishing Bobber"}))
        self.q.put(("bait", {"digits": 3, "count": 294}))
        bass = next((i for i, it in self.catch_data.items.items() if it["en"] == "Bass"), None)             if getattr(self, "catch_data", None) else None
        if bass is not None:
            it = self.catch_data.items[bass]
            self.q.put(("catch", {"id": bass, "name": it["ru"] if i18n.LANG == "ru" else it["en"], "wanted": True,
                                  "biome": "forest", "caught": True}))
        self.q.put(("live", {"seen": 88, "ref": 110, "ratio": 0.49, "frame": img, "t": 7.4,
                             "max_wait": 45, "flash": False, "auto": True}))

    def snapshot(self, path, close=True, overlay=True):
        """Снимок окон программы через PrintWindow — работает, даже если окно ничем закрыто."""
        import ctypes.wintypes as wt
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        self.root.update()
        for w, p in ((self.root, path), (self.overlay if overlay else None, path.replace(".png", "_overlay.png"))):
            if w is None:
                continue
            hwnd = u.GetParent(w.winfo_id())
            r = wt.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(r))
            ww, hh = r.right - r.left, r.bottom - r.top
            hdc = u.GetWindowDC(hwnd)
            mdc = g.CreateCompatibleDC(hdc)
            bmp = g.CreateCompatibleBitmap(hdc, ww, hh)
            g.SelectObject(mdc, bmp)
            u.PrintWindow(hwnd, mdc, 2)
            bmi = struct.pack("<IiiHHIIiiII", 40, ww, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
            buf = ctypes.create_string_buffer(ww * hh * 4)
            g.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.c_char_p(bmi), 0)
            g.DeleteObject(bmp)
            g.DeleteDC(mdc)
            u.ReleaseDC(hwnd, hdc)
            img = np.frombuffer(buf.raw, np.uint8).reshape(hh, ww, 4)[:, :, :3].astype(np.float32)
            af.save_png(img, p)
        if close:
            self.close()

    def run(self):
        self.root.mainloop()


def uninstall():
    """Удаление (Windows вызывает «TerrariaAutoFish.exe --uninstall» из «Приложений»)."""
    import setup_core as sc
    from tkinter import messagebox
    i18n.set_lang(load_cfg().get("lang", "auto"))
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(APP, tr("Удалить Terraria AutoFish с этого компьютера?")):
        return
    with_settings = messagebox.askyesno(APP, tr("Удалить также настройки и сохранённые точки?"))
    home = sc.installed_dir()
    same = home and os.path.normcase(os.path.abspath(home)) == os.path.normcase(os.path.abspath(af.HERE))
    if same:
        sc.uninstall(af.HERE, remove_settings=with_settings)
    else:                            # запущено не из папки установки — папку не трогаем
        sc.remove_shortcuts()
        sc.unregister()
    messagebox.showinfo(APP, tr("Terraria AutoFish удалена."))


def main():
    args = sys.argv[1:]
    if args[:1] == ["--uninstall"]:
        uninstall()
        return
    if args[:1] == ["--selfcheck"]:                   # проверка сборки: всё ли внутри .exe
        f = af.Fisher()
        with open(args[1], "w", encoding="utf-8") as out:
            out.write("version=%s buffs=%s icons=%s rods=%d bobbers=%d portable=%s\n" % (
                VERSION, f.buffs is not None, sorted(f.buffs.icons) if f.buffs else [],
                len(f.rods.rods.sprites) if f.rods else 0,
                len({s.name for s in f.bobber_sprites.sprites}) if f.bobber_sprites else 0, PORTABLE))
            import ocr
            out.write("potions=%d catches=%d ocr=%s\n" % (
                len(f.potions.rgba) if f.potions else 0, len(f.catches.items) if f.catches else 0,
                ",".join(ocr.available_languages()) or "нет"))
            import gamenames
            out.write("game_names=%d from_game=%d\n" % (
                len(gamenames.load()), sum(1 for it in f.catches.items.values() if it.get("ru_wiki"))
                if f.catches else 0))
        return
    if args[:1] == ["--make-icon"]:
        write_ico(args[1])
        return
    if args[:1] == ["--make-version"]:                 # сведения о файле для .exe (сборка)
        write_version_info(args[1], args[2] if len(args) > 2 else APP, args[3] if len(args) > 3 else APP + ".exe")
        return
    selftest = args[1] if args[:1] == ["--selftest"] else None
    lang = args[2] if selftest and len(args) > 2 and args[2] in ("ru", "en") else None
    App(selftest=selftest, lang=lang).run()


if __name__ == "__main__":
    main()
