"""
Диагностика: одна проверка всего, что нужно для рыбалки, — видна ли игра, хотбар, удочка и
наживка, зелья и баффы, сердечки здоровья, распознавание текста, названия из игры. На каждый пункт —
«в порядке» или что сделать.
"""
import os
import sys

from i18n import tr

OK, WARN, BAD = "ok", "warn", "bad"
MARK = {OK: "✓", WARN: "!", BAD: "✗"}


def _af():
    return sys.modules["autofish"]


def run(fisher, sct, hwnd, active):
    """[(состояние, текст)]. hwnd — окно игры (или None), active — активно ли оно сейчас."""
    A = _af()
    out = []
    if not hwnd:
        return [(BAD, tr("Окно Terraria не найдено — запустите игру (режим «Оконный» или «Без рамки»)."))]
    cl = A.client_rect(hwnd)
    w, h = cl[2] - cl[0], cl[3] - cl[1]
    out.append((OK if active else WARN,
                tr("Окно игры: %d×%d.") % (w, h) if active else
                tr("Окно игры %d×%d не активно — во время проверки переключитесь в игру.") % (w, h)))

    import hotbar
    frame = fisher.hotbar_frame(sct, cl)
    sel = hotbar.selected_slot(frame)
    if sel is None:
        out.append((BAD, tr("Хотбар не виден — закройте инвентарь, карту и меню.")))
    else:
        out.append((OK, tr("Хотбар виден: выбран слот %d, масштаб интерфейса %d%%.")
                    % ((sel[0] + 1) % 10, round(100 * sel[1]))))
        rod = fisher.rods.find(frame, A.ROD_HINT_MIN, A.ROD_HINT_MARGIN) if fisher.rods else None
        slot = rod[0] if rod else fisher.rod_target()
        if slot is None:
            out.append((WARN, tr("Удочку в хотбаре уверенно не узнал — перед стартом возьмите её в руки "
                                 "(слот запомнится) или задайте слот на вкладке «Автоматика».")))
        else:
            x0, y0, x1, y1, rel = hotbar.slot_boxes(*sel)[slot]
            cell = frame[max(0, y0):y1, max(0, x0):x1].astype("float64")
            count = fisher.digit_reader.read(cell, rel * sel[1]) if fisher.digit_reader else None
            digits = hotbar.bait_digits(cell, rel * sel[1])
            if not digits:
                out.append((BAD, tr("Удочка в слоте %d, но наживки на ней нет — положите наживку в инвентарь.")
                            % ((slot + 1) % 10)))
            else:
                bait = str(count) if count is not None else {1: tr("меньше 10"), 2: "10–99"}.get(digits, "100+")
                out.append((WARN if (count or 10) < 10 or digits == 1 else OK,
                            tr("Удочка в слоте %d, наживка: %s.") % ((slot + 1) % 10, bait)))
        if A.BUFFS_ON and fisher.potions is not None:
            want = [n for n in ("fishing", "crate", "sonar", "calm") if A.BUFF_WANT.get(n)]
            slots = fisher.potion_slots(frame)
            have = [n for n in want if n in slots]
            miss = [n for n in want if n not in slots]
            if want and A.BUFF_METHOD == "hotbar":
                if miss:
                    out.append((WARN, tr("Нет в хотбаре: %s — выпить не получится.")
                                % ", ".join(tr(A.BUFF_NAMES[n]) for n in miss)))
                if have:
                    out.append((OK, tr("Зелья в хотбаре: %s.") % ", ".join(
                        "%s (%d)" % (tr(A.BUFF_NAMES[n]), (slots[n] + 1) % 10) for n in have)))
    if fisher.buffs is not None:
        region = {"left": cl[0], "top": cl[1], "width": min(w, 900), "height": min(h, 360)}
        found = fisher.buffs.find(A.grab(sct, region))
        active_buffs = [n for n in sorted(found) if found[n] >= A.BUFF_THRESHOLD()]
        out.append((OK, tr("Баффы сейчас: %s.") % (", ".join(tr(A.BUFF_NAMES[n]) for n in active_buffs)
                                                   if active_buffs else tr("нет"))))
        if A.SONAR_FILTER and "sonar" not in active_buffs:
            out.append((WARN, tr("Выбор улова по сонару включён, а баффа сонара нет — выпейте зелье сонара.")))

    fisher.hp_band = None
    hp = fisher.hearts(sct, cl)
    out.append((OK, tr("Сердечки здоровья видны.")) if hp else
               (WARN, tr("Сердечки здоровья не видны (другой вид полоски здоровья?) — защита от урона и "
                         "остановка после смерти не сработают. Сделайте снимок экрана и пришлите его вместе "
                         "с отчётом.")))

    try:
        import ocr
        langs = ocr.available_languages()
    except Exception:
        langs = []
    if any(x.startswith("ru") for x in langs) and any(x.startswith("en") for x in langs):
        out.append((OK, tr("Распознавание текста Windows: %s.") % ", ".join(langs)))
    elif langs:
        out.append((WARN, tr("Распознавание текста Windows: только %s — для русских надписей игры "
                             "добавьте русский язык в Windows (Параметры → Время и язык).") % ", ".join(langs)))
    else:
        out.append((BAD, tr("Распознавание текста Windows недоступно — выбор улова по сонару, учёт улова "
                            "и события в чате не работают.")))

    try:
        import gamenames
        n = len(gamenames.load())
    except Exception:
        n = 0
    out.append((OK, tr("Названия предметов прочитаны из игры (%d).") % n) if n else
               (WARN, tr("Названия из игры не прочитались — используются названия с Вики (часть улова "
                         "может не узнаваться).")))
    out.append((OK, tr("Zoom в настройках программы: %d%% (узнаётся сам при первом автопоиске поплавка).")
                % round(100 * fisher.scale)))
    out.append((OK, tr("Точки рыбалки сохранены — HOME продолжит с ними.")) if fisher.has_points() else
               (OK, tr("Точек пока нет: курсор на воду и HOME.")))
    return out


def text(results):
    return "\n".join("%s %s" % (MARK[s], t) for s, t in results)


def save(results, folder):
    import time
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("diagnostics_%Y%m%d_%H%M%S.txt"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text(results) + "\n")
    return path
