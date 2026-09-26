"""
Улов: зелье сонара, надпись о подборе, полный инвентарь, задание рыбака.
Часть движка рыбалки (см. autofish.py). Настройки и общие функции берутся из autofish в момент
работы (через A.имя) — поэтому их можно менять на ходу (приложение, тесты).
"""
import sys
import time

import numpy as np

import i18n
from i18n import tr


class _AutoFish:
    """autofish, откуда бы он ни был запущен (модулем или как __main__)."""

    def __getattr__(self, name):
        return getattr(sys.modules["autofish"], name)


A = _AutoFish()


class CatchMixin:
    # ---------- задание рыбака ----------
    def check_quest(self, item_id):
        """Поймали рыбу для задания рыбака — пауза и уведомление."""
        if A.QUEST_FISH is None or item_id != A.QUEST_FISH or self.catches is None:
            return
        name = self.catch_name(item_id)
        self.log(tr("Поймал рыбу для задания рыбака: %s!") % name, "good")
        self.emit("notify", title=tr("Задание рыбака"), text=tr("Поймана %s — отнесите её рыбаку.") % name)
        self.resume_on_focus = False
        self.stop_fishing(tr("Пауза: рыба для задания рыбака поймана."), notify=False)
        A.beep(1200, 150)

    # ---------- сонар: выбор улова ----------
    def catch_name(self, item_id):
        it = self.catches.items[item_id]
        return it["ru"] if i18n.LANG == "ru" else it["en"]

    def current_biome(self):
        if A.CATCH_BIOME != "auto":
            return A.CATCH_BIOME
        return self.catches.guess_biome(self.recent_catch) if self.catches else None

    def heat_hint(self):
        """Рыбачим в лаве, а надпись сонара не читается: над лавой игра «дрожит» картинку
        (искажение от тепла) и буквы двоятся. Подсказать один раз, как это выключить."""
        if self.heat_hinted or self.current_biome() != "lava":
            return
        self.heat_hinted = True
        self.log(tr("Над лавой надписи дрожат и двоятся — их трудно прочитать. Выключите в игре: "
                    "Настройки → Видео → «Искажение от тепла»."), "bad")

    def ocr_ready(self):
        if self.ocr_ok is None:
            try:
                import ocr
                self.ocr_ok = bool(ocr.available_languages())
            except Exception:
                self.ocr_ok = False
            if not self.ocr_ok and A.SONAR_FILTER:
                self.log(tr("Распознавание текста Windows недоступно — выбор улова по сонару не работает."), "bad")
        return self.ocr_ok and self.catches is not None

    def sonar_reader(self, sct, cl, pos):
        """Читатель надписи сонара для этого заброса — если выбор улова включён или идёт запись
        (тогда надписи сохраняются для разбора). None — не нужен или OCR недоступен."""
        if not (A.SONAR_FILTER or self.record or self.debug) or not self.ocr_ready():
            return None
        import sonar
        rd = sonar.SonarReader(self.scale)
        rd.reg = rd.region(pos, cl)
        rd.set_base(A.grab(sct, rd.reg))
        return rd

    def sonar_refresh(self, sct, rd):
        """Обновить снимок фона надписи — только если надписи сейчас нет (иначе висящее название
        пропущенного улова попало бы в «фон» и следующая такая же поклёвка не прочиталась бы)."""
        frame = A.grab(sct, rd.reg)
        if rd.text_mask(frame).sum() < 15:
            rd.set_base(frame)

    def read_name(self, rd, frame, exclude=None, use_ocr=True):
        """Какой предмет написан: (id, похожесть, отрыв, прочтения) или None — надписи нет.
        Сначала — память надписей (без ошибок OCR), потом OCR; уверенно прочитанное запоминается."""
        m = rd.extract(frame, exclude)
        if m is None:
            return None
        if self.memory is not None:
            hit = self.memory.match(m)
            if hit is not None:
                return hit[0], 1.0, hit[2], []
        if not use_ocr or not self.ocr_ready():
            return None, 0.0, 0.0, []
        texts = rd.ocr(m)
        item_id, ratio, margin = self.catches.identify_any(texts) if texts else (None, 0.0, 0.0)
        if item_id is not None and ratio >= A.LEARN_MIN_RATIO and margin >= A.LEARN_MIN_MARGIN and self.memory is not None:
            self.memory.learn(m, item_id)
        return item_id, ratio, margin, texts

    def sonar_decide(self, sct, rd, pos):
        """Прочитать надпись сонара: (id, ловить ли) или None — надписи нет / не узнали."""
        tw, th = self.tw, self.th
        bx, by = pos[0] - rd.reg["left"], pos[1] - rd.reg["top"]
        frame = A.grab(sct, rd.reg)
        res = self.read_name(rd, frame, (bx - tw // 2 - 6, by - th // 2 - 6, bx + tw // 2 + 6, by + th // 2 + 6))
        self.n += 1
        if rd.present:
            self.save_dbg("%03d_sonar.png" % self.n, frame, scale=2)
        if rd.last_img is not None:
            self.save_dbg("%03d_sonar_ocr.png" % self.n, np.dstack([rd.last_img] * 3).astype(np.float32))
        if res is None:
            return None
        item_id, ratio, margin, texts = res
        if item_id is None:
            if texts:
                self.log(tr("Сонар: «%s» — не узнал предмет, подсекаю.") % texts[0])
                self.heat_hint()
            return None
        self.recent_catch.append(item_id)
        biome = self.current_biome()
        wanted = not A.CATCH_WANT or self.catches.wanted(item_id, A.CATCH_WANT, biome) or item_id == A.QUEST_FISH
        if not wanted and (ratio < A.SKIP_MIN_RATIO or margin < A.SKIP_MIN_MARGIN):
            # отпускать можно только уверенно прочитанное — иначе можно упустить нужное
            self.log(tr("Сонар: похоже на «%s», но не уверен — подсекаю.") % self.catch_name(item_id))
            wanted = True
        self.emit("catch", id=item_id, name=self.catch_name(item_id), wanted=wanted, biome=biome)
        return item_id, wanted

    def pickup_start(self, sct, cl, player):
        """Перед подсечкой: снимок места над персонажем, где появится надпись о подборе. Нужен и без
        OCR: по тому, появилась ли надпись, видно, что инвентарь полон."""
        if not (A.READ_PICKUP or A.INV_FULL_STOP):
            return None
        import sonar
        rd = sonar.PickupReader(self.scale)
        rd.reg = rd.region(player, cl)
        rd.set_base(A.grab(sct, rd.reg))
        return rd

    def pickup_read(self, sct, rd):
        """После подсечки: что поймано (надпись о подборе над персонажем). Для учёта и угадывания
        биома. id или None."""
        frame = A.grab(sct, rd.reg)
        res = self.read_name(rd, frame, use_ocr=A.READ_PICKUP) if self.catches is not None else rd.extract(frame)
        self.n += 1
        if rd.present:
            self.save_dbg("%03d_podbor.png" % self.n, frame, scale=2)
        if rd.last_img is not None:
            self.save_dbg("%03d_podbor_ocr.png" % self.n, np.dstack([rd.last_img] * 3).astype(np.float32))
        self.check_inventory(rd.present)
        item_id = res[0] if isinstance(res, tuple) else None
        if item_id is None:
            self.caught_unknown += 1
            self.emit("catch", id=None, name=None, wanted=True, biome=self.current_biome(), caught=True)
            return None
        self.recent_catch.append(item_id)
        self.caught[item_id] = self.caught.get(item_id, 0) + 1
        self.log(tr("Поймал: %s.") % self.catch_name(item_id), "good")
        self.emit("catch", id=item_id, name=self.catch_name(item_id), wanted=True, biome=self.current_biome(),
                  caught=True)
        return item_id

    def check_inventory(self, present):
        """Надписи о подборе нет INV_FULL_HOOKS подсечек подряд, хотя раньше она была, — похоже,
        инвентарь полон (улов падает на землю)."""
        if present:
            self.pickup_seen, self.no_pickup = True, 0
            return
        self.no_pickup += 1
        if not (A.INV_FULL_STOP and self.pickup_seen and self.no_pickup >= A.INV_FULL_HOOKS):
            return
        self.no_pickup = 0
        self.log(tr("Улов перестал подбираться %d раз подряд — похоже, инвентарь полон.") % A.INV_FULL_HOOKS, "bad")
        self.pause(tr("инвентарь полон"))

    def check_sonar_buff(self, sct, cl):
        """Выбор улова включён, а баффа сонара нет — надписи не будет: предупредить (раз в 5 минут)."""
        if not A.SONAR_FILTER or self.buffs is None or "sonar" not in self.buffs.icons:
            return
        now = time.time()
        if now - self.last_sonar_check < 30:
            return
        self.last_sonar_check = now
        region = {"left": cl[0], "top": cl[1], "width": min(cl[2] - cl[0], 900),
                  "height": min(cl[3] - cl[1], 360)}
        if self.buffs.find(A.grab(sct, region)).get("sonar", 0) >= A.BUFF_THRESHOLD():
            return
        if now - self.sonar_buff_warned > 300:
            self.sonar_buff_warned = now
            self.log(tr("Нет баффа сонара — выбирать улов не по чему, подсекаю всё. Выпейте зелье сонара."), "bad")
            self.emit("notify", title=tr("Сонар"), text=tr("Нет баффа сонара — выбор улова не работает."))
