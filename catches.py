"""
Что можно поймать в каждом биоме (assets/fishing/catches.json, собран с Terraria Wiki скриптом
tools/build_catches.py) и какой это предмет по надписи зелья сонара.

Надпись читается OCR и бывает с ошибками (похожие буквы, латиница вместо кириллицы), поэтому
название ищется «примерно»: нормализуем и сравниваем со всеми известными названиями.
"""
import difflib
import json
import os
import re

# латинские буквы, похожие на русские (OCR их путает)
LOOKALIKE = str.maketrans("aeopcxykmthbABEKMHOPCTXY", "аеорсхукмтнвАВЕКМНОРСТХУ")


def normalize(text, cyrillic=None):
    """Для сравнения: нижний регистр, ё -> е, без кавычек и знаков, похожая латиница -> кириллица
    (если в строке больше кириллицы)."""
    t = text.replace("ё", "е").replace("Ё", "Е")
    if cyrillic is None:
        cyr = len(re.findall(r"[а-яА-Я]", t))
        cyrillic = cyr > len(re.findall(r"[a-zA-Z]", t))
    if cyrillic:
        t = t.translate(LOOKALIKE)
    t = re.sub(r"[^0-9a-zа-я ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


class Catches:
    def __init__(self, path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.groups = data["groups"]                      # [{key, en, ru, items: [...]}]
        self.group = {g["key"]: g for g in self.groups}
        self.items = {}                                   # id -> предмет
        self.where = {}                                   # id -> [ключи групп, где он есть]
        for g in self.groups:
            for it in g["items"]:
                self.items[it["id"]] = it
                self.where.setdefault(it["id"], []).append(g["key"])
        self.names = []                                   # (нормализованное название, id)
        for i, it in self.items.items():
            for lang in ("ru", "en"):
                self.names.append((normalize(it[lang], lang == "ru"), i))

    def biomes(self):
        """Группы-биомы (не «везде»)."""
        return [g for g in self.groups if g["key"] not in ("crates", "rare", "junk")]

    def identify(self, text, min_ratio=0.72):
        """По прочитанной надписи: (id, похожесть) или (None, похожесть лучшего)."""
        t = normalize(text)
        if len(t) < 3:
            return None, 0.0
        best, best_id = 0.0, None
        for name, i in self.names:
            r = difflib.SequenceMatcher(None, t, name).ratio()
            if r > best:
                best, best_id = r, i
        return (best_id, best) if best >= min_ratio else (None, best)

    def guess_biome(self, ids):
        """Где рыбачим — по тому, что клевало: биом, где встречается больше всего из ids
        (предметы «везде» — ящики, мусор, редкое — не считаются). None — непонятно."""
        score = {}
        for i in ids:
            homes = [k for k in self.where.get(i, []) if k not in ("crates", "rare", "junk")]
            for k in homes:
                score[k] = score.get(k, 0) + 1.0 / len(homes)
        if not score:
            return None
        return max(score, key=score.get)

    def wanted(self, item_id, want, biome=None):
        """Ловить ли предмет. want — {ключ группы: [id, ...] отмеченных}. Сначала смотрим список
        текущего биома (если предмет там есть), потом списки «везде», потом любые другие."""
        homes = self.where.get(item_id, [])
        order = ([biome] if biome in homes else []) + [k for k in ("crates", "rare", "junk") if k in homes] + homes
        for k in order:
            if k in want:
                return item_id in want[k]
        return True                                       # ни в одном списке не настроен — ловим

    def default_want(self):
        """По умолчанию ловим всё."""
        return {g["key"]: [it["id"] for it in g["items"]] for g in self.groups}
