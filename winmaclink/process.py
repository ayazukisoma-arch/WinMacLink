import os
import subprocess


def hidden_console():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
