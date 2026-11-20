"""Launch the packaged Windows GUI in the current process."""

import ctypes
from pathlib import Path
import subprocess
import sys
from tkinter import Tk, messagebox

from winmaclink.desktop import SHORTCUT_ARGUMENT, create_shortcut
from winmaclink.gui import launch


def main():
    # Tk is already loaded. Let system tools resolve their own DLLs.
    ctypes.windll.kernel32.SetDllDirectoryW(None)

    if SHORTCUT_ARGUMENT not in sys.argv[1:]:
        executable = Path(sys.executable).resolve()
        try:
            create_shortcut(executable, arguments=SHORTCUT_ARGUMENT, icon=executable)
        except (OSError, subprocess.CalledProcessError):
            notice = Tk()
            notice.withdraw()
            messagebox.showwarning("WinMacLink", "デスクトップにショートカットを作成できませんでした。WinMacLinkは起動できます。", parent=notice)
            notice.destroy()
    launch()


if __name__ == "__main__":
    main()
