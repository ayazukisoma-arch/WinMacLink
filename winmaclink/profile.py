"""Strict configuration: no passwords, commands, or trust bypasses."""
from dataclasses import dataclass, asdict
from pathlib import Path
import ipaddress
import json
import re
from .network import resolve_local


def identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(f"Invalid {label}: use letters, digits, dot, dash or underscore")
    return value


@dataclass(frozen=True)
class Profile:
    schema: int = 1
    host: str = "192.168.250.2"
    user: str = "macuser"
    identity: str = "~/.ssh/winmaclink_ed25519"
    host_key_alias: str = "mac-mini.local"
    windows_name: str = "windows-main"
    mac_name: str = "mac-mini"
    mac_position: str = "left"
    topology: str = "direct"
    windows_ip: str = "192.168.250.1"
    mac_ip: str = "192.168.250.2"
    prefix: int = 30
    local_port: int = 15900
    ssh_port: int = 22
    viewer: str = "C:/Program Files/TigerVNC/vncviewer.exe"

    def __post_init__(self):
        if type(self.schema) is not int or self.schema != 1:
            raise ValueError("Unsupported profile schema")
        for name in ("host", "user", "host_key_alias", "windows_name", "mac_name"):
            identifier(getattr(self, name), name)
        if self.windows_name == self.mac_name:
            raise ValueError("Computer names must differ")
        if self.mac_position not in ("left", "right", "above", "below"):
            raise ValueError("Invalid mac_position")
        if self.topology not in ("direct", "lan"):
            raise ValueError("topology must be direct or lan")
        for name in ("local_port", "ssh_port"):
            value = getattr(self, name)
            if name == "local_port" and (type(value) is not int or not 1024 <= value <= 65535):
                raise ValueError("local_port must be 1024..65535")
            if type(value) is not int or not 1 <= value <= 65535:
                raise ValueError(f"Invalid {name}")
        if type(self.prefix) is not int or not 1 <= self.prefix <= 30:
            raise ValueError("prefix must be 1..30")
        addresses = [ipaddress.IPv4Address(self.windows_ip), ipaddress.IPv4Address(self.mac_ip)]
        private_blocks = [ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
        private_blocks.append(ipaddress.IPv4Network("169.254.0.0/16"))
        if any(not any(a in block for block in private_blocks) for a in addresses):
            raise ValueError("Use private unicast addresses for the LAN profile")
        network = ipaddress.IPv4Network(f"{addresses[0]}/{self.prefix}", strict=False)
        if not any(network.subnet_of(block) for block in private_blocks):
            raise ValueError("Subnet must stay within a private address block")
        if addresses[0] == addresses[1] or addresses[1] not in network:
            raise ValueError("Addresses must differ and share a subnet")
        if any(a in (network.network_address, network.broadcast_address) for a in addresses):
            raise ValueError("Do not use subnet or broadcast addresses")
        for name in ("identity", "viewer"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or any(c in value for c in '\x00\r\n"'):
                raise ValueError(f"Invalid {name} path")

    @classmethod
    def load(cls, path):
        obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(obj, dict):
            raise ValueError("Profile must be an object")
        unknown = set(obj) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError("Unknown profile fields; passwords and commands are not accepted")
        return cls(**obj)

    def public(self):
        obj = asdict(self)
        for name in ("host", "user", "identity", "host_key_alias", "viewer", "windows_name", "mac_name", "windows_ip", "mac_ip"):
            obj[name] = "<redacted>"
        return obj


def ssh_arguments(p: Profile):
    address = resolve_local(p.host)
    if p.topology == "direct" and address != p.mac_ip:
        raise ValueError("DIRECT_ENDPOINT_MISMATCH: direct mode must target the configured Mac Ethernet IP")
    binding = ["-b", p.windows_ip] if p.topology == "direct" else []
    return ["ssh", *binding, "-i", str(Path(p.identity).expanduser()), "-p", str(p.ssh_port),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", f"HostKeyAlias={p.host_key_alias}", "-o", "ConnectTimeout=5",
            f"{p.user}@{address}"]
