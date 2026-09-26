@echo off
cd /d "%~dp0.."
python -c "import mss, numpy, pynput" 2>nul || python -m pip install -r requirements.txt
python src\autofish.py --debug %*
pause
