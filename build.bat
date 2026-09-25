@echo off
rem Build TerrariaAutoFish.exe (requires Python 3.10+)
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python app.py --make-icon "%~dp0icon.ico"
python -m PyInstaller --noconfirm --onefile --windowed --name TerrariaAutoFish --icon "%~dp0icon.ico" ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 --exclude-module PIL ^
  --distpath "%~dp0." --workpath "%~dp0_build" --specpath "%~dp0_build" app.py
rmdir /s /q _build
del icon.ico
pause
