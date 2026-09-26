"""
Установщик Terraria AutoFish. Внутри лежит TerrariaAutoFish.exe (добавляется при сборке).
Ставит программу для текущего пользователя (без прав администратора), создаёт ярлыки
и запись в «Приложения» Windows, откуда программу можно удалить.
"""
import os
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, ttk

import setup_core as sc
from i18n import system_lang

VERSION = "1.2.5"
LANG = system_lang()
TEXT = {
    "title": ("Установка Terraria AutoFish %s", "Terraria AutoFish %s Setup"),
    "intro": ("Автоматическая рыбалка для Terraria. Программа будет установлена для текущего "
              "пользователя — права администратора не нужны.",
              "Automatic fishing for Terraria. The program will be installed for the current user — "
              "no administrator rights needed."),
    "folder": ("Папка установки", "Install folder"),
    "browse": ("Обзор…", "Browse…"),
    "desktop": ("Ярлык на рабочем столе", "Desktop shortcut"),
    "start": ("Ярлык в меню «Пуск»", "Start menu shortcut"),
    "launch": ("Запустить после установки", "Launch after installation"),
    "install": ("Установить", "Install"),
    "update": ("Обновить", "Update"),
    "cancel": ("Отмена", "Cancel"),
    "close": ("Закрыть", "Close"),
    "working": ("Устанавливаю…", "Installing…"),
    "done": ("Готово! Terraria AutoFish установлена.\nУдалить её можно в «Параметры → Приложения».",
             "Done! Terraria AutoFish is installed.\nYou can remove it in Settings → Apps."),
    "busy": ("Не удалось заменить файл: закройте запущенную Terraria AutoFish и нажмите «%s» ещё раз.",
             "Could not replace the file: close the running Terraria AutoFish and press “%s” again."),
    "error": ("Ошибка установки: %s", "Installation error: %s"),
    "found": ("Программа уже установлена — установщик обновит её.",
              "The program is already installed — the installer will update it."),
}


def t(key):
    return TEXT[key][0 if LANG == "ru" else 1]


def payload():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "payload", sc.EXE_NAME)


BG, PANEL, TEXT_C, MUTED, GREEN, RED = "#14161b", "#1c2028", "#e8eaed", "#8f99a6", "#3ecf8e", "#ef5350"


class Setup:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(t("title") % VERSION)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        try:
            self.root.iconbitmap(os.path.join(base, "icon.ico"))
        except Exception:
            pass
        self.root.after(10, self.dark_titlebar)
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=PANEL, foreground=TEXT_C, font=("Segoe UI", 9), fieldbackground="#242a35",
                    bordercolor="#2e3544", lightcolor="#2e3544", darkcolor="#2e3544")
        s.configure("TButton", background="#242a35", foreground=TEXT_C, padding=(10, 4), borderwidth=0)
        s.map("TButton", background=[("active", "#2e3544"), ("disabled", PANEL)])
        s.configure("Accent.TButton", background=GREEN, foreground="#0d1a13", font=("Segoe UI", 9, "bold"))
        s.map("Accent.TButton", background=[("active", "#35b87d"), ("disabled", PANEL)])
        s.map("TCheckbutton", background=[("active", PANEL)],
              indicatorcolor=[("selected", GREEN), ("!selected", "#242a35")])

        box = tk.Frame(self.root, bg=PANEL, padx=16, pady=14)
        box.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(box, text="Terraria AutoFish %s" % VERSION, bg=PANEL, fg=TEXT_C,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(box, text=t("intro"), bg=PANEL, fg=MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(2, 10))

        existing = sc.installed_dir()
        tk.Label(box, text=t("folder"), bg=PANEL, fg=TEXT_C, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(box, bg=PANEL)
        row.pack(fill="x", pady=(2, 8))
        self.dir = tk.StringVar(value=existing or sc.default_dir())
        ttk.Entry(row, textvariable=self.dir, width=44).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=t("browse"), command=self.browse).pack(side="left", padx=(6, 0))

        self.desktop, self.start, self.launch = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        for var, key in ((self.desktop, "desktop"), (self.start, "start"), (self.launch, "launch")):
            ttk.Checkbutton(box, text=t(key), variable=var).pack(anchor="w")

        self.msg = tk.Label(box, text=t("found") if existing else "", bg=PANEL, fg=MUTED, wraplength=400,
                           justify="left")
        self.msg.pack(anchor="w", pady=(10, 0))
        btns = tk.Frame(box, bg=PANEL)
        btns.pack(fill="x", pady=(12, 0))
        self.action = t("update") if existing else t("install")
        self.go = ttk.Button(btns, text=self.action, style="Accent.TButton", command=self.install)
        self.go.pack(side="right")
        self.cancel = ttk.Button(btns, text=t("cancel"), command=self.root.destroy)
        self.cancel.pack(side="right", padx=(0, 6))

    def dark_titlebar(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
            self.root.withdraw()
            self.root.deiconify()
        except Exception:
            pass

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.dir.get())
        if d:
            d = os.path.normpath(d)
            if os.path.basename(d).lower() != "terrariaautofish":
                d = os.path.join(d, "TerrariaAutoFish")
            self.dir.set(d)

    def install(self):
        self.go.state(["disabled"])
        self.msg.config(text=t("working"), fg=MUTED)
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            target = sc.install(payload(), self.dir.get(), VERSION, self.desktop.get(), self.start.get())
        except PermissionError:
            self.root.after(0, lambda: self.finish(t("busy") % self.action, RED, False))
            return
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: self.finish(t("error") % err, RED, False))
            return
        if self.launch.get():
            subprocess.Popen([target], cwd=os.path.dirname(target), close_fds=True)
        self.root.after(0, lambda: self.finish(t("done"), GREEN, True))

    def finish(self, text, color, ok):
        self.msg.config(text=text, fg=color)
        if ok:
            self.go.pack_forget()
            self.cancel.config(text=t("close"))
        else:
            self.go.state(["!disabled"])

    def run(self):
        self.root.mainloop()


def main():
    args = sys.argv[1:]
    if "--silent" in args:          # для проверки сборки: без окна, ярлыков и записи в Windows
        d = args[args.index("--dir") + 1]
        sc.install(payload(), d, VERSION, desktop=False, start_menu=False, add_to_windows=False)
        return
    Setup().run()


if __name__ == "__main__":
    main()
