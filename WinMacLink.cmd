@echo off
setlocal
pushd "%~dp0" || (pause & exit /b 1)
py -3 -c "import sys, tkinter; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m winmaclink.desktop
) else (
    python -c "import sys, tkinter; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
    if errorlevel 1 (
        echo WinMacLink requires Python 3.11 or later with Tcl/Tk.
        popd
        pause
        exit /b 1
    )
    python -m winmaclink.desktop
)
set "WINMACLINK_EXIT=%ERRORLEVEL%"
popd
if not "%WINMACLINK_EXIT%"=="0" pause
exit /b %WINMACLINK_EXIT%
