"""
Terraria AutoFish — приложение с окном, оверлеем поверх игры и уведомлениями Windows.
Вся логика рыбалки — в autofish.py.
"""
import base64
import ctypes
import json
import os
import queue
import struct
import subprocess
import sys
import threading
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
VERSION = "1.2.0"
# Портативная версия: рядом с программой лежит portable.txt — всё хранится в папке программы
PORTABLE = os.path.exists(os.path.join(af.HERE, "portable.txt"))
CFG_DIR = (os.path.join(af.HERE, "settings") if PORTABLE
           else os.path.join(os.environ.get("APPDATA") or af.HERE, "TerrariaAutoFish"))
CFG_PATH = os.path.join(CFG_DIR, "settings.json")
DEFAULTS = {
    "hotkey": "home", "reset_key": "end", "scale": 1.0, "sink_ratio": 0.55, "max_wait": 45,
    "overlay": True, "overlay_pos": None, "toasts": True, "toast_hooks": False,
    "sound": True, "hook_sound": False, "debug": False, "record": False, "win_pos": None,
    "lang": "auto", "auto_calib": True, "auto_recover": True, "auto_resume": True,
    "buffs_on": False, "buff_fishing": True, "buff_crate": True, "buff_key": "b",
    "auto_rod": True, "auto_mark": True,
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


def save_cfg(cfg):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
        self.attributes("-alpha", 0.9)
        self.configure(bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
        top = tk.Frame(self, bg=C["panel"])
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.dot = tk.Canvas(top, width=12, height=12, bg=C["panel"], highlightthickness=0)
        self.dot.pack(side="left")
        self.title = tk.Label(top, text=tr("Готов"), bg=C["panel"], fg=C["text"], font=(FONT, 11, "bold"))
        self.title.pack(side="left", padx=6)
        self.count = tk.Label(top, text=tr("Подсечек: 0"), bg=C["panel"], fg=C["text"], font=(FONT, 11, "bold"))
        self.count.pack(side="right")
        self.hint = tk.Label(self, text="", bg=C["panel"], fg=C["muted"], font=(FONT, 9),
                             wraplength=250, justify="left", anchor="w")
        self.hint.pack(fill="x", padx=10)
        self.bar = Bar(self, width=250, height=10)
        self.bar.pack(padx=10, pady=(4, 8))
        for w in (self, top, self.title, self.hint, self.count, self.dot):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag)
            w.bind("<ButtonRelease-1>", self.drag_end)
        self.update_idletasks()
        pos = app.cfg.get("overlay_pos")
        if not pos:
            pos = (20, self.winfo_screenheight() - 170)
        self.geometry("+%d+%d" % tuple(pos))
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

    def set_state(self, state, title, hint):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 11, 11, fill=STATE_COLOR.get(state, C["muted"]), width=0)
        self.title.config(text=title)
        self.hint.config(text=hint)


