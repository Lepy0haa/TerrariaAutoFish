"""
Мастер первого запуска: несколько коротких страниц — как настроить игру и начать рыбачить.
Открывается сам при первом запуске, потом — по F1 или из меню значка в трее.
"""
import tkinter as tk
from tkinter import ttk

from i18n import tr


def pages(key_start, key_reset):
    return [
        (tr("Добро пожаловать!"),
         tr("Terraria AutoFish рыбачит за вас: следит за поплавком, подсекает, когда клюёт, и забрасывает "
            "снова. Работает только по картинке на экране и нажатиям — в игру и её файлы не лезет.\n\n"
            "Четыре коротких шага — и можно начинать.")),
        (tr("1. Настройте игру"),
         tr("• Режим экрана — «Оконный» или «Без рамки» (в полноэкранном программа не видит игру).\n"
            "• «Масштаб» (Zoom) в настройках игры — такой же, как на вкладке «Настройки» программы "
            "(по умолчанию 100 %).\n"
            "• Во время рыбалки окно игры не закрывайте другими окнами.")),
        (tr("2. Удочка, наживка, зелья"),
         tr("• Возьмите удочку, наживка — в инвентаре. Удочку программа потом берёт в руки сама.\n"
            "• Зелья рыбалки, ящиков, сонара и спокойствия положите в хотбар — программа будет пить их "
            "сама (вкладка «Автоматика»).\n"
            "• С зельем сонара можно выбирать, что ловить в каждом биоме (вкладка «Улов»).")),
        (tr("3. Старт"),
         tr("• Наведите курсор на воду и нажмите %s — программа забросит и сама найдёт поплавок.\n"
            "• %s ещё раз — пауза, потом снова %s — продолжить с теми же точками.\n"
            "• %s — выбрать новое место.\n"
            "• Свёрнутая программа живёт в трее, рядом с часами.\n\n"
            "Мышь во время рыбалки не трогайте. Удачного клёва!") % (key_start, key_start, key_start, key_reset)),
    ]


class Wizard(tk.Toplevel):
    def __init__(self, master, colors, font, key_start, key_reset, on_done):
        super().__init__(master)
        self.C, self.font, self.on_done = colors, font, on_done
        self.pages = pages(key_start, key_reset)
        self.i = 0
        self.title(tr("Как начать"))
        self.configure(bg=self.C["bg"])
        self.resizable(False, False)
        self.transient(master)
        body = tk.Frame(self, bg=self.C["panel"], padx=16, pady=14)
        body.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.head = tk.Label(body, bg=self.C["panel"], fg=self.C["text"], font=(font, 12, "bold"), anchor="w")
        self.head.pack(fill="x")
        self.text = tk.Label(body, bg=self.C["panel"], fg=self.C["text"], font=(font, 9), justify="left",
                             anchor="nw", wraplength=380, height=9)
        self.text.pack(fill="both", expand=True, pady=(8, 0))
        bar = tk.Frame(self, bg=self.C["bg"])
        bar.pack(fill="x", padx=10, pady=10)
        self.dots = tk.Label(bar, bg=self.C["bg"], fg=self.C["muted"], font=(font, 9))
        self.dots.pack(side="left")
        self.next_btn = ttk.Button(bar, text=tr("Далее"), command=self.next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(bar, text=tr("Назад"), command=self.back)
        self.back_btn.pack(side="right", padx=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self.finish)
        self.bind("<Escape>", lambda e: self.finish())
        self.show()
        self.place_over(master)
        self.after(10, self.dark_titlebar)

    def dark_titlebar(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
        except Exception:
            pass

    def place_over(self, master):
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + 60
        self.geometry("+%d+%d" % (max(0, x), max(0, y)))

    def show(self):
        head, text = self.pages[self.i]
        self.head.config(text=head)
        self.text.config(text=text)
        self.dots.config(text="  ".join("●" if n == self.i else "○" for n in range(len(self.pages))))
        self.back_btn.state(["disabled"] if self.i == 0 else ["!disabled"])
        self.next_btn.config(text=tr("Готово") if self.i == len(self.pages) - 1 else tr("Далее"))

    def next(self):
        if self.i == len(self.pages) - 1:
            self.finish()
        else:
            self.i += 1
            self.show()

    def back(self):
        if self.i > 0:
            self.i -= 1
            self.show()

    def finish(self):
        self.destroy()
        self.on_done()
