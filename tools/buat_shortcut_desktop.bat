@echo off
REM Dobel klik file ini untuk bikin shortcut "Orulabs POS" di Desktop.
REM Lihat buat_shortcut_desktop.ps1 untuk detail logikanya.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0buat_shortcut_desktop.ps1"
echo.
pause
