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
    """(версия, адрес страницы релиза, файлы) последнего релиза; файлы — {"setup": ..., "portable": ...},
    каждый {"name", "url", "size"} (чего нет — того нет). Исключение — если GitHub недоступен."""
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    files = {}
    for a in data.get("assets") or []:
        if not a.get("browser_download_url", "").startswith("https://github.com/%s/releases/download/" % REPO):
            continue
        for kind, end in (("setup", "-setup.exe"), ("portable", "-portable.zip")):
            if a.get("name", "").endswith(end):
                files[kind] = {"name": a["name"], "url": a["browser_download_url"], "size": int(a.get("size") or 0)}
    return data.get("tag_name", ""), data.get("html_url") or PAGE, files


def newer(current, timeout=10):
    """(версия, адрес, файлы) если на GitHub есть версия новее current, иначе None."""
    tag, url, files = latest(timeout)
    if parse_version(tag) > parse_version(current):
        return tag.lstrip("v"), url, files or {}
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


def extract_portable(zip_path, folder):
    """Распаковать портативную версию: папка, где лежит TerrariaAutoFish.exe."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(folder)
    for root, _, names in os.walk(folder):
        if "TerrariaAutoFish.exe" in names:
            return root
    raise IOError("TerrariaAutoFish.exe not found in the archive")


def portable_update_command(src, dest, pid, start=True):
    """Команда, которая дождётся закрытия программы (pid), заменит её файлы в dest новыми из src
    (папки settings и data не трогаются — их нет в архиве) и снова запустит программу.
    PowerShell с -EncodedCommand — пути с русскими буквами и пробелами не ломаются."""
    import base64

    def q(path):
        return "'" + path.replace("'", "''") + "'"
    script = (
        "$p = %d; while (Get-Process -Id $p -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }; "
        "Start-Sleep -Milliseconds 700; "
        "Remove-Item -LiteralPath (Join-Path %s '_internal') -Recurse -Force -ErrorAction SilentlyContinue; "
        "Copy-Item -Path (Join-Path %s '*') -Destination %s -Recurse -Force; " % (int(pid), q(dest), q(src), q(dest)))
    if start:
        script += "Start-Process -FilePath (Join-Path %s 'TerrariaAutoFish.exe')" % q(dest)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]
