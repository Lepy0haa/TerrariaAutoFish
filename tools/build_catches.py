"""
Собирает assets/fishing/catches.json — что можно поймать в каждом биоме — с Terraria Wiki:
  * https://terraria.wiki.gg/wiki/Fishing_catches — таблицы улова по биомам (номера предметов);
  * https://terraria.wiki.gg/ru/wiki/Идентификаторы_предметов — номер -> русское и английское название.

Запуск: python tools/build_catches.py   (нужен интернет; результат кладётся в assets/fishing)
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "fishing", "catches.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# группы таблицы -> ключ, название по-русски; порядок — как в интерфейсе
GROUPS = [
    ("Pure biome", "forest", "Лес (обычный биом)"),
    ("Ocean", "ocean", "Океан"),
    ("Jungle", "jungle", "Джунгли"),
    ("Snow", "snow", "Снега"),
    ("Desert", "desert", "Пустыня"),
    ("Corruption", "corruption", "Порча"),
    ("Crimson", "crimson", "Багрянец"),
    ("Hallow", "hallow", "Святые земли"),
    ("Hallowed Desert", "hallowed_desert", "Святая пустыня"),
    ("Glowing Mushroom biome", "mushroom", "Светящиеся грибы"),
    ("Dungeon", "dungeon", "Темница"),
    ("Space", "space", "Космос"),
    ("Lava", "lava", "Лава"),
    ("Honey", "honey", "Мёд"),
    ("Crate", "crates", "Ящики (везде)"),
    ("Rare items", "rare", "Редкое (везде)"),
    ("Junk", "junk", "Мусор (везде)"),
]
SKIP = {"Enemy", "Truffle Worm", "Quest fish (Remix)"}
# биом в столбце «Other conditions» у ящиков -> ключ биома
CRATE_BIOMES = {"Dungeon": "dungeon", "Ocean": "ocean", "Beach": "ocean", "Corruption": "corruption",
                "Crimson": "crimson", "Hallow": "hallow", "Jungle": "jungle", "Snow": "snow",
                "Desert": "desert", "Sky": "space", "Space": "space", "Underworld": "lava"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def parse_page(api, page):
    q = urllib.parse.urlencode({"action": "parse", "page": page, "prop": "text", "format": "json"})
    return json.loads(get("%s?%s" % (api, q)))["parse"]["text"]["*"]


def text_of(fragment):
    alts = " ".join(re.findall(r'alt="([^"]*)"', fragment))
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment) + " " + alts)


def names_by_id():
    t = parse_page("https://terraria.wiki.gg/ru/api.php", "Идентификаторы_предметов")
    out = {}
    for m in re.finditer(r"<tr><td>(\d+)</td><td>(.*?)</td><td>(.*?)</td>", t):
        ru = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        en = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        out[int(m.group(1))] = {"ru": ru, "en": en}
    return out


def tables():
    t = parse_page("https://terraria.wiki.gg/api.php", "Fishing_catches")
    for tbl in re.findall(r'<table class="terraria lined mw-collapsible".*?</table>', t, re.S):
        cap = re.search(r'class="mw-headline" id="[^"]*">([^<]+)<', tbl) or re.search(r"<caption>(.*?)<", tbl, re.S)
        name = html.unescape(re.sub(r"<[^>]+>", "", cap.group(1))).strip() if cap else "?"
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", tbl, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 5:
                continue
            ids = [int(i) for i in re.findall(r"Item ID</a>:\s*(\d+)", tds[0])]
            quality = re.split(r"\s*Bestiary", re.sub(r"\s+", " ", text_of(tds[2])).strip())[0]
            heights = [h for h in ("Space", "Surface", "Underground", "Cavern", "Underworld", "Any")
                       if h in text_of(tds[3])]
            cond = re.sub(r"\s+", " ", text_of(tds[4])).strip()
            rows.append({"ids": ids, "quality": quality, "heights": heights, "cond": cond})
        yield name, rows


def main():
    names = names_by_id()
    groups = {key: {"key": key, "en": en, "ru": ru, "items": []} for en, key, ru in GROUPS}
    seen = {key: set() for _, key, _ in GROUPS}
    by_en = {en: key for en, key, _ in GROUPS}

    def add(key, item_id, row):
        if item_id in seen[key] or item_id not in names:
            return
        seen[key].add(item_id)
        cond = row["cond"]
        groups[key]["items"].append({
            "id": item_id, "en": names[item_id]["en"], "ru": names[item_id]["ru"],
            "quality": row["quality"], "heights": row["heights"],
            "hardmode": "Hardmode" in cond and "Pre-Hardmode" not in cond,
            "quest": "quest" in cond.lower(),
            "crate": "Crate" in names[item_id]["en"] or "Box" in names[item_id]["en"],
        })

    for name, rows in tables():
        if name in SKIP or name not in by_en:
            continue
        key = by_en[name]
        for row in rows:
            for item_id in row["ids"]:
                add(key, item_id, row)
                if key == "crates":            # ящики биомов — ещё и в список своего биома
                    for word, biome in CRATE_BIOMES.items():
                        if word in row["cond"]:
                            add(biome, item_id, row)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {"source": "https://terraria.wiki.gg/wiki/Fishing_catches",
            "groups": [groups[key] for _, key, _ in GROUPS]}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    for g in data["groups"]:
        print("%-18s %3d  %s" % (g["key"], len(g["items"]), ", ".join(i["ru"] for i in g["items"][:6])))


if __name__ == "__main__":
    main()
