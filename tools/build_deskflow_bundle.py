"""Build the offline Deskflow edition from official, locally downloaded release files."""
import argparse
import hashlib
from importlib.metadata import distribution
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from winmaclink.deskflow_bundle import BUNDLE, PAYLOADS, VERSION, verified_payload
from winmaclink.desktop import ICON


def build_windows_app(build):
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--noupx",
        "--name", "WinMacLink", "--icon", str(ICON),
        "--add-data", f"{ICON}:winmaclink/assets", "--paths", str(ROOT),
        "--workpath", str(build / "work"), "--distpath", str(build / "app"),
        "--specpath", str(build), str(ROOT / "tools" / "windows_entrypoint.py"),
    ], cwd=ROOT, env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(build / "cache")), check=True)
    return build / "app" / "WinMacLink"


def add_runtime_licenses(archive, prefix):
    python_root = Path(sys.base_prefix)
    pyinstaller = distribution("PyInstaller")
    pyinstaller_license = next(file for file in pyinstaller.files if file.name == "COPYING.txt")
    for name, file in {
        "Python.txt": python_root / "LICENSE.txt",
        "Tcl-Tk.txt": next((python_root / "tcl").glob("tk*/license.terms")),
        "PyInstaller.txt": pyinstaller.locate_file(pyinstaller_license),
    }.items():
        archive.write(file, prefix / "vendor" / "licenses" / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("downloads", type=Path)
    args = parser.parse_args()
    payloads = [verified_payload(args.downloads, name) for name in PAYLOADS]
    source = args.downloads / f"deskflow-v{VERSION}-source.tar.gz"
    with source.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != "dfe4327f5d0631ead9bacee743a96ee58024af11b5cc080af89b4c740b18e893":
        raise ValueError("Deskflow source archive does not match the verified release archive.")
    with tarfile.open(source) as archive:
        notices = {
            name: archive.extractfile(f"deskflow-{VERSION}/{upstream}").read()
            for name, upstream in (
                ("LICENSE", "LICENSE"),
                ("LicenseRef-OpenSSL-Exception.txt", "LICENSES/LicenseRef-OpenSSL-Exception.txt"),
            )
        }
    BUNDLE.mkdir(parents=True, exist_ok=True)
    for file in (*payloads, source):
        shutil.copyfile(file, BUNDLE / file.name)
    for name, content in notices.items():
        (BUNDLE / name).write_bytes(content)
    notice = BUNDLE / "NOTICE.txt"
    notice.write_text(
        f"Deskflow {VERSION}\n"
        f"Official release: https://github.com/deskflow/deskflow/releases/tag/v{VERSION}\n"
        f"The release archives are included unmodified with the upstream LICENSE, OpenSSL exception, and {source.name}.\n"
        "The WinMacLink terms do not apply to Deskflow; its upstream terms govern your rights to that software.\n"
        "See the upstream source and the notices inside the platform archives for build and dependency information.\n",
        encoding="utf-8",
    )
    output = ROOT / "dist" / f"WinMacLink-with-Deskflow-{VERSION}.zip"
    output.parent.mkdir(exist_ok=True)
    prefix = Path("WinMacLink")
    files = [*(BUNDLE / item.name for item in (*payloads, source)),
             *(BUNDLE / name for name in notices), notice,
             ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "LICENSE.md"]
    sources = [*sorted((ROOT / "winmaclink").glob("*.py")), ICON, ROOT / "pyproject.toml",
               ROOT / "tools" / "windows_entrypoint.py", Path(__file__).resolve(),
               ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "LICENSE.md"]
    with TemporaryDirectory(prefix="winmaclink-build-", dir=output.parent) as directory:
        build = Path(directory)
        app = build_windows_app(build)
        staged = build / output.name
        with ZipFile(staged, "w", compression=ZIP_DEFLATED) as archive:
            for file in sorted(app.rglob("*")):
                if file.is_file():
                    archive.write(file, prefix / file.relative_to(app))
            for file in files:
                archive.write(file, prefix / file.relative_to(ROOT))
            for file in sources:
                archive.write(file, prefix / "source" / file.relative_to(ROOT))
            add_runtime_licenses(archive, prefix)
        with ZipFile(staged) as archive:
            if archive.testzip() is not None:
                raise ValueError("WinMacLink package failed its archive integrity check.")
        staged.replace(output)
    print(output)


if __name__ == "__main__":
    main()
