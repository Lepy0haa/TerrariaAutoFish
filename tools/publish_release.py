"""
Выложить релиз на GitHub от своего аккаунта (а не от «github-actions[bot]»).

Автосборка на GitHub по метке версии (v1.2.3) собирает установщик и портативную версию и
прикладывает их к своему запуску. Этот скрипт находит этот запуск, скачивает собранные файлы и
создаёт релиз с описанием из docs/releases/<метка>.md — от имени того, кто вошёл в GitHub в git
на этом компьютере (токен берётся у git: git credential fill, никуда не записывается).

    python tools/publish_release.py v1.5.0            # файлы из автосборки
    python tools/publish_release.py v1.5.0 --local    # файлы из папки dist (собраны build.bat)
    python tools/publish_release.py v1.4.0 --recreate # пересоздать уже выложенный релиз с теми же файлами
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Lepy0haa/TerrariaAutoFish"
API = "https://api.github.com/repos/" + REPO


def token():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, timeout=60, cwd=ROOT).stdout
    creds = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return creds["password"]


def api(method, url, tok, data=None, ctype="application/json"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": ctype, "User-Agent": "TerrariaAutoFish-release"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, json.loads(body) if body else {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(url, tok):
    """Скачать файл с API GitHub: он отвечает перенаправлением на хранилище, куда токен не нужен."""
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok, "User-Agent": "TerrariaAutoFish",
                                               "Accept": "application/octet-stream"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=600) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        with urllib.request.urlopen(e.headers["Location"], timeout=600) as r:
            return r.read()


def files_from_build(tag, tok):
    """{имя: байты} установщика и портативной версии из успешной автосборки по метке tag."""
    st, runs = api("GET", API + "/actions/runs?event=push&per_page=30", tok)
    run = next((r for r in runs.get("workflow_runs", []) if r["head_branch"] == tag and r["conclusion"] == "success"),
               None)
    if run is None:
        raise SystemExit("Нет успешной автосборки для %s — дождитесь её (вкладка Actions на GitHub)." % tag)
    st, arts = api("GET", run["artifacts_url"], tok)
    files = {}
    for a in arts.get("artifacts", []):
        with zipfile.ZipFile(io.BytesIO(fetch(a["archive_download_url"], tok))) as z:
            for name in z.namelist():
                files[os.path.basename(name)] = z.read(name)
    return files


def files_from_dist(tag):
    ver = tag.lstrip("v")
    names = ["TerrariaAutoFish-%s-setup.exe" % ver, "TerrariaAutoFish-%s-portable.zip" % ver]
    return {n: open(os.path.join(ROOT, "dist", n), "rb").read() for n in names}


def files_from_release(rel, tok):
    return {a["name"]: fetch(a["url"], tok) for a in rel.get("assets", [])}


def main():
    args = sys.argv[1:]
    if not args or not args[0].startswith("v"):
        raise SystemExit(__doc__)
    tag = args[0]
    ver = tag.lstrip("v")
    with open(os.path.join(ROOT, "docs", "releases", tag + ".md"), encoding="utf-8") as fh:
        body = fh.read()
    tok = token()
    st, rel = api("GET", API + "/releases/tags/" + tag, tok)
    if "--recreate" in args:
        if st != 200:
            raise SystemExit("Релиза %s нет." % tag)
        files = files_from_release(rel, tok)
        print("скачаны файлы релиза:", ", ".join("%s (%.1f МБ)" % (n, len(b) / 2 ** 20) for n, b in files.items()))
        st, _ = api("DELETE", API + "/releases/%d" % rel["id"], tok)      # метка остаётся
        print("старый релиз удалён:", st)
    elif st == 200:
        raise SystemExit("Релиз %s уже есть: %s" % (tag, rel["html_url"]))
    else:
        files = files_from_dist(tag) if "--local" in args else files_from_build(tag, tok)
    wanted = ["TerrariaAutoFish-%s-setup.exe" % ver, "TerrariaAutoFish-%s-portable.zip" % ver]
    missing = [n for n in wanted if n not in files]
    if missing:
        raise SystemExit("Нет файлов: %s" % ", ".join(missing))
    payload = json.dumps({"tag_name": tag, "name": "Terraria AutoFish " + ver, "body": body,
                          "draft": False, "prerelease": False, "make_latest": "true"}).encode()
    st, rel = api("POST", API + "/releases", tok, payload)
    if st != 201:
        raise SystemExit("Не создался релиз: %s %s" % (st, rel.get("message")))
    for name in wanted:
        ctype = "application/zip" if name.endswith(".zip") else "application/vnd.microsoft.portable-executable"
        url = "https://uploads.github.com/repos/%s/releases/%d/assets?name=%s" % (REPO, rel["id"], name)
        st, a = api("POST", url, tok, files[name], ctype)
        print("  %s: %s, %.1f МБ" % (name, st, (a.get("size") or 0) / 2 ** 20))
    print("релиз:", rel["html_url"], "— автор:", rel["author"]["login"])


if __name__ == "__main__":
    main()
