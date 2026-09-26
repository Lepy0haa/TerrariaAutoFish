"""
Проверка обновлений: последний релиз на GitHub (без входа в аккаунт, публичный API), и загрузка
установщика новой версии — для обновления в один клик.
"""
import json
import os
import re
import urllib.request

REPO = "Lepy0haa/TerrariaAutoFish"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "TerrariaAutoFish"}


def parse_version(text):
    """"v1.3.2" / "1.3.2" -> (1, 3, 2); непонятное -> ()."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def latest(timeout=10):
    """(версия, адрес страницы релиза, установщик) последнего релиза; установщик — {"name", "url",
    "size"} или None. Исключение — если GitHub недоступен."""
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    setup = None
    for a in data.get("assets") or []:
        if a.get("name", "").endswith("-setup.exe") and a.get("browser_download_url", "").startswith(
                "https://github.com/%s/releases/download/" % REPO):
            setup = {"name": a["name"], "url": a["browser_download_url"], "size": int(a.get("size") or 0)}
    return data.get("tag_name", ""), data.get("html_url") or PAGE, setup


def newer(current, timeout=10):
    """(версия, адрес, установщик) если на GitHub есть версия новее current, иначе None."""
    tag, url, setup = latest(timeout)
    if parse_version(tag) > parse_version(current):
        return tag.lstrip("v"), url, setup
    return None


def download(setup, folder, progress=None, timeout=30):
    """Скачать установщик в folder: путь к файлу. Размер сверяется с тем, что сообщил GitHub
    (недокачанный файл не запускаем). progress(доля 0..1) — по ходу."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.basename(setup["name"]))
    part = path + ".part"
    req = urllib.request.Request(setup["url"], headers={"User-Agent": HEADERS["User-Agent"]})
    done = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as fh:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress and setup["size"]:
                progress(min(1.0, done / float(setup["size"])))
    if setup["size"] and done != setup["size"]:
        os.remove(part)
        raise IOError("downloaded %d of %d bytes" % (done, setup["size"]))
    os.replace(part, path)
    return path
