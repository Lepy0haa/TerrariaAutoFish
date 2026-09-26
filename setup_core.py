"""
Установка и удаление Terraria AutoFish (для текущего пользователя, без прав администратора).
Используется установщиком (installer.py) и самой программой (TerrariaAutoFish.exe --uninstall).
"""
import os
import shutil
import subprocess
import winreg

APP_NAME = "Terraria AutoFish"
EXE_NAME = "TerrariaAutoFish.exe"
PUBLISHER = "Lepy0haa"
URL = "https://github.com/Lepy0haa/TerrariaAutoFish"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TerrariaAutoFish"
NO_WINDOW = 0x08000000


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", "TerrariaAutoFish")


def settings_dir():
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "TerrariaAutoFish")


def _powershell(script):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          creationflags=NO_WINDOW, capture_output=True, text=True, timeout=60)


def _ps_str(s):
    return "'" + s.replace("'", "''") + "'"


def make_shortcuts(target, desktop=True, start_menu=True):
    """Ярлыки на рабочем столе и в меню «Пуск» (папки берём у Windows — с учётом OneDrive)."""
    places = []
    if desktop:
        places.append("[Environment]::GetFolderPath('Desktop')")
    if start_menu:
        places.append("[Environment]::GetFolderPath('Programs')")
    if not places:
        return
    script = "$w = New-Object -ComObject WScript.Shell;"
    for place in places:
        script += ("$l = $w.CreateShortcut((Join-Path %s %s)); $l.TargetPath = %s; "
                   "$l.WorkingDirectory = %s; $l.IconLocation = %s; $l.Save();"
                   % (place, _ps_str(APP_NAME + ".lnk"), _ps_str(target),
                      _ps_str(os.path.dirname(target)), _ps_str(target + ",0")))
    _powershell(script)


def remove_shortcuts():
    _powershell("foreach ($p in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')))"
                " { Remove-Item -LiteralPath (Join-Path $p %s) -ErrorAction SilentlyContinue }"
                % _ps_str(APP_NAME + ".lnk"))


def register(install_dir, version):
    """Запись в «Приложения и возможности» Windows (раздел текущего пользователя)."""
    exe = os.path.join(install_dir, EXE_NAME)
    size_kb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(install_dir) for f in fs) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        for name, value in (("DisplayName", APP_NAME), ("DisplayVersion", version), ("Publisher", PUBLISHER),
                            ("InstallLocation", install_dir), ("DisplayIcon", exe + ",0"),
                            ("URLInfoAbout", URL), ("UninstallString", '"%s" --uninstall' % exe)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)


def unregister():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except OSError:
        pass


def installed_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            return winreg.QueryValueEx(k, "InstallLocation")[0]
    except OSError:
        return None


def install(payload_exe, install_dir, version, desktop=True, start_menu=True, add_to_windows=True):
    """Скопировать программу и (по желанию) создать ярлыки и запись в «Приложения»."""
    os.makedirs(install_dir, exist_ok=True)
    target = os.path.join(install_dir, EXE_NAME)
    shutil.copy2(payload_exe, target)          # PermissionError — если программа сейчас запущена
    for old in ("portable.txt",):              # установленная версия хранит настройки в %APPDATA%
        try:
            os.remove(os.path.join(install_dir, old))
        except OSError:
            pass
    make_shortcuts(target, desktop, start_menu)
    if add_to_windows:
        register(install_dir, version)
    return target


def uninstall(install_dir, remove_settings=False):
    """Удалить ярлыки, запись в «Приложения» и папку программы. Файл, из которого идёт
    удаление, ещё занят — папку удаляет отдельный процесс через пару секунд."""
    remove_shortcuts()
    unregister()
    if remove_settings:
        shutil.rmtree(settings_dir(), ignore_errors=True)
    subprocess.Popen('cmd /c ping 127.0.0.1 -n 3 > nul & rmdir /s /q "%s"' % install_dir,
                     creationflags=NO_WINDOW, close_fds=True)
