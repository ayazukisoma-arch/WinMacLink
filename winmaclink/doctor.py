import platform
import shutil
import socket
import subprocess
from pathlib import Path
from .profile import ssh_arguments
from .guidance import filevault_guidance
from .network import resolve_local
from .process import hidden_console

REMOTE_PROBE = r'''printf 'os='; uname -s
printf 'arch='; uname -m
printf 'version='; sw_vers -productVersion
printf 'filevault='; fdesetup status 2>/dev/null
printf 'console='; stat -f '%Su' /dev/console
if test -d /Applications/Deskflow.app; then echo deskflow=present; else echo deskflow=missing; fi
if nc -z -w 2 127.0.0.1 5900 >/dev/null 2>&1; then echo vnc=listening; else echo vnc=not-listening; fi
printf 'firewall='; /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
'''


def tcp(host, port, timeout=2, source=None):
    try:
        with socket.create_connection((host, port), timeout=timeout, source_address=(source, 0) if source else None):
            return True
    except OSError:
        return False


def classify_ssh(stderr):
    text = stderr.lower()
    if "bad permissions" in text or "unprotected private key" in text:
        return "SSH_KEY_PERMISSIONS"
    if "host key verification failed" in text or "host identification has changed" in text:
        return "SSH_TRUST_REQUIRED"
    if "permission denied" in text:
        return "SSH_AUTH_FAILED"
    if "timed out" in text or "no route" in text or "could not resolve" in text:
        return "SSH_UNREACHABLE"
    return "SSH_FAILED"


def diagnose(p, *, runner=subprocess.run, probe=tcp):
    checks = []
    def add(code, status, detail, next_step=""):
        checks.append(dict(code=code, status=status, detail=detail, next_step=next_step))
    add("HOST_OS", "info", platform.system())
    for name in ("ssh", "winget"):
        found = shutil.which(name)
        add(f"TOOL_{name.upper()}", "ok" if found else "warning", "available" if found else "not found")
    key = Path(p.identity).expanduser()
    add("SSH_IDENTITY", "ok" if key.is_file() else "error", "present" if key.is_file() else "missing", "Use an existing dedicated key or set one up manually; never paste a private key into a report.")
    viewer_exists = Path(p.viewer).expanduser().is_file()
    add("VNC_VIEWER", "ok" if viewer_exists else "warning", "present" if viewer_exists else "missing")
    try:
        address = resolve_local(p.host)
    except (OSError, ValueError):
        add("LOCAL_ENDPOINT_REQUIRED", "error", "接続先が未解決、公開IP、または未対応アドレス。操作接続はローカルIPv4に限定します。")
        return {"schema": 1, "profile": p.public(), "checks": checks, "limitations": ["Endpoint not probed."]}
    if p.topology == "direct" and address != p.mac_ip:
        add("DIRECT_ENDPOINT_MISMATCH", "error", "直結モードの接続先がMacの有線IPと一致しません。")
        return {"schema": 1, "profile": p.public(), "checks": checks, "limitations": ["Endpoint not probed."]}
    reachable = probe(address, p.ssh_port, 2, p.windows_ip if p.topology == "direct" else None)
    add("SSH_PORT", "ok" if reachable else "error", "reachable" if reachable else "unreachable", "Check power, LAN, IP changes, Remote Login, and firewall. An open port alone does not identify the Mac.")
    if reachable and shutil.which("ssh") and key.is_file():
        try:
            result = runner(ssh_arguments(p) + [REMOTE_PROBE], capture_output=True, text=True, timeout=20, **hidden_console())
            if result.returncode:
                add(classify_ssh(result.stderr), "error", "SSH authentication/probe failed", "Check the pinned host key and account. Trust failures are never repaired by deleting known_hosts.")
            else:
                facts = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                if facts.get("os") != "Darwin":
                    add("REMOTE_OS", "error", "The endpoint did not report macOS")
                else:
                    add("SSH_AUTH", "ok", "macOS probe succeeded")
                    add("REMOTE_ARCH", "info", facts.get("arch", "unknown"))
                    add("MAC_VERSION", "info", facts.get("version", "unknown"))
                    code, severity, message = filevault_guidance(facts.get("filevault", ""), facts.get("arch", ""), facts.get("version", ""))
                    add(code, severity, message, "設定を開く場合はガイドのFileVault手順を選択。状態変更は本人が判断する。")
                    logged_out = facts.get("console") in ("root", "loginwindow", "_mbsetupuser")
                    add("CONSOLE_SESSION", "info", "login screen" if logged_out else "user session (name redacted)")
                    add("MAC_DESKFLOW", "ok" if facts.get("deskflow") == "present" else "warning", facts.get("deskflow", "unknown"))
                    add("MAC_VNC", "ok" if facts.get("vnc") == "listening" else "warning", facts.get("vnc", "unknown"), "Enable Screen Sharing in macOS; this does not prove viewing or input works.")
                    firewall = facts.get("firewall", "unknown")
                    add("MAC_FIREWALL", "warning" if "disabled" in firewall.lower() else "info", "disabled" if "disabled" in firewall.lower() else "see macOS settings", "SSH encryption does not restrict VNC's separate network exposure.")
        except (OSError, subprocess.TimeoutExpired):
            add("SSH_PROBE_FAILED", "error", "probe unavailable or timed out")
    return {"schema": 1, "profile": p.public(), "checks": checks,
            "limitations": ["No screen contents or input injection is tested.", "Accessibility, Local Network and administrator permissions require macOS UI approval.", "No router/NAT/IPv6 exposure audit is performed.", "A successful current probe does not prove reboot recovery."]}
