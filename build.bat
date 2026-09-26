@echo off
rem Builds the program (folder TerrariaAutoFish: exe + _internal), the installer and the portable zip into dist.
rem Requires Python 3.10+. "build.bat --no-pause" does not wait for a key at the end (automatic builds).
cd /d "%~dp0"
set VER=1.4.0
set NOPAUSE=
if "%~1"=="--no-pause" set NOPAUSE=1
python -m pip install -r requirements.txt pyinstaller || goto :error
python app.py --make-icon "%~dp0icon.ico" || goto :error
if not exist "%~dp0_build" mkdir "%~dp0_build"
python app.py --make-version "%~dp0_build\app_version.txt" "Terraria AutoFish" TerrariaAutoFish.exe || goto :error
python app.py --make-version "%~dp0_build\setup_version.txt" "Terraria AutoFish Setup" TerrariaAutoFish-%VER%-setup.exe || goto :error

rem The program is a folder, not a single self-extracting exe: antivirus programs trust it more and it starts faster.
rmdir /s /q "%~dp0dist\TerrariaAutoFish" 2>nul
python -m PyInstaller --noconfirm --windowed --noupx --name TerrariaAutoFish --icon "%~dp0icon.ico" ^
  --version-file "%~dp0_build\app_version.txt" ^
  --add-data "%~dp0assets;assets" --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --collect-submodules winrt --hidden-import ocr --hidden-import sonar --hidden-import catches ^
  --exclude-module PIL --distpath "%~dp0dist" --workpath "%~dp0_build" --specpath "%~dp0_build" app.py || goto :error

python -m PyInstaller --noconfirm --onefile --windowed --noupx --name TerrariaAutoFish-%VER%-setup --icon "%~dp0icon.ico" ^
  --version-file "%~dp0_build\setup_version.txt" ^
  --add-data "%~dp0dist\TerrariaAutoFish;payload" --add-data "%~dp0icon.ico;." --exclude-module PIL --exclude-module numpy ^
  --distpath "%~dp0dist" --workpath "%~dp0_build" --specpath "%~dp0_build" installer.py || goto :error

rmdir /s /q "%~dp0dist\portable" 2>nul
mkdir "%~dp0dist\portable"
xcopy /e /i /q /y "%~dp0dist\TerrariaAutoFish" "%~dp0dist\portable\TerrariaAutoFish" >nul || goto :error
copy /y "%~dp0portable_note.txt" "%~dp0dist\portable\TerrariaAutoFish\portable.txt" >nul
copy /y "%~dp0README.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
copy /y "%~dp0README.ru.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path '%~dp0dist\portable\TerrariaAutoFish' -DestinationPath '%~dp0dist\TerrariaAutoFish-%VER%-portable.zip'" || goto :error
rmdir /s /q "%~dp0dist\portable" "%~dp0_build"
del "%~dp0icon.ico"
echo.
echo Done: dist\TerrariaAutoFish-%VER%-setup.exe and dist\TerrariaAutoFish-%VER%-portable.zip
if not defined NOPAUSE pause
exit /b 0

:error
echo Build failed.
if not defined NOPAUSE pause
exit /b 1
