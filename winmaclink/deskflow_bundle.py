"""Verified Deskflow payloads included with the offline WinMacLink distribution."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import tempfile

from . import APPLICATION_ROOT
from .mac_install import HASHES, VERSION
from .onboarding import settings_directory

WINDOWS_HASHES = {
    "x64": "8d19004cc3625623489d96580c1b58fd13ee78185689907fd4478595f93fab9a",
    "arm64": "86d9a02f9f2f747023de7f9808065bf4d7f922ffde67c7308061a5865d367ac2",
}
PAYLOADS = {
    **{f"deskflow-{VERSION}-win-{arch}-portable.zip": digest for arch, digest in WINDOWS_HASHES.items()},
    **{f"deskflow-{VERSION}-macos-{arch}.dmg": digest for arch, digest in HASHES.items()},
}
BUNDLE = APPLICATION_ROOT / "vendor" / "deskflow"


def verified_payload(directory, name):
    path = Path(directory) / name
    if not path.is_file():
        raise ValueError(f"WinMacLinkの同梱ファイルが見つかりません。{name}")
    with path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual != PAYLOADS[name]:
        raise ValueError(f"Deskflow同梱ファイルのSHA-256が一致しません。{name}")
    return path


def install_windows_bundle(directory, *, destination=None):
    if destination is None:
        if os.name != "nt":
            raise ValueError("Windows版DeskflowはWindowsへ配置してください。")
        destination = settings_directory() / "deskflow-binaries"
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not arch:
        raise ValueError("このWindows環境に対応するDeskflow同梱版がありません。")
    name = f"deskflow-{VERSION}-win-{arch}-portable"
    archive = verified_payload(directory, name + ".zip")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / name
    core = target / "deskflow-core.exe"
    if core.is_file():
        return core
    with tempfile.TemporaryDirectory(dir=destination) as temp:
        shutil.unpack_archive(archive, temp)
        extracted = Path(temp) / name
        if not (extracted / core.name).is_file():
            raise ValueError("展開したDeskflowに実行ファイルがありません。")
        extracted.rename(target)
    return core
