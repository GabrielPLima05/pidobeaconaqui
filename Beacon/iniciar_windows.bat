@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 web_app.py
) else (
    python web_app.py
)
if errorlevel 1 pause
