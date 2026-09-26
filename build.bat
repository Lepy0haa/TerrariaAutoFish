@echo off
rem Builds TerrariaAutoFish.exe, the installer and the portable zip into the dist folder.
rem Requires Python 3.10+.
cd /d "%~dp0"
set VER=1.2.1
python -m pip install -r requirements.txt pyinstaller || goto :error
python app.py --make-icon "%~dp0icon.ico" || goto :error

python -m PyInstaller --noconfirm --onefile --windowed --name TerrariaAutoFish --icon "%~dp0icon.ico" ^
  --add-data "%~dp0assets;assets" --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --exclude-module PIL --distpath "%~dp0dist" --workpath "%~dp0_build" --specpath "%~dp0_build" app.py || goto :error

python -m PyInstaller --noconfirm --onefile --windowed --name TerrariaAutoFish-%VER%-setup --icon "%~dp0icon.ico" ^
  --add-data "%~dp0dist\TerrariaAutoFish.exe;payload" --add-data "%~dp0icon.ico;." --exclude-module PIL --exclude-module numpy ^
  --distpath "%~dp0dist" --workpath "%~dp0_build" --specpath "%~dp0_build" installer.py || goto :error

rmdir /s /q "%~dp0dist\portable" 2>nul
mkdir "%~dp0dist\portable\TerrariaAutoFish"
copy /y "%~dp0dist\TerrariaAutoFish.exe" "%~dp0dist\portable\TerrariaAutoFish\" >nul
copy /y "%~dp0portable_note.txt" "%~dp0dist\portable\TerrariaAutoFish\portable.txt" >nul
copy /y "%~dp0README.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
copy /y "%~dp0README.ru.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path '%~dp0dist\portable\TerrariaAutoFish' -DestinationPath '%~dp0dist\TerrariaAutoFish-%VER%-portable.zip'" || goto :error
rmdir /s /q "%~dp0dist\portable" "%~dp0_build"
del "%~dp0icon.ico"
echo.
echo Done: dist\TerrariaAutoFish-%VER%-setup.exe and dist\TerrariaAutoFish-%VER%-portable.zip
pause
exit /b 0

:error
echo Build failed.
pause
exit /b 1
