@echo off
rem Builds the program (folder TerrariaAutoFish: exe + _internal), the installer and the portable zip into dist,
rem and puts the fresh program (TerrariaAutoFish.exe + _internal) into the project folder (if it is not running).
rem Requires Python 3.10+. "build.bat --no-pause" does not wait for a key at the end (automatic builds).
cd /d "%~dp0"
set VER=1.5.1
set NOPAUSE=
if "%~1"=="--no-pause" set NOPAUSE=1
set WORK=%~dp0dist\_build
python -m pip install -r requirements.txt pyinstaller || goto :error
if not exist "%WORK%" mkdir "%WORK%"
python src\app.py --make-icon "%WORK%\icon.ico" || goto :error
python src\app.py --make-version "%WORK%\app_version.txt" "Terraria AutoFish" TerrariaAutoFish.exe || goto :error
python src\app.py --make-version "%WORK%\setup_version.txt" "Terraria AutoFish Setup" TerrariaAutoFish-%VER%-setup.exe || goto :error

rem The program is a folder, not a single self-extracting exe: antivirus programs trust it more and it starts faster.
rmdir /s /q "%~dp0dist\TerrariaAutoFish" 2>nul
python -m PyInstaller --noconfirm --windowed --noupx --name TerrariaAutoFish --icon "%WORK%\icon.ico" ^
  --version-file "%WORK%\app_version.txt" --paths "%~dp0src" ^
  --add-data "%~dp0assets;assets" --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --collect-submodules winrt --hidden-import ocr --hidden-import sonar --hidden-import catches ^
  --exclude-module PIL --distpath "%~dp0dist" --workpath "%WORK%" --specpath "%WORK%" src\app.py || goto :error

python -m PyInstaller --noconfirm --onefile --windowed --noupx --name TerrariaAutoFish-%VER%-setup --icon "%WORK%\icon.ico" ^
  --version-file "%WORK%\setup_version.txt" --paths "%~dp0src" ^
  --add-data "%~dp0dist\TerrariaAutoFish;payload" --add-data "%WORK%\icon.ico;." --exclude-module PIL --exclude-module numpy ^
  --distpath "%~dp0dist" --workpath "%WORK%" --specpath "%WORK%" src\installer.py || goto :error

rmdir /s /q "%~dp0dist\portable" 2>nul
mkdir "%~dp0dist\portable"
xcopy /e /i /q /y "%~dp0dist\TerrariaAutoFish" "%~dp0dist\portable\TerrariaAutoFish" >nul || goto :error
copy /y "%~dp0scripts\portable_note.txt" "%~dp0dist\portable\TerrariaAutoFish\portable.txt" >nul
copy /y "%~dp0README.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
copy /y "%~dp0README.ru.md" "%~dp0dist\portable\TerrariaAutoFish\" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path '%~dp0dist\portable\TerrariaAutoFish' -DestinationPath '%~dp0dist\TerrariaAutoFish-%VER%-portable.zip'" || goto :error
rmdir /s /q "%~dp0dist\portable" "%WORK%"

rem The fresh program into the project folder (what it writes itself is in "data").
tasklist /fi "imagename eq TerrariaAutoFish.exe" | find /i "TerrariaAutoFish.exe" >nul
if errorlevel 1 (
  rmdir /s /q "%~dp0_internal" 2>nul
  xcopy /e /i /q /y "%~dp0dist\TerrariaAutoFish" "%~dp0." >nul
) else (
  echo TerrariaAutoFish is running - TerrariaAutoFish.exe in the project folder was not updated.
)
echo.
echo Done: dist\TerrariaAutoFish-%VER%-setup.exe and dist\TerrariaAutoFish-%VER%-portable.zip
if not defined NOPAUSE pause
exit /b 0

:error
echo Build failed.
if not defined NOPAUSE pause
exit /b 1
