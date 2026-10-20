@echo off
rem Build NotePrompt.exe (1 file, khong cua so console) vao thu muc dist\
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv || goto :fail
)
.venv\Scripts\python.exe -m pip install -q -r requirements.txt || goto :fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name NotePrompt --icon assets\icon.ico --add-data "assets\icon.ico;assets" --exclude-module tkinter app.py || goto :fail
echo.
echo Xong: dist\NotePrompt.exe
exit /b 0
:fail
echo Build loi.
exit /b 1
