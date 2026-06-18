@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Building AdolarRadio.exe...
pyinstaller adolar_radio.spec --clean --noconfirm

echo Done. Find AdolarRadio.exe in dist\
pause
