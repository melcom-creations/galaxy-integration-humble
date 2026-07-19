@echo off
REM Humble Bundle Plugin Configurator Launcher
REM This script runs the PowerShell configurator with proper error handling

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "scriptDir=%~dp0"
set "psScript=!scriptDir!configurator.ps1"

REM Check if PowerShell script exists
if not exist "!psScript!" (
    echo ERROR: configurator.ps1 not found in !scriptDir!
    echo Please make sure both configurator.bat and configurator.ps1 are in the same folder.
    pause
    exit /b 1
)

REM Run PowerShell script with proper execution policy
REM -ExecutionPolicy Bypass: Allows unsigned scripts to run
REM -NoProfile: Skip profile loading for faster execution
REM -File: Execute the specified script
powershell -NoProfile -ExecutionPolicy Bypass -File "!psScript!"

REM Capture the exit code
set "exitCode=!errorlevel!"

REM Exit with the PowerShell script's exit code
exit /b !exitCode!