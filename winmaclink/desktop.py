"""Windows launcher for the extracted WinMacLink distribution."""

import os
from pathlib import Path
import subprocess
import sys

from . import APPLICATION_ROOT
from .process import hidden_console


ICON = Path(__file__).with_name("assets") / "WinMacLink.ico"
GUI_ARGUMENTS = "-m winmaclink gui"
SHORTCUT_ARGUMENT = "--from-shortcut"

CREATE_SHORTCUT = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if ($env:WINMACLINK_DESKTOP) { $desktop = $env:WINMACLINK_DESKTOP }
if (-not $desktop -or -not [IO.Directory]::Exists($desktop)) {
    throw 'The Windows desktop folder could not be found.'
}
$shell = New-Object -ComObject WScript.Shell
$description = 'WinMacLink (desktop launcher)'
$iconLocation = "$env:WINMACLINK_ICON,0"
foreach ($name in @('WinMacLink.lnk', 'WinMacLink (Portable).lnk')) {
    $path = Join-Path $desktop $name
    $shortcut = $shell.CreateShortcut($path)
    if (Test-Path -LiteralPath $path) {
        $legacy = $shortcut.Arguments -ceq '-m winmaclink gui' -and
            [IO.Path]::GetFileName($shortcut.TargetPath) -in @('python.exe', 'pythonw.exe')
        $sameInstall = $shortcut.WorkingDirectory -eq $env:WINMACLINK_ROOT
        if ($shortcut.Description -ne $description -and -not ($legacy -and $sameInstall)) { continue }
        if ($shortcut.Description -eq $description -and
            $shortcut.TargetPath -eq $env:WINMACLINK_TARGET -and
            $shortcut.Arguments -ceq $env:WINMACLINK_GUI_ARGS -and
            $shortcut.WorkingDirectory -eq $env:WINMACLINK_ROOT -and
            $shortcut.IconLocation -eq $iconLocation) { exit 0 }
    }
    $shortcut.TargetPath = $env:WINMACLINK_TARGET
    $shortcut.Arguments = $env:WINMACLINK_GUI_ARGS
    $shortcut.WorkingDirectory = $env:WINMACLINK_ROOT
    $shortcut.IconLocation = $iconLocation
    $shortcut.Description = $description
    $shortcut.Save()
    exit 0
}
throw 'Both WinMacLink shortcut names are already in use by other applications.'
"""


def create_shortcut(target, *, arguments=GUI_ARGUMENTS, icon=ICON, desktop=None):
    env = dict(os.environ, WINMACLINK_ROOT=str(APPLICATION_ROOT), WINMACLINK_ICON=str(icon),
               WINMACLINK_TARGET=str(target), WINMACLINK_GUI_ARGS=arguments,
               WINMACLINK_DESKTOP=str(desktop) if desktop is not None else "")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", CREATE_SHORTCUT],
                   env=env, check=True, **hidden_console())


def main():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file() or not ICON.is_file():
        print("WinMacLink needs pythonw.exe and its bundled icon. Extract all ZIP contents first.", file=sys.stderr)
        return 1

    status = 0
    try:
        create_shortcut(pythonw)
    except (OSError, subprocess.CalledProcessError):
        print("Could not create the desktop shortcut. Starting WinMacLink anyway.", file=sys.stderr)
        status = 1
    subprocess.Popen([str(pythonw), *GUI_ARGUMENTS.split()], cwd=APPLICATION_ROOT, **hidden_console())
    return status


if __name__ == "__main__":
    raise SystemExit(main())
