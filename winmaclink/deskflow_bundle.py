"""Acquire and install the pinned upstream Deskflow packages."""
import hashlib
from http.client import HTTPException
import os
from pathlib import Path
import platform
import shutil
import tempfile
from urllib.request import urlopen

from .mac_install import HASHES, RELEASE_URL, VERSION
from .onboarding import settings_directory

WINDOWS_HASHES = {
    "x64": "8d19004cc3625623489d96580c1b58fd13ee78185689907fd4478595f93fab9a",
    "arm64": "86d9a02f9f2f747023de7f9808065bf4d7f922ffde67c7308061a5865d367ac2",
}
PAYLOADS = {
    **{f"deskflow-{VERSION}-win-{arch}-portable.zip": digest for arch, digest in WINDOWS_HASHES.items()},
    **{f"deskflow-{VERSION}-macos-{arch}.dmg": digest for arch, digest in HASHES.items()},
}
def download_payload(directory, name):
    expected = PAYLOADS[name]
    path = Path(directory) / name
    try:
        with urlopen(f"{RELEASE_URL}/{name}", timeout=30) as source, path.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
    except (OSError, HTTPException) as exc:
        raise ValueError(f"Deskflowを公式配布元から取得できませんでした。ネット接続を確認して再実行してください。\n{name}") from exc
    with path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"取得したDeskflowのSHA-256が一致しません。導入を中止しました。\n{name}")
    return path


def install_windows_package(*, destination=None):
    if destination is None:
        if os.name != "nt":
            raise ValueError("Windows版DeskflowはWindowsへ配置してください。")
        destination = settings_directory() / "deskflow-binaries"
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not arch:
        raise ValueError("このWindows環境に対応するDeskflowの公式パッケージがありません。")
    name = f"deskflow-{VERSION}-win-{arch}-portable"
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / name
    core = target / "deskflow-core.exe"
    if core.is_file():
        return core
    with tempfile.TemporaryDirectory(dir=destination) as temp:
        archive = download_payload(temp, name + ".zip")
        shutil.unpack_archive(archive, temp)
        extracted = Path(temp) / name
        if not (extracted / core.name).is_file():
            raise ValueError("展開したDeskflowに実行ファイルがありません。")
        try:
            extracted.rename(target)
        except FileExistsError:
            if not core.is_file():
                raise
    return core
