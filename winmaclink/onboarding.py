"""Remember user-owned connections; discover only cached LAN neighbours."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from . import APPLICATION_ROOT
from .profile import Profile, ssh_arguments
from .network import local_ipv4
from .process import hidden_console


def settings_directory():
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home()/".local"/"share"
    return base / "WinMacLink"


def prepare_new_connection(profile):
    """Create a dedicated key in a fresh directory for a new profile."""
    directory = settings_directory() / "identities" / profile.host_key_alias
    directory.mkdir(parents=True, exist_ok=False)
    identity = directory / "id_ed25519"
    public_key = identity.with_suffix(".pub")
    try:
        result = subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity)],
            capture_output=True, timeout=15, **hidden_console(),
        )
        if result.returncode or not identity.is_file() or not public_key.is_file():
            raise ValueError("接続専用のSSH鍵を作成できませんでした。")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        identity.unlink(missing_ok=True)
        public_key.unlink(missing_ok=True)
        directory.rmdir()
        raise ValueError("接続専用のSSH鍵を作成できませんでした。WindowsのOpenSSHクライアントを確認してください。") from exc
    return replace(profile, identity=str(identity))


def find_profile(explicit=None, *, storage=None, project=None):
    storage = Path(storage) if storage else settings_directory()
    project = Path(project) if project else APPLICATION_ROOT
    candidates = [Path(explicit)] if explicit else [storage/"connection.json", project/".local"/"profile.json"]
    errors = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            profile = Profile.load(candidate)
            return profile, candidate.absolute(), errors
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"保存済みの接続設定を読み込めません：{candidate.name}（{type(exc).__name__}）")
    return None, None, errors


def remember_profile(profile, *, storage=None):
    storage = Path(storage) if storage else settings_directory()
    storage.mkdir(parents=True, exist_ok=True)
    path = storage/"connection.json"
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("保存先がリンクになっているため停止しました")
    # Revalidate rather than copying arbitrary files or unknown JSON fields.
    value = json.dumps(asdict(profile), ensure_ascii=False, indent=2)
    fd, name = tempfile.mkstemp(prefix=".connection-", suffix=".tmp", dir=storage)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def parse_neighbours(text):
    result = []
    seen = set()
    interface_ip = None
    for line in text.splitlines():
        header = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)\s+---", line)
        if header:
            interface_ip = header.group(1)
            continue
        entry = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+", line)
        if not entry or not interface_ip:
            continue
        ip, mac = entry.groups()
        mac = mac.lower().replace(":", "-")
        if (interface_ip, ip) in seen or ip == interface_ip or not local_ipv4(ip) or mac in ("ff-ff-ff-ff-ff-ff", "00-00-00-00-00-00"):
            continue
        if int(mac[:2], 16) & 1:  # multicast is not a device candidate
            continue
        seen.add((interface_ip, ip))
        result.append({"host": ip, "windows_ip": interface_ip, "mac_address": mac,
                       "identity_verified": False})
    return result


WIRED_QUERY = r'''$ErrorActionPreference='Stop'; $ips=@(Get-NetAdapter -Physical | Where-Object {$_.Status -eq 'Up' -and $_.NdisPhysicalMedium -eq 14} | ForEach-Object {Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength}); ConvertTo-Json -InputObject $ips -Compress'''


def wired_networks(runner=subprocess.run):
    if os.name != "nt":
        return []
    result = runner(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WIRED_QUERY], capture_output=True, text=True, timeout=8, **hidden_console())
    if result.returncode:
        return []
    value = json.loads(result.stdout)
    return [{"ip": item["IPAddress"], "prefix": item["PrefixLength"]} for item in value if isinstance(item, dict)
            and isinstance(item.get("IPAddress"), str) and local_ipv4(item["IPAddress"])
            and type(item.get("PrefixLength")) is int and 1 <= item["PrefixLength"] <= 30] if isinstance(value, list) else []


def direct_candidates(neighbours, wired_ips, profile=None):
    sources = set(wired_ips)
    if profile and profile.topology == "direct":
        sources.add(profile.windows_ip)
    result = [dict(item) for item in neighbours if item["windows_ip"] in sources]
    if profile and profile.topology == "direct":
        matching = next((item for item in result if item["host"] == profile.mac_ip and item["windows_ip"] == profile.windows_ip), None)
        if matching is None:
            matching = {"host": profile.mac_ip, "windows_ip": profile.windows_ip, "mac_address": "", "identity_verified": False}
            result.insert(0, matching)
        matching.update(registered=True, name=profile.mac_name, verification="not-checked")
    return sorted(result, key=lambda item: (not item.get("registered", False), item["host"]))


def candidate_label(item):
    if item.get("identity_verified"):
        return f"登録済みMac：{item['name']}  — 鍵認証・macOS確認済み"
    if item.get("registered"):
        return f"登録済みMac：{item['name']}  — 接続を確認できません（{item['host']}）"
    return f"有線LANの機器：{item['host']}  — Macかどうかは未確認"


def verify_registered(candidates, profile, runner=subprocess.run):
    if not profile:
        return candidates
    saved = next((item for item in candidates if item.get("registered")), None)
    if saved is not None:
        try:
            verification = runner(ssh_arguments(profile) + ["uname -s"], capture_output=True, text=True, timeout=8, **hidden_console())
            if verification.returncode == 0 and verification.stdout.strip() == "Darwin":
                saved.update(identity_verified=True, verification="ssh-pinned-macos")
            else:
                saved["verification"] = "failed"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            saved["verification"] = "unavailable"
    return candidates


def discover(profile=None, *, runner=subprocess.run):
    # No network sweep or external vendor lookup. Candidates are not trusted Macs.
    if os.name != "nt":
        return []
    wired = []
    prefixes = {}
    try:
        query = runner(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WIRED_QUERY], capture_output=True, text=True, timeout=8, **hidden_console())
        if query.returncode == 0:
            value = json.loads(query.stdout)
            for item in value if isinstance(value, list) else []:
                if isinstance(item, str) and local_ipv4(item):
                    wired.append(item)
                elif isinstance(item, dict) and isinstance(item.get("IPAddress"), str) and local_ipv4(item["IPAddress"]):
                    address, prefix = item["IPAddress"], item.get("PrefixLength")
                    wired.append(address)
                    if type(prefix) is int and 1 <= prefix <= 30:
                        prefixes[address] = prefix
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    # Only ASCII address fields are parsed. Localized labels can use the Windows code page.
    result = runner(["arp", "-a"], capture_output=True, encoding="ascii",
                    errors="replace", timeout=5, **hidden_console())
    if result.returncode:
        raise ValueError("LANの接続履歴を取得できません。ケーブルとネットワーク設定を確認してください。")
    candidates = direct_candidates(parse_neighbours(result.stdout), wired, profile)
    for item in candidates:
        if item["windows_ip"] in prefixes:
            item["windows_prefix"] = prefixes[item["windows_ip"]]
    return verify_registered(candidates, profile, runner)
