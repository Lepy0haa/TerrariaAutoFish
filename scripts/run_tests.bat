@echo off
rem Runs all tests (real hotbar snapshots, recorded bites, bobber search, full scenarios in a fake game).
cd /d "%~dp0.."
python -m unittest discover -s tests -v
pause
