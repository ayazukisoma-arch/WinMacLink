"""WinMacLink: explicit, inspectable connection management."""

from pathlib import Path
import sys

__version__ = "0.1.0"
APPLICATION_ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                    else Path(__file__).resolve().parents[1])