class App:
    def __init__(self, selftest=None, lang=None):
        self.cfg = load_cfg()
        self.selftest = selftest
        if lang:
            self.cfg["lang"] = lang
        self.apply_engine_cfg()
        self.q = queue.Queue()
        self.live = None
        self.stats = {"hooks": 0, "casts": 0, "fails": 0, "started": None}
        self.state = "idle"
        self.countdown = 0
        self.log_lines = []               # (время, текст, тип) — чтобы пересоздать журнал при смене языка
        self.calib = {"ratio": af.SINK_RATIO, "casts": 0, "auto": af.AUTO_CALIB}
        self.fisher = None

        self.root = tk.Tk()
        self.root.title("%s %s" % (APP, VERSION))
        self.root.configure(bg=C["bg"])
        self.root.resizable(True, True)
        self.icon = tk.PhotoImage(data=base64.b64encode(png_bytes(icon_rgba(64))))
        self.root.iconphoto(True, self.icon)
        self.style()
        self.build()
        self.root.after(10, self.dark_titlebar)
        self.place_window()

        self.fisher = af.Fisher(debug=self.cfg["debug"], record=self.cfg["record"],
                                events=lambda k, d: self.q.put((k, d)), toggle_key=self.cfg["hotkey"],
                                reset_key=self.cfg["reset_key"],
                                points_path=None if selftest else os.path.join(CFG_DIR, "points.npz"))
        self.fisher.set_scale(self.cfg["scale"])
        self.overlay = None
        self.toggle_overlay()
        self.fisher.start()

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
            self.root.after(3800, lambda: self.snapshot(selftest.replace(".png", "_auto.png"), overlay=False))

    def place_window(self):
        """Открыть окно там, где его оставили, но не за краем экрана."""
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = self.cfg.get("win_pos") or ((sw - w) // 2, max(0, (sh - h) // 3))
        x = max(0, min(int(x), sw - w))
        y = max(0, min(int(y), sh - h - 60))
        self.root.geometry("+%d+%d" % (x, y))

    def dark_titlebar(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
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
        af.AUTO_MARK = bool(self.cfg["auto_mark"])
        af.BUFFS_ON = bool(self.cfg["buffs_on"])
        af.BUFF_WANT = {"fishing": bool(self.cfg["buff_fishing"]), "crate": bool(self.cfg["buff_crate"])}
        af.BUFF_KEY = self.cfg["buff_key"]
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
        self.build_main(main)
        self.build_settings(sett)
        self.build_auto(auto)

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
        self.show_gear({"rod_slot": None, "rod": None, "bobber": None})

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
        ttk.Button(btns, text=tr("Папка"), command=lambda: os.startfile(af.HERE)).pack(side="right")

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
                          ("debug", tr("Сохранять отладочные картинки (папка debug)")),
                          ("record", tr("Режим записи: подсекаю я сам"))):
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            ttk.Checkbutton(box, text=text, variable=var, command=lambda k=key: self.set_check(k)).grid(
                row=row, column=0, columnspan=2, sticky="w")
            self.checks[key] = var
            row += 1
        ttk.Button(box, text=tr("Проверить уведомление"), command=lambda: toast(
            APP, tr("Так выглядят уведомления программы"))).grid(row=row, column=0, sticky="w", pady=(6, 0))
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
        check("auto_mark", tr("Сам находить поплавок после первого заброса (по картинкам с Terraria Wiki)"))
        ttk.Separator(box).pack(fill="x", pady=8)

        ttk.Label(box, text=tr("Если что-то пошло не так"), style="Card.TLabel",
                  font=(FONT, 9, "bold")).pack(anchor="w")
        check("auto_recover", tr("Не сдаваться: после сбоев пробовать снова через 10, 30, 60 с"))
        check("auto_resume", tr("Сам продолжать, когда я вернусь в игру из другого окна"))
        ttk.Separator(box).pack(fill="x", pady=8)

        ttk.Label(box, text=tr("Зелья"), style="Card.TLabel", font=(FONT, 9, "bold")).pack(anchor="w")
        check("buffs_on", tr("Следить за баффами и пить зелья, когда бафф закончился"))
        check("buff_fishing", tr("Зелье рыбалки (бафф «Рыбалка»)"), pad=22)
        check("buff_crate", tr("Ящичное зелье (бафф «Ящики»)"), pad=22)
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=tr("Клавиша быстрого баффа (как в игре)"), style="Card.TLabel").pack(side="left")
        self.buffkey_var = tk.StringVar(value=self.cfg["buff_key"].upper())
        cb = ttk.Combobox(row, textvariable=self.buffkey_var, values=[k.upper() for k in BUFF_KEYS],
                          state="readonly", width=5)
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_auto_opt("buff_key", self.buffkey_var.get().lower()))
        ttk.Label(box, text=tr("Быстрый бафф выпивает все зелья-баффы из инвентаря, чьих баффов сейчас нет, "
                               "и не тратит зелья, если бафф ещё идёт. Держите в инвентаре только нужные зелья."),
                  style="Muted.TLabel", wraplength=390, justify="left").pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text=tr("Проверить баффы сейчас"), command=self.test_buffs).pack(side="left")
        self.buff_test_lbl = ttk.Label(box, text=tr("Игра должна быть видна на экране (окно программы не должно её закрывать)."),
                                       style="Muted.TLabel", wraplength=390, justify="left")
        self.buff_test_lbl.pack(anchor="w", pady=(4, 0))

    def set_auto_opt(self, key, value):
        self.cfg[key] = value
        save_cfg(self.cfg)
        self.apply_engine_cfg()
        if key.startswith("buff"):
            self.fisher.last_buff_check = 0          # проверить при ближайшем забросе
            self.show_buffs(None)

    def buff_text(self, status):
        names = {"fishing": tr("рыбалки"), "crate": tr("ящиков")}
        parts = ["%s %s" % (names[n], "✓" if ok else "✗") for n, ok in status.items()]
        return tr("Зелья: ") + " · ".join(parts)

    def show_gear(self, d):
        parts = []
        if d.get("rod_slot") is not None:
            parts.append(tr("Удочка: слот %d") % ((d["rod_slot"] + 1) % 10) +
                         (" (%s)" % d["rod"] if d.get("rod") else ""))
        if d.get("bobber"):
            parts.append(tr("поплавок: %s") % d["bobber"])
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
                status = self.fisher.check_buffs(sct, af.client_rect(hwnd), force=True) or {}
            want = {n: ok for n, ok in status.items()}
            self.q.put(("buff_test", {"text": self.buff_text(want) if want else tr("Не выбрано ни одного зелья.")}))
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

    def toggle_overlay(self):
        if self.cfg["overlay"] and self.overlay is None:
            self.overlay = Overlay(self)
            self.overlay.set_state(self.state, self.state_lbl.cget("text"), self.hint_lbl.cget("text"))
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

    def show_stats(self):
        s = self.stats
        self.stat_lbls["hooks"].config(text=str(s["hooks"]))
        self.stat_lbls["casts"].config(text=str(s["casts"]))
        self.fails_lbl.config(text=(tr("Неудачных забросов подряд: %d из %d") % (s["fails"], af.MAX_FAILS))
                              if s["fails"] else "")
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
            self.root.after(1000, self.tick)

    def add_log(self, text, kind="info", stamp=None):
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

    def close(self):
        self.cfg["win_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
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
        self.q.put(("gear", {"rod_slot": 4, "rod": "Golden Fishing Rod", "bobber": "Glowing Fishing Bobber"}))
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
                len(f.bobber_sprites.sprites) if f.bobber_sprites else 0, PORTABLE))
        return
    if args[:1] == ["--make-icon"]:
        write_ico(args[1])
        return
    selftest = args[1] if args[:1] == ["--selftest"] else None
    lang = args[2] if selftest and len(args) > 2 and args[2] in ("ru", "en") else None
    App(selftest=selftest, lang=lang).run()


if __name__ == "__main__":
    main()
