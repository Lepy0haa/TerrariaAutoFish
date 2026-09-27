"""
Удочка и хотбар, отметка поплавка и автопоиск поплавка по картинкам с Вики.
Часть движка рыбалки (см. autofish.py). Настройки и общие функции берутся из autofish в момент
работы (через A.имя) — поэтому их можно менять на ходу (приложение, тесты).
"""
import os
import sys
import time

import numpy as np

from i18n import tr


class _AutoFish:
    """autofish, откуда бы он ни был запущен (модулем или как __main__)."""

    def __getattr__(self, name):
        return getattr(sys.modules["autofish"], name)


A = _AutoFish()


class GearMixin:
    # ---------- поиск поплавка ----------
    def ask_mark(self, sct, cl):
        """Первый заброс: игрок сам показывает поплавок. Программа уточняет место (ищет
        поплавок рядом с курсором) и запоминает, как он выглядит. Возвращает центр или None."""
        tw, th, snap = self.tw, self.th, self.snap
        hint = tr("Наведите курсор на поплавок в игре и нажмите %s") % self.key_name
        while True:
            self.log(tr(">>> Наведите курсор на ПОПЛАВОК и нажмите %s.") % self.key_name, "ask")
            self.state("mark", tr("Отметьте поплавок"), hint)
            A.beep(660, 200)
            self.mark = None
            self.marking.set()
            while self.marking.is_set():
                if self.stopped():
                    self.marking.clear()
                    return None
                time.sleep(0.03)
            if self.mark is None:
                return None
            A.set_cursor(*self.park)      # убираем курсор, чтобы он не попал в снимок поплавка
            if not self.wait(0.3):
                return None
            area = A.rect_around(self.mark, tw // 2 + snap, th // 2 + snap)
            if not A.inside(area, cl):
                self.log(tr("Отметка слишком близко к краю окна — попробуйте ещё раз."), "ask")
                hint = tr("Отметка у края окна. Наведите на поплавок и нажмите %s ещё раз") % self.key_name
                continue
            frame = A.grab(sct, area)
            corner = A.snap_adaptive(frame, tw, th, self.min_bobber_px)
            if corner is None:
                self.log(tr("Рядом с курсором не видно поплавка — наведите точнее, прямо на него."), "ask")
                hint = tr("Рядом с курсором нет поплавка. Наведите прямо на него и нажмите %s") % self.key_name
                self.n += 1
                self.save_dbg("%03d_ne_poplavok.png" % self.n, frame, scale=6)
                continue
            x, y = corner
            self.adopt_bobber(area, frame, x, y)
            self.identify_bobber(frame)
            self.log(tr("Поплавок запомнен: %s. Дальше — автоматически.") % (self.mark,), "good")
            return self.mark

    def identify_bobber(self, frame):
        """Какой это поплавок (по картинкам с Вики) — чтобы потом находить его и по картинке."""
        if self.bobber_sprites is None:
            return
        best = self.bobber_sprites.find(frame, self.sprite_scales())
        if best is not None and best[0] >= A.SPRITE_MIN:
            self.bobber_kind = best[5]
            self.log(tr("Это %s.") % self.bobber_sprites.title(best[5]))
        else:
            self.bobber_kind = None
        self.gear_changed()
        self.save_points()

    def adopt_bobber(self, area, frame, x, y):
        """Запомнить поплавок, найденный в кадре frame (снят с экрана в area) в углу (x, y)."""
        tw, th = self.tw, self.th
        self.mark = (area["left"] + x + tw // 2, area["top"] + y + th // 2)
        self.bobber = frame[y:y + th, x:x + tw].copy()
        self.mark0, self.bobber0 = self.mark, self.bobber.copy()
        self.emit("bobber", img=self.bobber)
        self.points_changed()
        self.save_points()
        self.n += 1
        self.save_dbg("%03d_poplavok.png" % self.n, self.bobber, scale=8)

    # ---------- удочка и поплавки с Вики ----------
    def gear_changed(self):
        names = self.bobber_sprites
        self.emit("gear", rod_slot=self.rod_target() if A.AUTO_ROD else None, manual=A.ROD_SLOT is not None,
                  bobber=names.title(self.bobber_kind) if names and self.bobber_kind else None)

    def rod_target(self):
        """Слот удочки: заданный в настройках или запомненный по удачному забросу (или None)."""
        return A.ROD_SLOT if A.ROD_SLOT is not None else self.rod_slot

    def gear_path(self):
        return os.path.join(os.path.dirname(self.points_path), "gear.json") if self.points_path else None

    def save_gear(self):
        """Слот удочки храним отдельно от точек: хотбар не меняется, когда меняется место рыбалки."""
        try:
            if self.gear_path():
                import json
                with open(self.gear_path(), "w", encoding="utf-8") as fh:
                    json.dump({"rod_slot": self.rod_slot}, fh)
        except Exception:
            pass

    def load_gear(self):
        try:
            import json
            with open(self.gear_path(), encoding="utf-8") as fh:
                v = json.load(fh).get("rod_slot")
            self.rod_slot = int(v) if v is not None and 0 <= int(v) <= 9 else None
        except Exception:
            self.rod_slot = None

    def learn_rod(self):
        """Поплавок в воде — значит, в руках удочка: запоминаем слот, который был выбран при забросе."""
        if not A.AUTO_ROD or A.ROD_SLOT is not None or self.cast_slot is None or self.cast_slot == self.rod_slot:
            return
        self.rod_slot = self.cast_slot
        self.save_gear()
        self.gear_changed()
        self.log(tr("Запомнил: удочка в слоте %d. Если в руках окажется другой предмет — возьму её сам.")
                 % ((self.rod_slot + 1) % 10), "good")

    def sprite_scales(self):
        """Масштабы, в которых искать поплавок: около Zoom из настроек (игра не бывает мельче 100 %).
        При первом автопоиске с «Zoom сам» — все, чтобы узнать Zoom игры."""
        if self.zoom_probe:
            return list(A.ZOOMS)
        return sorted({max(1.0, round(self.scale, 2))} |
                      {v for v in (1.0, 1.25, 1.5, 1.75, 2.0) if abs(v - self.scale) <= 0.3})

    def hotbar_frame(self, sct, cl):
        region = {"left": cl[0], "top": cl[1], "width": min(cl[2] - cl[0], 1000),
                  "height": min(cl[3] - cl[1], 200)}
        return A.grab(sct, region)

    def ensure_rod(self, sct, cl):
        """Удочка должна быть в руках: если выбран другой слот хотбара, жмём цифру слота удочки.
        Слот удочки задан в настройках или запомнен по удачному забросу. Пока он неизвестен —
        забрасываем тем, что в руках (а по картинке переключаемся, только если удочка узнаётся
        очень уверенно: иконки в хотбаре мелкие, кнуты, мечи и кирки на них похожи).
        True — переключили предмет (значит, старый поплавок, если был, игра убрала)."""
        self.cast_slot, self.switched = None, False
        if not A.AUTO_ROD:
            return False
        import hotbar
        frame = self.hotbar_frame(sct, cl)
        sel = hotbar.selected_slot(frame)
        if sel is None:
            return False                     # хотбара не видно (открыт инвентарь, карта…)
        if self.hotbar_u is None:
            self.hotbar_u = sel[1]
        elif abs(sel[1] - self.hotbar_u) > 0.1:
            return False                     # хотбар другого размера — это не он: ничего не жмём
        target = self.rod_target()
        if target is None:
            target = self.rod_hint(frame, sel[0])
            if target is None:
                self.cast_slot = sel[0]      # забросим тем, что в руках; удался заброс — запомним слот
                return False
            if target != sel[0]:
                self.log(tr("Похоже, удочка в слоте %d (по картинке) — беру её.") % ((target + 1) % 10))
        if sel[0] == target:
            self.cast_slot = target
            self.check_bait(frame, sel)
            return False
        if self.rod_misses >= 3:
            if time.time() - self.rod_miss_time < A.ROD_RETRY_AFTER:
                return False                 # переключить не получается — пока не пытаемся
            self.rod_misses = 0              # прошло время — попробуем снова
        if A.terraria_window() is None:
            return False                     # игра не активна — нажатие ушло бы в другое окно
        key = str((target + 1) % 10)
        self.switched = True
        # нажатие может «потеряться» (игра была занята, окно только что стало активным) — пробуем
        # ещё раз и ждём подольше, прежде чем считать, что переключить не получилось
        for wait in A.ROD_KEY_WAITS:
            if A.terraria_window() is None:
                break
            A.press_key(key)
            time.sleep(wait)
            sel2 = hotbar.selected_slot(self.hotbar_frame(sct, cl))
            if sel2 is not None and sel2[0] == target:
                self.rod_misses = 0
                self.cast_slot = target
                self.log(tr("В руках был другой предмет (слот %d) — взял удочку (слот %s).")
                         % ((sel[0] + 1) % 10, key), "good")
                return True
        else:
            self.rod_misses += 1
            self.rod_miss_time = time.time()
            self.log(tr("Нажал %s, чтобы взять удочку, но слот не сменился.") % key, "bad")
            if self.rod_misses >= 3:
                self.log(tr("Не получается взять удочку клавишей — пару минут не переключаю. "
                            "Возьмите удочку в руки сами."), "bad")
                self.emit("notify", title=tr("Удочка"), text=tr("Не получается взять удочку. Возьмите её в руки сами."))
        return True

    def check_bait(self, frame, sel):
        """Сколько наживки на удочке в руках: само число (по образцам цифр), а если не прочиталось
        уверенно — хотя бы сколько в нём цифр. Мало — предупредить один раз."""
        if not A.BAIT_WATCH:
            return
        import hotbar
        x0, y0, x1, y1, rel = hotbar.slot_boxes(*sel)[sel[0]]
        cell = frame[max(0, y0):y1, max(0, x0):x1].astype(np.float64)
        if cell.shape[0] < 16 or cell.shape[1] < 16:
            return
        digits = hotbar.bait_digits(cell, rel * sel[1])
        count = None
        if digits and self.digit_reader is not None:
            try:
                count = self.digit_reader.read(cell, rel * sel[1])
            except Exception:
                count = None
            if count is not None and len(str(count)) != digits:
                count = None                     # не сходится с шириной числа — не верим
        if digits != self.bait_digits or count != self.bait_count:
            self.bait_digits, self.bait_count = digits, count
            self.emit("bait", digits=digits, count=count)
        if (digits == 1 or (count is not None and count < 10)) and not self.bait_warned:
            self.bait_warned = True
            self.log(tr("Наживки осталось меньше 10."), "bad")
            self.emit("notify", title=tr("Наживка"), text=tr("Наживки осталось меньше 10."))
        elif digits >= 2:
            self.bait_warned = False

    def rod_hint(self, frame, selected):
        """Слот, где удочка узнаётся уверенно (есть число наживки и форма удочки), или None."""
        if self.rods is None:
            return None
        r = self.rods.find(frame, A.ROD_HINT_MIN, A.ROD_HINT_MARGIN)
        return r[0] if r else None

    def sprite_candidates(self, frame, n=8, changed=None):
        """Места, где может быть поплавок: пятна ярких цветов, не похожих на небо и воду
        (лучшие n, не ближе ширины поплавка друг к другу). Список (x, y) центров.
        changed — маска того, что изменилось после заброса (тогда ищем только среди нового)."""
        tw, th = self.tw, self.th
        if frame.shape[0] < th or frame.shape[1] < tw:
            return []
        k = min(1.0, A.light_factor(frame))
        # фон — обычный цвет своей же строки: небо, вода (у поверхности светлее, чем в глубине)
        # и кромка воды идут горизонтальными полосами, а поплавок занимает в строке мало места
        row_bg = np.median(frame, 1)[:, None, :]
        far = np.abs(frame - row_bg).max(2) > A.BG_DIST * k
        vivid = (frame.max(2) - frame.min(2)) > A.SAT_MIN * k
        m = far & vivid
        if changed is not None:
            m &= changed
        # только «сплошные» места (все соседи 3x3 тоже яркие): у поплавка они есть, а у тонких
        # полос — светлой кромки воды, лески, контуров — нет, иначе они забирают всех кандидатов
        core = m.copy()
        core[0, :] = core[-1, :] = core[:, 0] = core[:, -1] = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                core[1:-1, 1:-1] &= m[1 + dy:m.shape[0] - 1 + dy, 1 + dx:m.shape[1] - 1 + dx]
        m = core.astype(np.int32)
        ii = np.pad(m.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        sums = (ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]).astype(np.float64)
        # поплавок — отдельное пятно: в окне вдвое больше вокруг него ярких мест почти не прибавляется.
        # У больших ярких областей (пирс, постройки, NPC, отражения) — прибавляется много
        py, px = th // 2, tw // 2
        jj = np.pad(np.pad(m, ((py, py), (px, px))).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        H, W = th + 2 * py, tw + 2 * px
        big = (jj[H:, W:] - jj[:-H, W:] - jj[H:, :-W] + jj[:-H, :-W]).astype(np.float64)
        if changed is None:
            sums[sums < 0.5 * big] = 0
        out = []
        for _ in range(n):
            y, x = np.unravel_index(int(sums.argmax()), sums.shape)
            if sums[y, x] < 2:
                break
            out.append((int(x) + tw // 2, int(y) + th // 2))
            sums[max(0, y - th):y + th, max(0, x - tw):x + tw] = -1
        return out

    def sprite_search(self, frame, only=None, changed=None, n=8, near=None):
        """Поплавок по картинкам с Вики: (оценка, центр x, центр y, ключ, масштаб) или None.
        near — (x точки заброса, x игрока) в кадре: поплавок летит от игрока в сторону курсора
        (быстрые удочки — и дальше него), поэтому место рядом с игроком или позади него
        сомнительно: оценка уменьшается до NEAR_PENALTY.
        При первом автопоиске (zoom_probe) все масштабы проверяются только у трёх лучших мест."""
        if self.bobber_sprites is None:
            return None
        probe, self.zoom_probe = self.zoom_probe, False      # 1-й проход — в обычных масштабах
        try:
            found = self._sprite_scores(frame, self.sprite_candidates(frame, n, changed), only, near)
        finally:
            self.zoom_probe = probe
        if probe and found:
            top = sorted(found, key=lambda r: -r[0])[:3]
            found = self._sprite_scores(frame, [(r[1], r[2]) for r in top], only, near) or found
        return max(found, key=lambda r: r[0]) if found else None

    @staticmethod
    def throw_penalty(bx, cast_x, player_x):
        """Насколько место bx сомнительно для первого заброса: поплавок улетает от игрока в сторону
        курсора хотя бы на полпути; ближе к игроку (или позади него) — штраф до NEAR_PENALTY."""
        way = cast_x - player_x
        if abs(way) < 1:
            return 0.0
        along = (bx - player_x) / float(way)          # 0 — у игрока, 1 — под курсором, >1 — дальше
        return A.NEAR_PENALTY * min(1.0, max(0.0, (0.5 - along) / 0.5))

    def _sprite_scores(self, frame, spots, only, near):
        k = max(self.sprite_scales()) / self.scale      # запас под самый крупный масштаб
        pad_x, pad_y = int((self.tw + 8 * self.scale) * k), int((self.th + 8 * self.scale) * k)
        out = []
        for cx, cy in spots:
            x0, y0 = max(0, cx - pad_x), max(0, cy - pad_y)
            patch = frame[y0:cy + pad_y, x0:cx + pad_x]
            r = self.bobber_sprites.find(patch, self.sprite_scales(), only=only)
            if not r:
                continue
            v, x, y, w, h, key, s = r
            bx, by = x0 + x + w // 2, y0 + y + h // 2
            if near is not None:
                v -= self.throw_penalty(bx, *near)
            out.append((v, bx, by, key, s))
        return out

    def mark_area(self, cl, player):
        """Где искать поплавок после первого заброса: между игроком и точкой заброса и дальше в
        сторону заброса — быстрые удочки (золотая, механическая) бросают дальше курсора."""
        s = self.scale
        cx, cy = self.cast_point
        right = cx >= player[0]
        x0 = max(cl[0], min(player[0], cx) - int((120 if right else A.THROW_BEYOND) * s))
        x1 = min(cl[2], max(player[0], cx) + int((A.THROW_BEYOND if right else 120) * s))
        y0 = max(cl[1], min(player[1], cy) - int(160 * s))
        y1 = min(cl[3], max(player[1], cy) + int(120 * s))
        if x1 - x0 < 3 * self.tw or y1 - y0 < 3 * self.th:
            return None
        return {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}

    def auto_mark(self, sct, cl, player):
        """Первый заброс: найти поплавок самому по картинкам поплавков с Вики — между игроком
        и точкой заброса (и чуть дальше). Возвращает центр или None (тогда попросим отметить)."""
        if not A.AUTO_MARK or self.bobber_sprites is None:
            return None
        self.zoom_probe = A.AUTO_ZOOM                # заодно узнаем Zoom игры по размеру поплавка
        try:
            return self._auto_mark(sct, cl, player)
        finally:
            self.zoom_probe = False

    def _auto_mark(self, sct, cl, player):
        s, tw, th = self.scale, self.tw, self.th
        area = self.mark_area(cl, player)
        if area is None:
            return None
        x0, y0 = area["left"], area["top"]
        frame = A.grab(sct, area)
        near = (self.cast_point[0] - x0, player[0] - x0)   # поплавок летит от игрока в сторону курсора
        before = self.mark_before
        if before is not None and before.shape != frame.shape:
            before = None
        # сам игрок, удочка у него в руках и курсор (он над головой игрока) — не поплавок
        for (px, py), hx, hy in ((player, int(28 * s), int(45 * s)), (self.park, int(25 * s), int(25 * s))):
            px, py = px - x0, py - y0
            for img in (frame, before):
                if img is not None:
                    img[max(0, py - hy):max(0, py + hy), max(0, px - hx):max(0, px + hx)] = frame[0, 0]
        best = None
        if before is not None:
            # главное: поплавок появился только после заброса. Пирс, столбы, NPC и прочее
            # яркое стоят на месте — среди изменившегося их нет
            changed = np.abs(frame - before).max(2) > 30
            best = self.sprite_search(frame, changed=changed, n=A.MARK_CANDIDATES, near=near)
        if best is None or best[0] < A.SPRITE_MIN:
            # снимка до заброса нет или новое не похоже на поплавок — ищем среди всего яркого,
            # но строже (там больше похожего)
            other = self.sprite_search(frame, n=A.MARK_CANDIDATES, near=near)
            if other is not None and other[0] >= A.SPRITE_MIN + 0.05 and (best is None or other[0] > best[0]):
                best = other
        self.n += 1
        self.save_dbg("%03d_avto_poisk.png" % self.n, frame, scale=2,
                      rects=[(best[1] - tw // 2, best[2] - th // 2, tw, th,
                              (0, 255, 0) if best[0] >= A.SPRITE_MIN else (0, 0, 255))] if best else [])
        if best is None or best[0] < A.SPRITE_MIN:
            if best is not None:
                self.log(tr("Похожее на поплавок: %s, совпадение %.2f — мало.")
                         % (self.bobber_sprites.title(best[3]), best[0]))
            return None
        v, bx, by, key, zoom = best
        if A.AUTO_ZOOM and abs(zoom - self.scale) >= 0.2 and v >= A.SPRITE_MIN + 0.05:
            # поплавок уверенно совпал в другом масштабе — значит, Zoom в игре другой
            self.log(tr("Похоже, Zoom в игре %d%% (в настройках было %d%%) — поставил %d%%.")
                     % (round(100 * zoom), round(100 * self.scale), round(100 * zoom)), "good")
            self.set_scale(zoom)
            self.emit("zoom", scale=zoom)
            tw, th = self.tw, self.th
        # уточняем место так же, как при отметке курсором
        snap = self.snap
        center = (x0 + bx, y0 + by)
        near = A.rect_around(center, tw // 2 + snap, th // 2 + snap)
        nx0, ny0 = max(cl[0], near["left"]), max(cl[1], near["top"])     # у края окна — обрезаем
        nx1 = min(cl[2], near["left"] + near["width"])
        ny1 = min(cl[3], near["top"] + near["height"])
        if nx1 - nx0 < tw or ny1 - ny0 < th:
            return None
        near = {"left": nx0, "top": ny0, "width": nx1 - nx0, "height": ny1 - ny0}
        near_frame = A.grab(sct, near)
        corner = A.snap_adaptive(near_frame, tw, th, self.min_bobber_px)
        if corner is None:                         # пятно не выделилось — берём место по картинке
            corner = (int(np.clip(center[0] - nx0 - tw // 2, 0, near["width"] - tw)),
                      int(np.clip(center[1] - ny0 - th // 2, 0, near["height"] - th)))
        self.bobber_kind = key
        self.adopt_bobber(near, near_frame, *corner)
        self.gear_changed()
        self.log(tr("Поплавок нашёлся сам: %s (совпадение %.2f), %s. Дальше — автоматически.")
                 % (self.bobber_sprites.title(key), v, self.mark), "good")
        return self.mark
