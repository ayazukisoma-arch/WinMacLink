"""Local execution boundaries: allowlisted installers, pinned SSH, owned tunnel."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from .profile import ssh_arguments
from .process import hidden_console

PACKAGES = {"deskflow": "Deskflow.Deskflow", "tigervnc": "TigerVNC.TigerVNC"}


def windows_setup_packages(viewer=None):
    """Return the supported desktop packages whose executable is absent."""
    roots = {Path(os.environ.get(name, "C:/Program Files"))
             for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")}
    candidates = {
        "deskflow": [root / "Deskflow" / "deskflow.exe" for root in roots],
        "tigervnc": [root / "TigerVNC" / "vncviewer.exe" for root in roots],
    }
    if viewer:
        candidates["tigervnc"].append(Path(viewer).expanduser())
    return [name for name, paths in candidates.items() if not any(path.is_file() for path in paths)]


def install_command(component):
    if component not in PACKAGES:
        raise ValueError("Unsupported installer")
    return ["winget", "install", "--id", PACKAGES[component], "--exact",
            "--source", "winget", "--accept-source-agreements", "--accept-package-agreements",
            "--disable-interactivity"]


def install(component, execute=False):
    command = install_command(component)
    if not execute:
        return {"state": "preview", "command": command,
                "effects": "installs the selected package; package license and source agreements will be accepted; administrator UI may appear",
                "rollback": "Not automatically reversible; uninstall separately after checking user data"}
    if os.name != "nt" or not shutil.which("winget"):
        raise ValueError("Installation requires Windows with winget")
    result = subprocess.run(command, timeout=600)
    if result.returncode:
        raise ValueError(f"Installer failed (exit {result.returncode}); no success claimed. Check source availability and administrator approval.")
    return {"state": "installer-reported-success", "component": component,
            "next_step": "Run doctor and verify the installed application manually"}


def tunnel_arguments(p):
    args = ssh_arguments(p)
    return args[:-1] + ["-N", "-o", "ExitOnForwardFailure=yes",
                       "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
                       "-L", f"127.0.0.1:{p.local_port}:127.0.0.1:5900", args[-1]]


def connect(p):
    viewer = Path(p.viewer).expanduser()
    if not viewer.is_file():
        raise ValueError("Viewer not found; set its full path in the private profile")
    # Reject occupied ports rather than trusting or killing an unrelated listener.
    with socket.socket() as check:
        try:
            check.bind(("127.0.0.1", p.local_port))
        except OSError as exc:
            raise ValueError("Local port is occupied; choose another port or close your existing connection") from exc
    proc = subprocess.Popen(tunnel_arguments(p), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **hidden_console())
    try:
        deadline = time.monotonic() + 12
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                from .doctor import classify_ssh
                error = proc.stderr.read().decode(errors="replace")
                raise ValueError(classify_ssh(error) + ": tunnel did not start")
            try:
                with socket.create_connection(("127.0.0.1", p.local_port), timeout=1) as connection:
                    connection.settimeout(2)
                    banner = connection.recv(12)
                    if banner.startswith(b"RFB "):
                        ready = True
                        break
            except OSError:
                pass
            time.sleep(0.2)
        if not ready:
            raise ValueError("VNC_NOT_READY: SSH is running but no VNC banner was received; check Screen Sharing")
        result = subprocess.run([str(viewer), "-ViewOnly=0", "-AlwaysCursor=1", "-FullScreen=0", f"127.0.0.1::{p.local_port}"])
        if result.returncode:
            raise ValueError(f"Viewer exited with code {result.returncode}")
        return {"state": "viewer-closed", "note": "Screen contents and successful login are not automatically verified"}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.stderr:
            proc.stderr.close()
