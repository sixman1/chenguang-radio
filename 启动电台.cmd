@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "RADIO_EXIT=1"
pushd "%~dp0"
if errorlevel 1 goto folder_error
set "RADIO_PUSHED=1"
if not exist "tools\preview.mjs" goto files_error

set "RADIO_NODE=node.exe"
where.exe node.exe >nul 2>nul
if not errorlevel 1 goto start_radio
set "RADIO_NODE=%ProgramFiles%\nodejs\node.exe"
if exist "%RADIO_NODE%" goto start_radio
set "RADIO_NODE=%LocalAppData%\Programs\nodejs\node.exe"
if exist "%RADIO_NODE%" goto start_radio
echo Node.js was not found. Install it from https://nodejs.org/ and try again.
goto finish

:start_radio
echo Starting radio. Keep this window open.
echo Open http://127.0.0.1:8765/ in your browser.
echo.
"%RADIO_NODE%" "%~dp0tools\preview.mjs"
set "RADIO_EXIT=%errorlevel%"
if not "%RADIO_EXIT%"=="0" echo Startup stopped. The error message is shown above.
goto finish

:folder_error
echo Could not open the project folder.
goto finish

:files_error
echo Missing tools\preview.mjs. Extract the entire ZIP before starting.
goto finish

:finish
echo.
echo Press any key to close this window.
pause >nul
if defined RADIO_PUSHED popd
exit /b %RADIO_EXIT%
