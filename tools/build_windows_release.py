"""Build the Windows distribution with the embedded Python runtime."""
from importlib.metadata import distribution
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from winmaclink import __version__
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
    architecture = {"win-amd64": "x64", "win-arm64": "arm64"}.get(sysconfig.get_platform())
    if architecture is None:
        raise ValueError("Build with Windows x64 or ARM64 Python.")
    output = ROOT / "dist" / f"WinMacLink-{__version__}-windows-{architecture}.zip"
    output.parent.mkdir(exist_ok=True)
    prefix = Path("WinMacLink")
    files = [ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "LICENSE.md"]
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
