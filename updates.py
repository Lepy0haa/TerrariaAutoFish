"""
Проверка обновлений: последний релиз на GitHub (без входа в аккаунт, публичный API).
"""
import json
import re
import urllib.request

REPO = "Lepy0haa/TerrariaAutoFish"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO


def parse_version(text):
    """"v1.3.2" / "1.3.2" -> (1, 3, 2); непонятное -> ()."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def latest(timeout=10):
    """(версия, адрес страницы релиза) последнего релиза. Исключение — если GitHub недоступен."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "TerrariaAutoFish"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("tag_name", ""), data.get("html_url") or PAGE


def newer(current, timeout=10):
    """(версия, адрес) если на GitHub есть версия новее current, иначе None."""
    tag, url = latest(timeout)
    if parse_version(tag) > parse_version(current):
        return tag.lstrip("v"), url
    return None
