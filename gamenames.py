"""
Названия предметов так, как их пишет сама игра. Русские названия на Вики часто не совпадают с
переводом в игре («Обсидиановая рыба» — в игре «Обсидирыба», «Карп-огнепёрка» — «Золотоперый
карп»), а надписи сонара и подбора игра пишет своими. Поэтому таблицы названий берём прямо из
установленной Terraria.exe (там лежат файлы перевода Items.json) — у каждого свои, ничего чужого
программа с собой не возит.
"""
import ctypes
import json
import os
import re
from ctypes import wintypes as wt

_cache = {}


def _norm(name):
    """Английское название для сравнения: без регистра, апострофов и лишних пробелов."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z ]+", "", name.lower())).strip()


def _running_exe():
    """Путь к запущенной Terraria.exe (или None)."""
    TH32CS_SNAPPROCESS = 0x2

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD), ("szExeFile", wt.WCHAR * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wt.HANDLE(-1).value:
        return None
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == "terraria.exe":
                h = k32.OpenProcess(0x1000, False, e.th32ProcessID)     # PROCESS_QUERY_LIMITED_INFORMATION
                if h:
                    try:
                        buf, size = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
                        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                            return buf.value
                    finally:
                        k32.CloseHandle(h)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return None


def _steam_exes():
    """Terraria.exe во всех библиотеках Steam."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = winreg.QueryValueEx(k, "SteamPath")[0]
    except Exception:
        steam = r"C:\Program Files (x86)\Steam"
    libs = [steam]
    try:
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as fh:
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', fh.read())]
    except Exception:
        pass
    return [os.path.join(lib, "steamapps", "common", "Terraria", "Terraria.exe") for lib in libs]


def find_exe():
    """Где установлена игра: запущенная, иначе из Steam. None — не нашли."""
    try:
        p = _running_exe()
    except Exception:
        p = None
    for c in [p] + _steam_exes():
        if c and os.path.isfile(c):
            return os.path.normpath(c)
    return None


def read_tables(data):
    """Все таблицы ItemName из байтов Terraria.exe: [{внутреннее имя: название}]."""
    dec = json.JSONDecoder()
    tables = []
    for m in re.finditer(rb'"ItemName"\s*:\s*\{', data):
        text = data[m.end() - 1:m.end() - 1 + 1500000].decode("utf-8", "replace")
        text = re.sub(r",(\s*\})", r"\1", text)          # в файлах игры бывают лишние запятые
        try:
            table, _ = dec.raw_decode(text)
        except ValueError:
            continue
        if isinstance(table, dict) and len(table) > 1000:
            tables.append(table)
    return tables


def english_to_russian(tables):
    """{английское название (для сравнения): русское название} по таблицам игры."""
    en = next((t for t in tables if t.get("IronPickaxe") == "Iron Pickaxe"), None)
    ru = next((t for t in tables if re.search("[а-яА-Я]", t.get("IronPickaxe", ""))), None)
    if en is None or ru is None:
        return {}
    out = {}
    for key, name in en.items():
        r = ru.get(key)
        if isinstance(name, str) and isinstance(r, str) and r and "{" not in r:
            out.setdefault(_norm(name), r)
    return out


def load(exe=None):
    """{английское название: русское название из игры} или {} (игра не найдена, не прочиталось).
    Читается за доли секунды; прочитанное помним до конца работы программы."""
    exe = exe or find_exe()
    if not exe:
        return {}
    try:
        st = os.stat(exe)
        stamp = (exe.lower(), st.st_size, int(st.st_mtime))
        if stamp not in _cache:
            with open(exe, "rb") as fh:
                _cache[stamp] = english_to_russian(read_tables(fh.read()))
        return _cache[stamp]
    except Exception:
        return {}


def lookup(names, english):
    """Русское название предмета из игры по английскому (или None)."""
    return names.get(_norm(english))
