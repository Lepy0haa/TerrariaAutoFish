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
    "Попробую продолжить через 2 с.": "Will try to continue in 2 s.",
    "Автокалибровка по этому забросу: подсекаю, когда видно меньше %d%% поплавка.":
        "Auto-calibration from this cast: hooking when less than %d%% of the bobber is visible.",
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
    "Не сдаваться: после сбоев пробовать снова каждые 2 с, без остановки":
        "Don't give up: after failures try again every 2 s, without stopping",
    "Не получается %d раз подряд — попробую снова через %d с (круг %d).":
        "Failed %d times in a row — will try again in %d s (round %d).",
    "Уже %d кругов неудачных забросов — загляните в игру.": "%d rounds of failed casts already — take a look at the game.",
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
    "Не получается взять удочку клавишей — пару минут не переключаю. Возьмите удочку в руки сами.":
        "Can't switch to the fishing rod with a key — not trying for a couple of minutes. Please select the rod yourself.",
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
    " (задан)": " (set)",
    "Снимок хотбара": "Hotbar snapshot",
    "Переключитесь в игру — снимок через 3 с…": "Switch to the game — snapshot in 3 s…",
    "Не удалось сохранить снимок: %r": "Couldn't save the snapshot: %r",
    "Сохранено: %s. Выбранный (жёлтый) слот не виден — закройте инвентарь и повторите.":
        "Saved: %s. The selected (yellow) slot isn't visible — close the inventory and try again.",
    "Сохранено: %s. Выбран слот %d.": "Saved: %s. Selected slot: %d.",
    "Удочка узнаётся в слоте %d (%.2f).": "The fishing rod is recognized in slot %d (%.2f).",
    "Удочку уверенно не узнал.": "Couldn't recognize the fishing rod with confidence.",
    "Собрать отчёт": "Collect a report",
    # вкладка «Без присмотра», зелья, здоровье, наживка
    " Без присмотра ": " Unattended ",
    "Защита": "Protection",
    "Персонаж получает урон — вытащить поплавок и встать на паузу":
        "The character takes damage — reel in and pause",
    "Смотрит на сердечки здоровья справа вверху: стало меньше — сообщит и остановится.":
        "Watches the health hearts at the top right: fewer hearts — notifies and stops.",
    "Следить за наживкой": "Watch the bait",
    "Меньше 10 — предупредит, кончилась — сразу остановится (без повторных попыток).":
        "Less than 10 — warns; none left — stops right away (without retries).",
    "Когда закончить": "When to finish",
    "Остановиться через, мин": "Stop after, min",
    "…или после стольких подсечек": "…or after this many hooks",
    "0 — не останавливаться. Время и подсечки — как в статистике на вкладке «Рыбалка».":
        "0 — don't stop. Time and hooks are as in the stats on the Fishing tab.",
    "После такой остановки выключить компьютер": "Shut down the computer after such a stop",
    "Через 60 с после остановки; отменить можно кнопкой ниже.": "60 s after the stop; can be cancelled with the button below.",
    "Отменить выключение": "Cancel shutdown",
    "Выключение компьютера": "Computer shutdown",
    "Выключение компьютера отменено.": "Computer shutdown cancelled.",
    "Не получилось отменить выключение: %r": "Couldn't cancel the shutdown: %r",
    "Не получилось запланировать выключение: %r": "Couldn't schedule the shutdown: %r",
    "Компьютер выключится через %d с. Отменить — кнопка в окне программы.":
        "The computer will shut down in %d s. To cancel — the button in the program window.",
    "Рыбалка закончена. Компьютер выключится через %d с.": "Fishing finished. The computer will shut down in %d s.",
    "Рыбалка закончена: %s.": "Fishing finished: %s.",
    "прошло %d мин": "%d min passed",
    "сделано %d подсечек": "%d hooks done",
    "Персонаж получает урон (здоровья меньше на %d%%) — вытащил поплавок и поставил на паузу.":
        "The character is taking damage (%d%% less health) — reeled in and paused.",
    "персонаж получает урон": "the character is taking damage",
    "Наживка": "Bait",
    # задание рыбака, надпись сонара
    "(нет задания)": "(no quest)",
    "Задание рыбака": "Angler quest",
    "надпись сонара": "sonar text",
    "Поймал рыбу для задания рыбака: %s!": "Caught the fish for the Angler quest: %s!",
    "Поймана %s — отнесите её рыбаку.": "%s is caught — bring it to the Angler.",
    "Пауза: рыба для задания рыбака поймана.": "Pause: the fish for the Angler quest is caught.",
    # полный инвентарь, отчёт об улове
    "инвентарь полон": "inventory is full",
    "Улов перестал подбираться %d раз подряд — похоже, инвентарь полон.":
        "The catch wasn't picked up %d times in a row — the inventory seems to be full.",
    "Подсечек: %d · узнано: %d · не узнано: %d · пропущено сонаром: %d":
        "Hooks: %d · recognized: %d · not recognized: %d · skipped by sonar: %d",
    " · в час: %.0f": " · per hour: %.0f",
    "Отчёт об улове": "Catch report",
    "Улов": "Catch",
    "Сколько": "Count",
    "Где ловится": "Where it's caught",
    "Закрыть": "Close",
    "Сохранить CSV": "Save CSV",
    "Улов узнаётся по надписи о подборе над персонажем после каждой подсечки.":
        "The catch is recognized by the pickup text above the character after every hook.",
    "пока ничего не узнано": "nothing recognized yet",
    "Отчёт об улове сохранён: %s": "Catch report saved: %s",
    "Не удалось сохранить отчёт об улове: %r": "Couldn't save the catch report: %r",
    "Наживка: мало — предупредить, кончилась — остановиться": "Bait: low — warn, none left — stop",
    "Улов перестал подбираться (инвентарь полон) — остановиться": "The catch isn't picked up (inventory full) — stop",
    "Остановиться через, мин (0 — нет)": "Stop after, min (0 — never)",
    "…или после стольких подсечек (0 — нет)": "…or after this many hooks (0 — never)",
    "Потом выключить компьютер (через 60 с)": "Then shut down the computer (in 60 s)",
    # обновления, трей, мастер первого запуска
    "Вышла новая версия %s — %s": "New version %s is out — %s",
    "Вышла новая версия %s. Обновить — кнопкой на вкладке «Настройки».":
        "New version %s is out. Update it with the button on the Settings tab.",
    "Показать окно": "Show window",
    "Пауза / продолжить": "Pause / resume",
    "Как начать": "Getting started",
    "Выход": "Exit",
    "Обновления": "Updates",
    "Не удалось проверить обновления: %s": "Couldn't check for updates: %s",
    "У вас последняя версия (%s).": "You have the latest version (%s).",
    "доступна %s": "%s available",
    "Добро пожаловать!": "Welcome!",
    "Terraria AutoFish рыбачит за вас: следит за поплавком, подсекает, когда клюёт, и забрасывает снова. Работает только по картинке на экране и нажатиям — в игру и её файлы не лезет.\n\nЧетыре коротких шага — и можно начинать.":
        "Terraria AutoFish fishes for you: it watches the bobber, hooks when a fish bites and casts again. "
        "It works only with what is on the screen and key presses — it doesn't touch the game or its files.\n\n"
        "Four short steps — and you can start.",
    "1. Настройте игру": "1. Set up the game",
    "• Режим экрана — «Оконный» или «Без рамки» (в полноэкранном программа не видит игру).\n• «Масштаб» (Zoom) в настройках игры — такой же, как на вкладке «Настройки» программы (по умолчанию 100 %).\n• Во время рыбалки окно игры не закрывайте другими окнами.":
        "• Display mode — Windowed or Borderless (in fullscreen the program can't see the game).\n"
        "• Zoom in the game settings — the same as on the program's Settings tab (100% by default).\n"
        "• While fishing, don't cover the game window with other windows.",
    "2. Удочка, наживка, зелья": "2. Fishing rod, bait, potions",
    "• Возьмите удочку, наживка — в инвентаре. Удочку программа потом берёт в руки сама.\n• Зелья рыбалки, ящиков, сонара и спокойствия положите в хотбар — программа будет пить их сама (вкладка «Автоматика»).\n• С зельем сонара можно выбирать, что ловить в каждом биоме (вкладка «Улов»).":
        "• Hold the fishing rod, keep bait in the inventory. Later the program takes the rod in hand itself.\n"
        "• Put Fishing, Crate, Sonar and Calming potions into the hotbar — the program will drink them "
        "(Automation tab).\n"
        "• With the Sonar Potion you can choose what to catch in every biome (Catch tab).",
    "3. Старт": "3. Start",
    "• Наведите курсор на воду и нажмите %s — программа забросит и сама найдёт поплавок.\n• %s ещё раз — пауза, потом снова %s — продолжить с теми же точками.\n• %s — выбрать новое место.\n• Свёрнутая программа живёт в трее, рядом с часами.\n\nМышь во время рыбалки не трогайте. Удачного клёва!":
        "• Point at the water and press %s — the program casts and finds the bobber itself.\n"
        "• %s again — pause, then %s again — resume with the same points.\n"
        "• %s — choose a new spot.\n"
        "• When minimized, the program lives in the tray, next to the clock.\n\n"
        "Don't touch the mouse while fishing. Good luck!",
    "Далее": "Next",
    "Назад": "Back",
    "Готово": "Done",
    # улов по сонару
    " Улов ": " Catch ",
    " (хардмод)": " (hardmode)",
    "Авто (по улову)": "Auto (by the catch)",
    "Всё": "All",
    "Ничего": "None",
    "Выбирать улов по зелью сонара": "Choose the catch using the Sonar Potion",
    "Где рыбачу": "Fishing in",
    "Список": "List",
    "Зелье сонара пишет над поплавком, что клюнуло. Программа читает надпись и подсекает только отмеченное, остальное пропускает. Не прочитала — подсекает.":
        "The Sonar Potion shows above the bobber what is biting. The program reads it and hooks only what is "
        "checked, skipping the rest. If it can't read it — it hooks.",
    "Нет данных об улове.": "No catch data.",
    "Пропущено по сонару: %d": "Skipped by sonar: %d",
    "Распознавание текста Windows недоступно — выбор улова по сонару не работает.":
        "Windows text recognition is not available — choosing the catch by sonar doesn't work.",
    "Сонар: «%s» — не узнал предмет, подсекаю.": "Sonar: «%s» — unknown item, hooking.",
    "Сонар: клюёт «%s» — не отмечено, пропускаю.": "Sonar: «%s» is biting — not checked, skipping.",
    "биом: %s": "biome: %s",
    "Нет баффа сонара — выбирать улов не по чему, подсекаю всё. Выпейте зелье сонара.":
        "No Sonar buff — nothing to choose the catch by, hooking everything. Drink a Sonar Potion.",
    "Нет баффа сонара — выбор улова не работает.": "No Sonar buff — choosing the catch doesn't work.",
    "Поймал: %s.": "Caught: %s.",
    "Сонар: похоже на «%s», но не уверен — подсекаю.": "Sonar: looks like «%s», but not sure — hooking.",
    # зелья из хотбара
    "%s — слот %d": "%s — slot %d",
    "Быстрый бафф выпивает все зелья-баффы из инвентаря, чьих баффов сейчас нет. Держите в инвентаре только нужные зелья.":
        "Quick Buff drinks every buff potion in the inventory whose buff is not active. Keep only the potions you need.",
    "В хотбаре зелий не нашёл.": "No potions found in the hotbar.",
    "В хотбаре: ": "In the hotbar: ",
    "Из хотбара: программа находит нужное зелье в хотбаре, берёт его цифрой слота, пьёт и снова берёт удочку. Положите зелья в хотбар.":
        "From the hotbar: the program finds the needed potion in the hotbar, selects it with the slot's number "
        "key, drinks it and takes the fishing rod again. Put the potions into the hotbar.",
    "Нажал %s, чтобы взять зелье, но слот не сменился.": "Pressed %s to take the potion, but the slot didn't change.",
    "Не вижу баффа «%s» после зелья из хотбара — зелье кончилось или не выпилось.":
        "No «%s» buff after the potion from the hotbar — out of potions or it wasn't drunk.",
    "Пить": "Drink",
    "Хотбар не виден (открыт инвентарь?) — зелья из хотбара не выпить.":
        "The hotbar isn't visible (inventory open?) — can't drink potions from the hotbar.",
    "быстрым баффом": "with Quick Buff",
    "из хотбара": "from the hotbar",
    "клавиша быстрого баффа": "Quick Buff key",
    "резкий нырок, видно %d%% поплавка": "sharp dip, %d%% of the bobber visible",
    "Наживки осталось меньше 10.": "Less than 10 bait left.",
    "кончилась наживка (на удочке нет числа наживки)": "out of bait (no bait count on the fishing rod)",
    "наживка: %s": "bait: %s",
    "меньше 10": "less than 10",
    "Рыбалка": "Fishing",
    "Ящики": "Crate",
    "Сонар": "Sonar",
    "Спокойствие": "Calm",
    "сонара": "sonar",
    "спокойствия": "calm",
    "зелье сонара": "sonar potion",
    "успокоительное зелье": "calming potion",
    "запуск": "start",
    "Не удалось собрать отчёт: %r": "Couldn't collect the report: %r",
    "Отчёт сохранён: %s": "Report saved: %s",
    "Если в руках не удочка — возьмите её, нажмите %s и начните заново (%s на воде). Слот удочки запомню "
    "сам или задайте его на вкладке «Автоматика».":
        "If you're not holding the fishing rod, select it, press %s and start again (%s on the water). "
        "I'll remember the rod slot, or you can set it on the Automation tab.",
    "Слот удочки": "Fishing rod slot",
    "Авто (запомню)": "Auto (remember)",
    "Запомнил: удочка в слоте %d. Если в руках окажется другой предмет — возьму её сам.":
        "Remembered: the fishing rod is in slot %d. If another item gets selected, I'll switch back to it.",
    "Похоже, удочка в слоте %d (по картинке) — беру её.": "The fishing rod seems to be in slot %d (by its image) — taking it.",
    "Переключился на слот %d, но поплавка нет — может, удочка теперь в другом слоте? "
    "Забыл этот слот: возьмите удочку в руки, запомню заново.":
        "Switched to slot %d, but there's no bobber — maybe the rod is in another slot now? "
        "Forgot this slot: select the rod yourself and I'll remember it again.",
    "Над лавой надписи дрожат и двоятся — их трудно прочитать. Выключите в игре: "
    "Настройки → Видео → «Искажение от тепла».":
        "Above lava the text shimmers and doubles, so it's hard to read. Turn it off in the game: "
        "Settings → Video → \"Heat Distortion\".",
    "Поймал: %s (ещё один — к надписи прибавилось число).":
        "Caught: %s (one more — the number on the text went up).",
    "Нет в хотбаре: %s — положите зелья в хотбар.": "Not in the hotbar: %s — put the potions into the hotbar.",
    "Нет в хотбаре: %s.": "Not in the hotbar: %s.",
    "Напоминать, если нужного зелья нет в хотбаре (не чаще раза в 10 мин)":
        "Remind me when a needed potion isn't in the hotbar (at most every 10 min)",
    # --- окошко поверх игры: режим работы
    "Режим записи: подсекаете вы, программа записывает": "Record mode: you hook, the program records",
    "биом определяю": "detecting the biome",
    "Улов: только отмеченное (сонар) · %s": "Catch: only checked (sonar) · %s",
    "Улов: всё подряд": "Catch: everything",
    "Задание рыбака: %s": "Angler quest: %s",
    "Зелья: %s (%s)": "Potions: %s (%s)",
    "не выбраны": "none selected",
    "  нет в хотбаре: %s": "  not in the hotbar: %s",
    "урон": "damage",
    "наживка": "bait",
    "полный инвентарь": "full inventory",
    "Слежу: %s": "Watching: %s",
    "через %d мин": "in %d min",
    "после %d подсечек": "after %d hooks",
    " или ": " or ",
    ", потом выключу ПК": ", then shut down the PC",
    "Стоп: %s": "Stop: %s",
    "Последний улов: %s": "Last catch: %s",
    "Картинка сдвинулась на %+d, %+d пикс. — наверное, персонажа сдвинуло. Переношу точку "
    "заброса и поплавка туда же.":
        "The picture moved by %+d, %+d px — the character was probably pushed. Moving the cast point "
        "and the bobber mark along.",
    "Похоже, Zoom в игре %d%% (в настройках было %d%%) — поставил %d%%.":
        "Looks like the game's Zoom is %d%% (settings had %d%%) — set it to %d%%.",
    " (хватит на ~%s)": " (enough for ~%s)",
    "меньше минуты": "less than a minute",
    "%d мин": "%d min",
    "%d ч %d мин": "%d h %d min",
    "Наживка: %s": "Bait: %s",
    " · дней с рыбалкой: %d": " · days of fishing: %d",
    "За": "For",
    "эту рыбалку": "this session",
    "сегодня": "today",
    "7 дней": "7 days",
    "всё время": "all time",
    "Обновить до %s": "Update to %s",
    "Скачать и установить версию %s?\n\nПрограмма закроется, а установщик обновит её (настройки и точки сохранятся).": "Download and install version %s?\n\nThe program will close and the installer will update it (settings and points are kept).",
    "Обновление — рыбалка остановлена.": "Updating — fishing stopped.",
    "Скачиваю версию %s…": "Downloading version %s…",
    "Не удалось скачать обновление: %s": "Couldn't download the update: %s",
    "Не удалось запустить установщик: %r": "Couldn't start the installer: %r",
    "Скачиваю… %d%%": "Downloading… %d%%",
    "Кровавая луна": "Blood Moon",
    "Продолжу сам в %s (или нажмите %s)": "I'll continue at %s (or press %s)",
    "Рыбалка на паузе — продолжу через %d мин.": "Fishing paused — I'll continue in %d min.",
    "Персонаж погиб во время события «%s» — рыбалка остановлена совсем.": "The character died during «%s» — fishing stopped completely.",
    "Персонаж погиб — рыбалка остановлена совсем.": "The character died — fishing stopped completely.",
    "Пауза: персонаж погиб.": "Paused: the character died.",
    "Персонаж погиб": "The character died",
    "Рыбалка остановлена. Начните заново: %s": "Fishing stopped. Start again: %s",
    "В чате: «%s» — продолжаю рыбалку.": "Chat: «%s» — continuing fishing.",
    "В чате: «%s» (%s) — вытащил поплавок, пережду %d мин и продолжу сам.": "Chat: «%s» (%s) — reeled in, waiting %d min, then I'll continue.",
    "Пауза: %s.": "Paused: %s.",
    "Событие «%s» должно было закончиться — продолжаю.": "«%s» should be over — continuing.",
    "события": "events",
    "смерть": "death",
    "События в чате (кровавая луна, вторжения, боссы) — переждать и продолжить": "Events in chat (Blood Moon, invasions, bosses) — wait them out and continue",
    "Персонаж погиб — остановить рыбалку совсем": "The character died — stop fishing completely",
    "Тыквенная луна": "Pumpkin Moon",
    "Морозная луна": "Frost Moon",
    "Солнечное затмение": "Solar Eclipse",
    "Этой ночью придёт босс": "A boss is coming tonight",
    "Армия гоблинов": "Goblin Army",
    "Пираты": "Pirates",
    "Ледяной легион": "Frost Legion",
    "Марсиане": "Martians",
    "Небесные существа": "Celestial creatures",
    "Босс": "Boss",
    "%d раза подряд без поклёвки — вернулся к исходному образцу и отметке поплавка.":
        "%d times in a row without a bite — went back to the original bobber image and mark.",
    "☕ Поддержать": "☕ Support",
    "☕ Поддержать автора": "☕ Support the author",
    "Поддержать автора": "Support the author",
    "Спасибо, что пользуетесь Terraria AutoFish!": "Thank you for using Terraria AutoFish!",
    "Программа бесплатная. Если она вам помогла, можно оставить автору «на чай» — это добровольно и ни на что в программе не влияет.": "The program is free. If it helped you, you can leave the author a tip — it's voluntary and changes nothing in the program.",
    'Диагностика': 'Diagnostics',
    'Диагностика: переключитесь в игру — проверка через 3 с…': 'Diagnostics: switch to the game — checking in 3 s…',
    'Ошибка диагностики: %r': 'Diagnostics error: %r',
    'Диагностика: всё в порядке.': 'Diagnostics: everything is fine.',
    'Диагностика: есть что исправить (%d).': 'Diagnostics: something to fix (%d).',
    'Сохранено: %s': 'Saved: %s',
    'Окно Terraria не найдено — запустите игру (режим «Оконный» или «Без рамки»).': 'Terraria window not found — start the game (Windowed or Borderless mode).',
    'Окно игры: %d×%d.': 'Game window: %d×%d.',
    'Окно игры %d×%d не активно — во время проверки переключитесь в игру.': 'The game window %d×%d is not active — switch to the game during the check.',
    'Хотбар не виден — закройте инвентарь, карту и меню.': "The hotbar isn't visible — close the inventory, map and menus.",
    'Хотбар виден: выбран слот %d, масштаб интерфейса %d%%.': 'Hotbar visible: slot %d selected, interface scale %d%%.',
    'Удочку в хотбаре уверенно не узнал — перед стартом возьмите её в руки (слот запомнится) или задайте слот на вкладке «Автоматика».': "Couldn't recognize the fishing rod in the hotbar — hold it when starting (the slot will be remembered) or set the slot on the Automation tab.",
    'Удочка в слоте %d, но наживки на ней нет — положите наживку в инвентарь.': 'The fishing rod is in slot %d, but it has no bait — put bait into the inventory.',
    'Удочка в слоте %d, наживка: %s.': 'Fishing rod in slot %d, bait: %s.',
    'Нет в хотбаре: %s — выпить не получится.': "Not in the hotbar: %s — can't drink it.",
    'Зелья в хотбаре: %s.': 'Potions in the hotbar: %s.',
    'Баффы сейчас: %s.': 'Buffs now: %s.',
    'Выбор улова по сонару включён, а баффа сонара нет — выпейте зелье сонара.': "Choosing the catch by sonar is on, but there's no Sonar buff — drink a Sonar Potion.",
    'Сердечки здоровья видны.': 'Health hearts are visible.',
    'Сердечки здоровья не видны (другой вид полоски здоровья?) — защита от урона и остановка после смерти не сработают. Сделайте снимок экрана и пришлите его вместе с отчётом.': "Health hearts aren't visible (another health display style?) — the damage guard and the stop after death won't work. Take a screenshot and send it with the report.",
    'Распознавание текста Windows: %s.': 'Windows text recognition: %s.',
    'Распознавание текста Windows: только %s — для русских надписей игры добавьте русский язык в Windows (Параметры → Время и язык).': "Windows text recognition: only %s — for the game's Russian texts add the Russian language in Windows (Settings → Time & language).",
    'Распознавание текста Windows недоступно — выбор улова по сонару, учёт улова и события в чате не работают.': "Windows text recognition isn't available — choosing the catch by sonar, counting the catch and chat events don't work.",
    'Названия предметов прочитаны из игры (%d).': 'Item names read from the game (%d).',
    'Названия из игры не прочитались — используются названия с Вики (часть улова может не узнаваться).': "Couldn't read the names from the game — Wiki names are used (some catches may not be recognized).",
    'Zoom в настройках программы: %d%% (узнаётся сам при первом автопоиске поплавка).': "Zoom in the program's settings: %d%% (recognized by itself on the first automatic bobber search).",
    'Точки рыбалки сохранены — HOME продолжит с ними.': 'Fishing points are saved — HOME continues with them.',
    'Точек пока нет: курсор на воду и HOME.': 'No points yet: cursor on the water and HOME.',
    '⚑ Что-то не так': "⚑ Something's wrong",
    'Не удалось сохранить: %r': "Couldn't save: %r",
    'Сохранил для разбора: %s — пришлите этот файл автору.': 'Saved for analysis: %s — send this file to the author.',
    "Чат: «%s» — %s.": "Chat: «%s» — %s.",
    "событие «%s»": "event «%s»",
    "не событие": "not an event",
    # --- подписи на двух языках сразу (выбор языка) — одинаковы в обоих
    "Авто / Auto": "Авто / Auto",
    "Русский": "Русский",
    "Язык / Language": "Язык / Language",
}
