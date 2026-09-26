"""
Здоровье персонажа, лимиты сессии и зелья (быстрый бафф или из хотбара).
Часть движка рыбалки (см. autofish.py). Настройки и общие функции берутся из autofish в момент
работы (через A.имя) — поэтому их можно менять на ходу (приложение, тесты).
"""
import sys
import time

from i18n import tr


class _AutoFish:
    """autofish, откуда бы он ни был запущен (модулем или как __main__)."""

    def __getattr__(self, name):
        return getattr(sys.modules["autofish"], name)


A = _AutoFish()


class ExtrasMixin:
    # ---------- здоровье и лимиты ----------
    def check_health(self, sct, cl, watching=False):
        """Сердечки здоровья (справа вверху): стало заметно меньше на двух проверках подряд —
        персонаж получает урон: вытащить поплавок, встать на паузу, сообщить. True — встали."""
        self.hp_last = time.perf_counter()
        if not A.HEALTH_GUARD:
            return False
        W, H = cl[2] - cl[0], cl[3] - cl[1]
        region = {"left": cl[0] + int(W * 0.55), "top": cl[1], "width": W - int(W * 0.55), "height": int(H * 0.25)}
        mask = A.heart_mask(A.grab(sct, region))
        if self.hp_band is None:
            self.hp_band = A.heart_rows(mask)
            if self.hp_band is None:
                return False                  # сердечек не видно (другой стиль, скрыт интерфейс)
        count = int(mask[self.hp_band[0]:self.hp_band[1]].sum())
        if count < 150:
            return False
        if self.hp_base is None or count > self.hp_base:
            self.hp_base = count              # здоровье восстановилось — это новая «норма»
        self.hp_low = self.hp_low + 1 if count < self.hp_base * (1 - A.HEALTH_DROP) else 0
        if self.hp_low < 2:
            return False
        self.hp_low = 0
        lost = 1 - count / float(self.hp_base)
        self.hp_base = None
        if watching and self.cast_point is not None:
            A.click(*self.cast_point)           # вытаскиваем поплавок
        self.phase, self.watched = "idle" if watching else self.phase, None
        text = tr("Персонаж получает урон (здоровья меньше на %d%%) — вытащил поплавок и поставил на паузу.") \
            % round(100 * lost)
        self.log(text, "bad")
        self.pause(tr("персонаж получает урон"))
        A.beep(330, 600)
        return True

    def session_over(self):
        """Лимит по времени или подсечкам: вытащить поплавок, остановиться и (если выбрано)
        выключить компьютер. True — остановились."""
        why = None
        if A.STOP_AFTER_MIN and self.started and time.time() - self.started >= A.STOP_AFTER_MIN * 60:
            why = tr("прошло %d мин") % A.STOP_AFTER_MIN
        elif A.STOP_AFTER_HOOKS and self.hooks >= A.STOP_AFTER_HOOKS:
            why = tr("сделано %d подсечек") % A.STOP_AFTER_HOOKS
        if why is None:
            return False
        if self.phase == "watching" and self.cast_point is not None:
            A.click(*self.cast_point)
        self.phase, self.watched = "idle", None
        self.resume_on_focus = False
        self.stop_fishing(tr("Рыбалка закончена: %s.") % why)
        if A.SHUTDOWN_AFTER:
            try:
                A.schedule_shutdown(A.SHUTDOWN_DELAY)
                self.log(tr("Компьютер выключится через %d с. Отменить — кнопка в окне программы.") % A.SHUTDOWN_DELAY,
                         "bad")
                self.emit("shutdown", seconds=A.SHUTDOWN_DELAY)
            except Exception as e:
                self.log(tr("Не получилось запланировать выключение: %r") % e, "bad")
        return True

    # ---------- зелья ----------
    def check_buffs(self, sct, cl, force=False):
        """Есть ли нужные баффы. Нет — выпить (из хотбара или быстрым баффом) и проверить."""
        if self.buffs is None or not (A.BUFFS_ON or force):
            return None
        now = time.time()
        if not force and now - self.last_buff_check < A.BUFF_CHECK_EVERY:
            return None
        self.last_buff_check = now
        if force:
            self.buff_backoff.clear()             # проверили вручную — пробовать выпить сразу
        region = {"left": cl[0], "top": cl[1], "width": min(cl[2] - cl[0], 900),
                  "height": min(cl[3] - cl[1], 360)}
        want = [n for n in self.buffs.icons if A.BUFF_WANT.get(n)]
        have = self.buffs.find(A.grab(sct, region))
        status = {n: have[n] >= A.BUFF_THRESHOLD() for n in want}
        self.emit("buffs", status=status)
        if force:
            return status
        missing = [n for n in want if not status[n] and now >= self.buff_backoff.get(n, 0)]
        if not missing:
            return status
        if A.BUFF_METHOD == "hotbar" and self.potions is not None:
            missing = self.drink_from_hotbar(sct, cl, missing, now)
            if not missing:
                status = {n: status[n] for n in want}
                return status
            time.sleep(0.5)
        else:
            A.press_key(A.BUFF_KEY)
            time.sleep(0.9)
        have = self.buffs.find(A.grab(sct, region))
        for n in missing:
            if have[n] >= A.BUFF_THRESHOLD():
                self.log(tr("Выпил: %s.") % tr(A.BUFF_NAMES[n]), "good")
            else:
                self.buff_backoff[n] = now + A.BUFF_BACKOFF
                why = (tr("Не вижу баффа «%s» после зелья из хотбара — зелье кончилось или не выпилось.")
                       if A.BUFF_METHOD == "hotbar" and self.potions is not None else
                       tr("Не вижу баффа «%s» и после быстрого баффа — кончились зелья?"))
                self.log(why % tr(A.BUFF_NAMES[n]), "bad")
                self.emit("notify", title=tr("Зелья"),
                          text=tr("Не получается выпить: %s. Кончились зелья?") % tr(A.BUFF_NAMES[n]))
        status = {n: have[n] >= A.BUFF_THRESHOLD() for n in want}
        self.emit("buffs", status=status)
        return status

    def report_absent(self, absent):
        """Нужных зелий нет в хотбаре: одно сообщение на все сразу. Повторяем, только если список
        изменился или раз в POTION_NAG_EVERY секунд (а не каждую минуту про каждое зелье)."""
        key = tuple(sorted(absent))
        changed = key != self.absent_potions
        self.absent_potions = key
        if changed:
            self.emit("absent", potions=list(key))
        if not key or not A.POTION_REMIND:
            return
        now = time.time()
        if not changed and now - self.absent_told < A.POTION_NAG_EVERY:
            return
        self.absent_told = now
        names = ", ".join(tr(A.BUFF_NAMES[n]) for n in key)
        self.log(tr("Нет в хотбаре: %s — положите зелья в хотбар.") % names, "bad")
        if changed:
            self.emit("notify", title=tr("Зелья"), text=tr("Нет в хотбаре: %s.") % names)

    def potion_slots(self, frame):
        """Какие зелья лежат в хотбаре: {зелье: номер слота}. Слот засчитываем зелью, только если
        он похож именно на него больше, чем на другие зелья, и достаточно сильно."""
        r = self.potions.all_scores(frame) if self.potions is not None else None
        if r is None:
            return {}
        found = {}
        for j, (sc, count) in enumerate(r[1]):
            if not sc:
                continue
            key = max(sc, key=sc.get)
            need = A.POTION_MIN if count else A.POTION_MIN_SINGLE
            if sc[key] >= need and (key not in found or sc[key] > found[key][1]):
                found[key] = (j, sc[key])
        return {k: v[0] for k, v in found.items()}

    def drink_from_hotbar(self, sct, cl, missing, now):
        """Выпить нужные зелья точечно: цифра слота зелья, клик (зелье выпивается), потом снова
        удочка в руки. Смена предмета убирает поплавок — поэтому пьём между забросами.
        Возвращает зелья, которые выпить так не вышло (их нет в хотбаре)."""
        import hotbar
        frame = self.hotbar_frame(sct, cl)
        sel = hotbar.selected_slot(frame)
        if sel is None:
            self.log(tr("Хотбар не виден (открыт инвентарь?) — зелья из хотбара не выпить."), "bad")
            return []
        slots = self.potion_slots(frame)
        back = self.rod_target()
        if back is None:
            back = sel[0]                        # вернём то, что было в руках (обычно удочка)
        drank, left = [], []
        absent = [n for n in missing if n not in slots]
        for n in absent:
            self.buff_backoff[n] = now + A.POTION_RETRY
        self.report_absent(absent)
        for n in missing:
            if n not in slots:
                continue
            key = str((slots[n] + 1) % 10)
            A.press_key(key)
            time.sleep(0.25)
            now_sel = hotbar.selected_slot(self.hotbar_frame(sct, cl))
            if now_sel is None or now_sel[0] != slots[n]:
                self.log(tr("Нажал %s, чтобы взять зелье, но слот не сменился.") % key, "bad")
                left.append(n)
                continue
            A.click(*self.park)                    # зелье пьётся кликом (курсор — над персонажем)
            time.sleep(0.4)
            drank.append(n)
        if drank or left:
            A.press_key(str((back + 1) % 10))      # снова удочка в руки
            time.sleep(0.25)
            self.phase, self.watched = "idle", None
        return drank + left
