"""
История улова между запусками: по дням — сколько подсечек, что поймано (по надписям о подборе),
сколько не узнано и сколько отпущено по сонару. Хранится в catch_history.json рядом с настройками.
"""
import datetime
import json
import os

PERIODS = ("session", "today", "week", "all")      # за сессию / сегодня / 7 дней / всё время


def today():
    return datetime.date.today().isoformat()


class History:
    def __init__(self, path=None):
        self.path = path                 # None — только в памяти (самопроверка, тесты)
        self.days = {}                   # "2026-09-26" -> {"hooks", "unknown", "skipped", "items": {id: n}}
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    self.days = json.load(fh).get("days", {})
            except Exception:
                self.days = {}

    def day(self, day=None):
        return self.days.setdefault(day or today(), {"hooks": 0, "unknown": 0, "skipped": 0, "items": {}})

    def add_hook(self, day=None):
        self.day(day)["hooks"] += 1
        self.save()

    def add_skip(self, day=None):
        self.day(day)["skipped"] += 1
        self.save()

    def add_catch(self, item_id, day=None):
        d = self.day(day)
        if item_id is None:
            d["unknown"] += 1
        else:
            d["items"][str(item_id)] = d["items"].get(str(item_id), 0) + 1
        self.save()

    def totals(self, period, now=None):
        """Сумма за период ("today", "week" — последние 7 дней, "all"): {"hooks", "unknown",
        "skipped", "items": {id (int): n}, "days": сколько дней рыбачили}."""
        now = now or datetime.date.today()
        first = {"today": now, "week": now - datetime.timedelta(days=6)}.get(period)
        out = {"hooks": 0, "unknown": 0, "skipped": 0, "items": {}, "days": 0}
        for key, d in self.days.items():
            try:
                date = datetime.date.fromisoformat(key)
            except ValueError:
                continue
            if first is not None and not first <= date <= now:
                continue
            out["days"] += 1
            for k in ("hooks", "unknown", "skipped"):
                out[k] += int(d.get(k, 0))
            for i, n in d.get("items", {}).items():
                out["items"][int(i)] = out["items"].get(int(i), 0) + int(n)
        return out

    def save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"days": self.days}, fh, ensure_ascii=False)
            os.replace(tmp, self.path)       # целиком или никак: файл не бывает недописанным
        except Exception:
            pass
