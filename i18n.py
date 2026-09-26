"""
Языки программы: русский (как в коде) и английский.
tr("русская строка") возвращает перевод на текущий язык.
"""
import ctypes

LANG = "ru"


def system_lang():
    """Язык Windows: русский, украинский, белорусский, казахский -> ru, остальные -> en."""
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return "ru" if primary in (0x19, 0x22, 0x23, 0x3F) else "en"
    except Exception:
        return "en"


def set_lang(code):
    """code: "ru", "en" или "auto" (как в Windows)."""
    global LANG
    LANG = system_lang() if code in (None, "", "auto") else code


def tr(text):
    return EN.get(text, text) if LANG == "en" else text


EN = {
    # --- консольная версия
    "  1) Возьмите удочку, наживка в инвентаре, поплавок не заброшен.":
        "  1) Hold the fishing rod, bait in the inventory, bobber not cast.",
    "  2) Наведите курсор на воду (в 5+ блоках от персонажа) и нажмите %s.":
        "  2) Point the cursor at the water (5+ tiles from the character) and press %s.",
    "  3) Программа забросит. Наведите курсор на поплавок и снова нажмите %s.":
        "  3) The program casts. Point the cursor at the bobber and press %s again.",
    "  4) Дальше всё само. %s — пауза / продолжить с теми же точками.":
        "  4) The rest is automatic. %s — pause / resume with the same points.",
    "  4) Увидели поклёвку — кликните сами. Сделайте так 5–10 раз.":
        "  4) When you see a bite, click yourself. Do this 5–10 times.",
    "  %s — выбрать новые точки.": "  %s — choose new points.",
    "  %s — выход.": "  %s — exit.",
    "  [DEBUG: картинки в папке debug]": "  [DEBUG: pictures in the debug folder]",
    "Terraria AutoFish готов.%s": "Terraria AutoFish is ready.%s",
    "Terraria AutoFish — РЕЖИМ ЗАПИСИ (забрасывает программа, подсекаете вы).":
        "Terraria AutoFish — RECORD MODE (the program casts, you hook).",
    "Выход. Подсечек за сессию: %d": "Exit. Hooks this session: %d",
    "Автоматическая рыбалка для Terraria": "Automatic fishing for Terraria",
    "печатать замеры и сохранять картинки": "print measurements and save pictures",
    "режим записи: подсекаете вы, программа записывает": "record mode: you hook, the program records",
    "Zoom в игре (1.0 = 100%%, 2.0 = 200%%)": "in-game Zoom (1.0 = 100%%, 2.0 = 200%%)",
    "Работает только в Windows.": "Works on Windows only.",

    # --- состояния и подсказки
    "Готов": "Ready",
    "Заброс": "Casting",
    "Ищу поплавок": "Looking for the bobber",
    "Отметьте поплавок": "Mark the bobber",
    "Жду поклёвку": "Waiting for a bite",
    "Поклёвка!": "Bite!",
    "Пауза": "Paused",
    "Подсекайте сами": "Hook it yourself",
    "Подсекаю…": "Hooking…",
    "Нужно окно Terraria": "Terraria window needed",
    "Выберите новые точки": "Choose new points",
    "Мышь не трогайте": "Don't touch the mouse",
    "Мышь не трогайте. %s — пауза": "Don't touch the mouse. %s — pause",
    "Мышь не трогайте. HOME — пауза": "Don't touch the mouse. HOME — pause",
    "Наведите курсор на воду в игре и нажмите %s": "Point the cursor at the water in the game and press %s",
    "Наведите курсор на поплавок в игре и нажмите %s": "Point the cursor at the bobber in the game and press %s",
    "Точки сохранены. В игре: %s — продолжить.%s": "Points saved. In the game: %s — resume.%s",
    " %s — выбрать новые": " %s — choose new ones",
    "Переключитесь в игру и нажмите %s": "Switch to the game and press %s",
    "Клюнуло — кликните мышью (не наводя на поплавок)": "A bite — click the mouse (not over the bobber)",
    "На обычном месте его нет — ищу вокруг отметки": "It's not in the usual place — searching around the mark",
    "Отметка у края окна. Наведите на поплавок и нажмите %s ещё раз":
        "The mark is at the window edge. Point at the bobber and press %s again",
    "Рядом с курсором нет поплавка. Наведите прямо на него и нажмите %s":
        "No bobber near the cursor. Point right at it and press %s",
    "Переключитесь в игру и наведите курсор на воду, куда забрасывать":
        "Switch to the game and point the cursor at the water where to cast",
    "Переключитесь в игру — продолжу с прежними точками": "Switch to the game — I'll resume with the same points",
    "Старт через %d…": "Starting in %d…",
    "Продолжаю через %d…": "Resuming in %d…",

    # --- журнал
    "Сначала переключитесь в окно Terraria.": "Switch to the Terraria window first.",
    "Продолжаю: точка заброса и поплавок прежние.": "Resuming: same cast point and bobber.",
    "Старт. Точка заброса: %s.%s": "Start. Cast point: %s.%s",
    " Подсекаете вы.": " You hook.",
    "Точки сброшены. Наведите курсор на воду и нажмите %s.":
        "Points cleared. Point the cursor at the water and press %s.",
    "Пауза: ": "Paused: ",
    "Пауза (по вашей команде).": "Paused (by your command).",
    "Пауза (из окна программы).": "Paused (from the program window).",
    "Пауза: выбираем новые точки.": "Paused: choosing new points.",
    "Рыбалка на паузе": "Fishing paused",
    "окно Terraria не активно": "the Terraria window is not active",
    "не получается %d раз подряд. Нет наживки?": "failed %d times in a row. Out of bait?",
    "ошибка": "error",
    "Ошибка": "Error",
    "Ошибка: %r": "Error: %r",
    ">>> Наведите курсор на ПОПЛАВОК и нажмите %s.": ">>> Point the cursor at the BOBBER and press %s.",
    "Отметка слишком близко к краю окна — попробуйте ещё раз.": "The mark is too close to the window edge — try again.",
    "Рядом с курсором не видно поплавка — наведите точнее, прямо на него.":
        "No bobber visible near the cursor — point more precisely, right at it.",
    "Поплавок запомнен: %s. Дальше — автоматически.": "Bobber remembered: %s. The rest is automatic.",
    "Поплавок: %s, непохожесть %.0f, пятно поплавка: %s%s": "Bobber: %s, difference %.0f, bobber blob: %s%s",
    "есть": "yes",
    "нет": "no",
    " (широкий поиск)": " (wide search)",
    "Поплавка нет на обычном месте — ищу шире вокруг отметки…":
        "The bobber is not in the usual place — searching wider around the mark…",
    "Нашёл поплавок в стороне %s — теперь ищу его там.": "Found the bobber off to the side %s — will look there now.",
    "Нашёл поплавок.": "Found the bobber.",
    "Пауза: окно Terraria не активно. Вернитесь в игру — продолжу сам.":
        "Paused: the Terraria window is not active. Return to the game — I'll resume by myself.",
    "Вернитесь в игру — продолжу сам через %d с": "Return to the game — I'll resume by myself in %d s",
    "Вы вернулись в игру — продолжаю.": "You're back in the game — resuming.",
    "Не получается %d раз подряд — попробую снова через %d с (попытка %d из %d).":
        "Failed %d times in a row — will try again in %d s (attempt %d of %d).",
    "Восстанавливаюсь…": "Recovering…",
    "Попробую снова через %d с": "Will try again in %d s",
    "Попробую продолжить через 5 с.": "Will try to continue in 5 s.",
    "зелье рыбалки": "fishing potion",
    "ящичное зелье": "crate potion",
    "Выпил: %s.": "Drank: %s.",
    "Не вижу баффа «%s» и после быстрого баффа — кончились зелья?":
        "Still no “%s” buff after Quick Buff — out of potions?",
    "Зелья": "Potions",
    "Не получается выпить: %s. Кончились зелья?": "Can't drink: %s. Out of potions?",
    "Поплавок уже в воде — продолжаю следить за ним.": "The bobber is already in the water — continuing to watch it.",
    "Точки с прошлого запуска загружены. %s — продолжить.": "Points from the last run loaded. %s — resume.",
    "Поплавок не найден (непохожесть %.0f).": "Bobber not found (difference %.0f).",
    "Поплавок почти не виден (%d пикс.).": "Bobber barely visible (%d px).",
    "Поплавок у края окна — перезаброс.": "Bobber at the window edge — recasting.",
    "Нет поклёвки %d с — перезаброс.": "No bite for %d s — recasting.",
    "Поклёвка (%s)! Подсекаю. Подсечек: %d (ждали %.1f с)": "Bite (%s)! Hooking. Hooks: %d (waited %.1f s)",
    "видно %d%% поплавка": "%d%% of the bobber visible",
    "видно 31% поплавка": "31% of the bobber visible",
    "  видно поплавка: %d (обычно %.0f, порог %.0f)": "  bobber visible: %d (usually %.0f, threshold %.0f)",
    "Ждите поклёвку и подсекайте сами (курсор к поплавку не подводите).":
        "Wait for a bite and hook yourself (keep the cursor away from the bobber).",
    "Автокалибровка: подсекаю, когда видно меньше %d%% поплавка (по %d забросам).":
        "Auto-calibration: hooking when less than %d%% of the bobber is visible (from %d casts).",
    "Клавиши управления и «новые точки» должны быть разными.": "The control and “new points” keys must be different.",
    "Режим изменён — начните заново.": "Mode changed — start again.",

    # --- режим записи
    "Подсечка №%d через %.1f с — слишком рано, программа ещё делала замер (%.1f с).":
        "Hook #%d after %.1f s — too early, the program was still measuring (%.1f s).",
    "видно от %d%% до %d%% поплавка": "%d%% to %d%% of the bobber visible",
    "нет данных": "no data",
    "НЕ сработал бы": "would NOT have triggered",
    "сработал бы РАНЬШЕ, на %.1f с (%s) — ложное срабатывание?":
        "would have triggered EARLIER, at %.1f s (%s) — false trigger?",
    "сработал бы на %.2f с (%s) — верно": "would have triggered at %.2f s (%s) — correct",
    "Подсечка №%d через %.1f с после заброса (обычно видно %.0f пикс. поплавка, порог %d%%)":
        "Hook #%d %.1f s after the cast (usually %.0f px of the bobber visible, threshold %d%%)",
    "  Спокойно (до последней секунды): ": "  Calm (before the last second): ",
    "  Последняя секунда перед подсечкой: ": "  Last second before the hook: ",
    "  Автомат: ": "  Automatic: ",
    "  Сохранено: record/%03d.txt и record/%03d_kadry.png": "  Saved: record/%03d.txt and record/%03d_kadry.png",
    "\n\nt, видно пикселей, обычно\n": "\n\nt, visible pixels, usual\n",

    # --- окно программы
    " Рыбалка ": " Fishing ",
    " Настройки ": " Settings ",
    "▶ Старт (5 с)": "▶ Start (5 s)",
    "▶ Продолжить (5 с)": "▶ Resume (5 s)",
    "⏸ Пауза": "⏸ Pause",
    "↺ Новые точки": "↺ New points",
    "Папка": "Folder",
    "подсечек": "hooks",
    "забросов": "casts",
    "в час": "per hour",
    "в работе": "running",
    "Подсечек: %d": "Hooks: %d",
    "Подсечек: 0": "Hooks: 0",
    "Неудачных забросов подряд: %d из %d": "Failed casts in a row: %d of %d",
    "Видно поплавка над водой (красная черта — порог)": "Bobber visible above water (red line — threshold)",
    "Жду поклёвку: %d с из %d · порог %d%%%s": "Waiting for a bite: %d s of %d · threshold %d%%%s",
    " (авто)": " (auto)",
    "ждём замер…": "measuring…",
    "вспышка — пропускаю": "flash — skipping",
    " запомнен": " remembered",
    "поплавок\nне отмечен": "bobber\nnot marked",
    "поплавок не отмечен": "bobber not marked",
    "Подсечка №%d (ждали %.0f с)": "Hook #%d (waited %.0f s)",
    "Так выглядят уведомления программы": "This is what the program's notifications look like",

    # --- настройки
    "Клавиша: старт, пауза, продолжить": "Key: start, pause, resume",
    "Клавиша: выбрать новые точки": "Key: choose new points",
    "Масштаб (Zoom) — как в игре": "Scale (Zoom) — same as in the game",
    "Чувствительность": "Sensitivity",
    "Подсекать, когда видно меньше этой доли поплавка. Выше — раньше, но чаще зря":
        "Hook when less than this share of the bobber is visible. Higher — earlier, but more false hooks",
    "Автокалибровка: порог подбирается сам по вашей воде и погоде":
        "Auto-calibration: the threshold adapts to your water and weather",
    "Выключена — порог берётся с ползунка": "Off — the threshold comes from the slider",
    "Учусь: нужно ещё забросов — %d (пока порог с ползунка)":
        "Learning: %d more casts needed (using the slider for now)",
    "Сейчас порог %d%% (подобран по %d забросам)": "Current threshold %d%% (tuned from %d casts)",
    "Ждать поклёвку, сек": "Wait for a bite, s",
    "Потом вытащить и забросить заново": "Then reel in and cast again",
    "Окошко поверх игры (перетаскивается мышью)": "Small window over the game (drag with the mouse)",
    "Уведомления Windows: пауза, нет наживки, ошибки": "Windows notifications: pause, out of bait, errors",
    "Уведомление о каждой подсечке": "Notification for every hook",
    "Звуки: старт, отметка, пауза": "Sounds: start, mark, pause",
    "Звук при подсечке": "Sound on hook",
    "Сохранять отладочные картинки (папка debug)": "Save debug pictures (debug folder)",
    "Режим записи: подсекаю я сам": "Record mode: I hook myself",
    "Проверить уведомление": "Test notification",

    # --- вкладка «Автоматика»
    " Автоматика ": " Automation ",
    "Если что-то пошло не так": "If something goes wrong",
    "Не сдаваться: после сбоев пробовать снова через 10, 30, 60 с":
        "Don't give up: after failures try again in 10, 30, 60 s",
    "Сам продолжать, когда я вернусь в игру из другого окна":
        "Resume by itself when I return to the game from another window",
    "Следить за баффами и пить зелья, когда бафф закончился": "Watch buffs and drink potions when a buff ends",
    "Зелье рыбалки (бафф «Рыбалка»)": "Fishing Potion (“Fishing” buff)",
    "Ящичное зелье (бафф «Ящики»)": "Crate Potion (“Crate” buff)",
    "Клавиша быстрого баффа (как в игре)": "Quick Buff key (as in the game)",
    "Быстрый бафф выпивает все зелья-баффы из инвентаря, чьих баффов сейчас нет, и не тратит зелья, если бафф ещё идёт. Держите в инвентаре только нужные зелья.":
        "Quick Buff drinks every buff potion in the inventory whose buff is not active, and doesn't waste potions "
        "while a buff is still active. Keep only the potions you need in the inventory.",
    "Проверить баффы сейчас": "Check buffs now",
    "Игра должна быть видна на экране (окно программы не должно её закрывать).":
        "The game must be visible on the screen (not covered by the program window).",
    "рыбалки": "fishing",
    "ящиков": "crate",
    "Зелья: ": "Potions: ",
    "Зелья: не слежу (вкладка «Автоматика»)": "Potions: not watching (Automation tab)",
    "Зелья: проверю при забросе": "Potions: will check on the next cast",
    "Проверяю…": "Checking…",
    "Окно Terraria не найдено — игра запущена?": "Terraria window not found — is the game running?",
    "Не выбрано ни одного зелья.": "No potion selected.",
    "Удалить Terraria AutoFish с этого компьютера?": "Remove Terraria AutoFish from this computer?",
    "Удалить также настройки и сохранённые точки?": "Also remove the settings and saved points?",
    "Terraria AutoFish удалена.": "Terraria AutoFish has been removed.",
    # удочка и поплавки с Вики
    "В руках был другой предмет (слот %d) — взял удочку (слот %s).":
        "Another item was selected (slot %d) — switched to the fishing rod (slot %s).",
    "Нажал %s, чтобы взять удочку, но слот не сменился.": "Pressed %s to take the fishing rod, but the slot didn't change.",
    "Не получается взять удочку клавишей — больше не переключаю. Возьмите удочку в руки сами.":
        "Can't switch to the fishing rod with a key — not trying anymore. Please select the rod yourself.",
    "Не получается взять удочку. Возьмите её в руки сами.": "Can't switch to the fishing rod. Please select it yourself.",
    "Поплавок нашёлся сам: %s (совпадение %.2f), %s. Дальше — автоматически.":
        "Found the bobber by myself: %s (match %.2f), %s. Automatic from now on.",
    "Похожее на поплавок: %s, совпадение %.2f — мало.": "Something like a bobber: %s, match %.2f — too low.",
    "Сам брать удочку в руки (если выбран другой слот хотбара)":
        "Select the fishing rod automatically (if another hotbar slot is selected)",
    "Сам находить поплавок после первого заброса (по картинкам с Terraria Wiki)":
        "Find the bobber automatically after the first cast (using Terraria Wiki images)",
    "Сам поплавок не нашёл — покажите его, пожалуйста.": "Couldn't find the bobber by myself — please show it to me.",
    "Удочка": "Fishing rod",
    "Удочка и поплавок": "Fishing rod and bobber",
    "Удочка теперь в слоте %d.": "The fishing rod is now in slot %d.",
    "Удочка: %s, слот %d.": "Fishing rod: %s, slot %d.",
    "Удочку по картинке не узнал — считаю, что она в слоте %d (он был выбран).":
        "Didn't recognize the fishing rod — assuming it's in slot %d (the selected one).",
    "Узнал поплавок по картинке (%s, совпадение %.2f).": "Recognized the bobber by its image (%s, match %.2f).",
    "Это %s.": "It's a %s.",
    "поплавок: %s": "bobber: %s",
    "Удочка: слот %d": "Rod: slot %d",
}
