"""
Поиск поплавка после заброса: образец, картинка вида поплавка с Вики, широкий поиск.
Часть движка рыбалки (см. autofish.py). Настройки и общие функции берутся из autofish в момент
работы (через A.имя) — поэтому их можно менять на ходу (приложение, тесты).
"""
import sys
import time

import numpy as np

from i18n import tr


class _AutoFish:
    """autofish, откуда бы он ни был запущен (модулем или как __main__)."""

    def __getattr__(self, name):
        return getattr(sys.modules["autofish"], name)


A = _AutoFish()


class SearchMixin:
    def search(self, sct, cl, center, half_x, half_y, wide=False, strict=False, update=True):
        """Ищет поплавок в зоне вокруг center. Возвращает (центр или None, непохожесть).
        Обычный поиск — по текущему образцу. Широкий (wide) — ещё и по образцу, который
        отметил игрок, и просто по цветам поплавка."""
        tw, th = self.tw, self.th
        zone = A.rect_around(center, half_x + tw // 2, half_y + th // 2)
        zone["left"], zone["top"] = max(cl[0], zone["left"]), max(cl[1], zone["top"])
        zone["width"] = min(cl[2], zone["left"] + zone["width"]) - zone["left"]
        zone["height"] = min(cl[3], zone["top"] + zone["height"]) - zone["top"]
        if zone["width"] < tw + 2 or zone["height"] < th + 2:
            return None, float("inf")
        frame = A.grab(sct, zone)
        best_err, hit, blob = float("inf"), None, False
        templates = [self.bobber]
        if wide and self.bobber0 is not None:
            templates.append(self.bobber0)
        for tmpl in templates:
            y, x, err = A.match(frame, tmpl)
            best_err = min(best_err, err)
            # Непохожесть растёт, когда меняется небо (закат, рассвет), хотя поплавок на месте.
            # Поэтому главное — есть ли в найденном месте сплошное яркое пятно поплавка.
            m = 6
            y0, x0 = max(0, y - m), max(0, x - m)
            corner = A.snap_adaptive(frame[y0:y + th + m, x0:x + tw + m], tw, th, self.min_bobber_px)
            if corner is not None:
                cand = (x0 + corner[0], y0 + corner[1])
                # яркое пятно бывает и не поплавком (стена, доски пирса, факелы) — проверяем, что это
                # наш поплавок, иначе образец «переучится» на фон и дальше будет находиться фон
                if self.bobber_here(frame, *cand):
                    hit, blob = cand, True
                    break
                continue
            # без пятна — только по образцу; если вид поплавка известен, проверяем и по картинке:
            # образец мог «переучиться» на кромку воды, а она одинаковая по всей ширине
            if err <= A.NOT_FOUND_ERR and not strict and (not self.bobber_kind or self.bobber_here(frame, x, y)):
                hit = (x, y)
                break
        if hit is not None and wide and self.bobber_kind and self.bobber_sprites is not None:
            # широкий поиск: если в зоне есть место, намного больше похожее на поплавок по картинке
            # с Вики, — берём его (иначе можно «найти» пустое место рядом с настоящим поплавком)
            here = self.bobber_score(frame, *hit) or 0.0
            best = self.sprite_search(frame, only=[self.bobber_kind])
            if best is not None and best[0] >= A.SPRITE_MIN and best[0] > here + 0.1:
                hit = (int(np.clip(best[1] - tw // 2, 0, frame.shape[1] - tw)),
                       int(np.clip(best[2] - th // 4 - th // 2, 0, frame.shape[0] - th)))
                blob = True
        if hit is None and self.bobber_kind and self.bobber_sprites is not None:
            # по образцу не нашёлся — ищем по картинке этого вида поплавка с Вики во всей зоне
            best = self.sprite_search(frame, only=[self.bobber_kind])
            if best is not None and best[0] >= A.SPRITE_MIN:
                x = int(np.clip(best[1] - tw // 2, 0, frame.shape[1] - tw))
                y = int(np.clip(best[2] - th // 4 - th // 2, 0, frame.shape[0] - th))
                hit, blob = (x, y), True
        if hit is None and wide:
            corner = A.snap_adaptive(frame, tw, th, self.min_bobber_px)
            ref = self.bobber0 if self.bobber0 is not None else self.bobber
            patch = frame[corner[1]:corner[1] + th, corner[0]:corner[0] + tw] if corner is not None else None
            # похоже и цветом, и силуэтом (отражения, факелы и доски бывают того же цвета)
            if (corner is not None and A.same_colors(patch, ref) and
                    A.bobber_likeness(patch, ref) >= A.SIMILAR_MIN):
                hit, blob = corner, True
        self.n += 1
        if hit:
            self.save_dbg("%03d_poisk%s.png" % (self.n, "_shiroko" if wide else ""), frame, scale=4,
                          rects=[(hit[0], hit[1], tw, th, (0, 255, 0))])
        else:
            self.save_dbg("%03d_poisk%s_net.png" % (self.n, "_shiroko" if wide else ""), frame, scale=4)
        if hit is None:
            return None, best_err
        x, y = hit
        if blob and update:
            self.bobber = frame[y:y + th, x:x + tw].copy()   # обновляем образец под текущее освещение
        pos = (zone["left"] + x + tw // 2, zone["top"] + y + th // 2)
        if self.debug:
            self.log(tr("Поплавок: %s, непохожесть %.0f, пятно поплавка: %s%s")
                     % (pos, best_err, tr("есть") if blob else tr("нет"), tr(" (широкий поиск)") if wide else ""))
        return pos, best_err

    def bobber_score(self, frame, x, y):
        """Насколько место с левым верхним углом (x, y) похоже на картинку этого вида поплавка с
        Вики (None — вид неизвестен)."""
        if not self.bobber_kind or self.bobber_sprites is None:
            return None
        tw, th = self.tw, self.th
        pad = int(6 * self.scale)
        patch = frame[max(0, y - pad):y + th + pad, max(0, x - pad):x + tw + pad]
        r = self.bobber_sprites.find(patch, self.sprite_scales(), only=[self.bobber_kind])
        return r[0] if r is not None else 0.0

    def bobber_here(self, frame, x, y):
        """Наш ли поплавок в кадре frame с левым верхним углом (x, y): по картинке этого вида
        поплавка с Вики (не зависит от освещения), а если вид неизвестен — по цветам."""
        tw, th = self.tw, self.th
        score = self.bobber_score(frame, x, y)
        if score is not None:
            # порог — как при узнавании поплавка: пустая кромка воды в темноте даёт около 0.7
            return score >= A.SPRITE_MIN
        block = frame[y:y + th, x:x + tw]
        ref = self.bobber0 if self.bobber0 is not None else self.bobber
        if ref is None or A.same_colors(block, ref):
            return True
        # цвета исходного поплавка могли смениться (ночь) — тогда нужен и похожий силуэт: текущий
        # образец мог «переучиться» на фон, одних его цветов мало
        return (self.bobber is not None and A.same_colors(block, self.bobber) and
                block.shape == ref.shape and A.bobber_likeness(block, ref) >= A.SIMILAR_MIN)

    def similarity(self, sct, pos):
        """Насколько силуэт в месте pos похож на запомненный поплавок (лучшее из текущего и
        исходного образца)."""
        patch = A.grab(sct, A.rect_around(pos, self.tw // 2, self.th // 2))
        refs = [r for r in (self.bobber, self.bobber0, getattr(self, "bobber_ref", None))
                if r is not None and r.shape == patch.shape]
        return max((A.bobber_likeness(patch, r) for r in refs), default=0.0)

    def bobber_in_water(self, sct, cl):
        """Лежит ли поплавок в воде прямо сейчас (например, продолжаем после паузы). Засчитываем,
        только если найденное похоже на запомненный поплавок и стоит на месте на двух снимках
        подряд: только что заброшенный (ещё летящий) поплавок ждём, пока не сядет."""
        last = None
        end = time.perf_counter() + A.SETTLE_TIME + 1.5
        while time.perf_counter() < end:
            # образец не обновляем, пока не убедились, что это поплавок, а не что-то похожее рядом
            pos, _ = self.search(sct, cl, self.mark, self.zone_x, self.zone_y, strict=True, update=False)
            ok = pos is not None and self.similarity(sct, pos) >= A.SIMILAR_MIN
            if ok and last is not None and max(abs(pos[0] - last[0]), abs(pos[1] - last[1])) <= 4:
                return pos
            if not ok and last is None and pos is None:
                return None                      # с первого взгляда ничего нет — поплавка нет
            last = pos if ok else None
            if not self.wait(0.4):
                return None
        return None

    def settle(self, sct, cl):
        """Ждём, пока поплавок сядет на воду, и сразу начинаем следить (рыба бывает клюёт сразу
        после заброса): с SETTLE_MIN ищем его около отметки, и как только он на одном месте на
        двух снимках подряд — готово. (центр, непохожесть) или (None, ...) — тогда обычный поиск."""
        start = time.perf_counter()
        err, last = float("inf"), None
        if not self.wait(A.SETTLE_MIN):
            return None, err
        while time.perf_counter() - start < A.SETTLE_TIME + 0.4:
            # пока не убедились, что поплавок сел, образец не обновляем (летящий смазан)
            pos, err = self.search(sct, cl, self.mark, self.zone_x, self.zone_y, strict=True, update=False)
            if pos and last and max(abs(pos[0] - last[0]), abs(pos[1] - last[1])) <= 2:
                final, err2 = self.search(sct, cl, pos, self.zone_x // 2, self.zone_y // 2)
                return (final, err2) if final else (pos, err)
            last = pos
            if not self.wait(0.08):
                return None, err
        return None, err

    def locate(self, sct, cl):
        """Найти поплавок после заброса. Если его нет на обычном месте — подождать (вдруг
        ещё не упал) и поискать шире вокруг места, которое отметил игрок."""
        pos, err = self.search(sct, cl, self.mark, self.zone_x, self.zone_y)
        if pos:
            return pos, err
        self.state("search", tr("Ищу поплавок"), tr("На обычном месте его нет — ищу вокруг отметки"))
        if not self.wait(0.4):
            return None, err
        pos, err = self.search(sct, cl, self.mark, self.zone_x, self.zone_y)
        if pos:
            return pos, err
        self.log(tr("Поплавка нет на обычном месте — ищу шире вокруг отметки…"))
        home = self.mark0 or self.mark
        pos, err2 = self.search(sct, cl, home, self.zone_x * 3, self.zone_y * 3, wide=True)
        if pos is None and self.bobber_kind and self.bobber_sprites is not None:
            pos = self.sprite_locate(sct, cl, home)
        if pos is None:
            return None, min(err, err2)
        if max(abs(pos[0] - self.mark[0]), abs(pos[1] - self.mark[1])) > self.zone_x // 2:
            self.mark = pos
            self.log(tr("Нашёл поплавок в стороне %s — теперь ищу его там.") % (pos,))
        else:
            self.log(tr("Нашёл поплавок."))
        return pos, err2

    def sprite_locate(self, sct, cl, home):
        """Поплавок не узнали по образцу (сильно сменилось освещение) — ищем по картинке
        этого вида поплавка с Вики вокруг отметки. Нашли — обновляем образец."""
        zone = A.rect_around(home, self.zone_x * 3 + self.tw, self.zone_y * 3 + self.th)
        zone["left"], zone["top"] = max(cl[0], zone["left"]), max(cl[1], zone["top"])
        zone["width"] = min(cl[2], zone["left"] + zone["width"]) - zone["left"]
        zone["height"] = min(cl[3], zone["top"] + zone["height"]) - zone["top"]
        if zone["width"] < 3 * self.tw or zone["height"] < 3 * self.th:
            return None
        frame = A.grab(sct, zone)
        best = self.sprite_search(frame, only=[self.bobber_kind])
        if best is None or best[0] < A.SPRITE_MIN:
            return None
        tw, th = self.tw, self.th
        x = int(np.clip(best[1] - tw // 2, 0, frame.shape[1] - tw))
        y = int(np.clip(best[2] - th // 4 - th // 2, 0, frame.shape[0] - th))   # как при отметке
        self.bobber = frame[y:y + th, x:x + tw].copy()
        self.log(tr("Узнал поплавок по картинке (%s, совпадение %.2f).")
                 % (self.bobber_sprites.title(self.bobber_kind), best[0]))
        return zone["left"] + x + tw // 2, zone["top"] + y + th // 2

    # ---------- сдвиг картинки (персонажа сдвинуло, камера уехала) ----------
    def scene_region(self, cl, pos):
        """Место рыбалки: от точки заброса до поплавка и вокруг, в пределах окна игры."""
        s = self.scale
        cx, cy = self.cast_point
        x0 = max(cl[0], min(cx, pos[0]) - int(170 * s))
        x1 = min(cl[2], max(cx, pos[0]) + int(170 * s))
        y0 = max(cl[1], min(cy, pos[1]) - int(130 * s))
        y1 = min(cl[3], max(cy, pos[1]) + int(110 * s))
        if x1 - x0 < 64 or y1 - y0 < 64:
            return None
        return {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}

    def remember_scene(self, sct, cl, player, pos):
        """После удачного поиска поплавка: снимок места рыбалки — без персонажа (камера держит его в
        центре, при сдвиге он не двигается) и без поплавка с курсором (они бывают и не бывают)."""
        self.scene = None
        if not A.FOLLOW_SHIFT or self.cast_point is None:
            return
        import sceneshift
        reg = self.scene_region(cl, pos)
        if reg is None:
            return
        g = sceneshift.gray(A.grab(sct, reg))
        mask = np.ones(g.shape, bool)
        s = self.scale
        for (px, py), hx, hy in ((player, int(45 * s), int(70 * s)), (pos, self.tw, self.th),
                                 (self.park or player, int(25 * s), int(25 * s))):
            px, py = px - reg["left"], py - reg["top"]
            mask[max(0, py - hy):max(0, py + hy), max(0, px - hx):max(0, px + hx)] = False
        if mask.mean() > 0.5:
            self.scene = (reg, g, mask)

    def follow_shift(self, sct, cl):
        """Поплавок не нашёлся: не сдвинулась ли вся картинка? Сдвинулась уверенно — переносим точку
        заброса и отметку поплавка на столько же и пробуем снова (это не неудачный заброс)."""
        if not A.FOLLOW_SHIFT or self.scene is None or self.cast_point is None:
            return False
        import sceneshift
        reg, g0, mask = self.scene
        if not A.inside(reg, cl):
            return False
        r = sceneshift.estimate(g0, sceneshift.gray(A.grab(sct, reg)), mask)
        if r is None:
            return False
        dx, dy, peak = r
        if abs(dx) + abs(dy) < A.SHIFT_MIN or abs(dx) > reg["width"] // 3 or abs(dy) > reg["height"] // 3:
            return False
        cx, cy = self.cast_point[0] + dx, self.cast_point[1] + dy
        if not (cl[0] + 10 <= cx < cl[2] - 10 and cl[1] + 10 <= cy < cl[3] - 10):
            return False                          # точка заброса уехала за край окна — не угнаться
        self.cast_point = (cx, cy)
        for name in ("mark", "mark0"):
            p = getattr(self, name)
            if p is not None:
                setattr(self, name, (p[0] + dx, p[1] + dy))
        self.scene = None
        self.phase, self.watched = "unknown", None
        self.shifts += 1
        self.log(tr("Картинка сдвинулась на %+d, %+d пикс. — наверное, персонажа сдвинуло. Переношу точку "
                    "заброса и поплавка туда же.") % (dx, dy), "bad")
        self.save_points()
        return True
