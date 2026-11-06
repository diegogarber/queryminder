@echo off
rem Launches Queryminder without a console window.
cd /d "%~dp0"
start "" pythonw -m queryminder %*
