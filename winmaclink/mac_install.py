"""Pinned official Deskflow package, never disabling macOS protections."""
import subprocess
from .profile import ssh_arguments
from .process import hidden_console

VERSION = "1.27.0"
# https://github.com/deskflow/deskflow/releases/download/v1.27.0/sums.txt
HASHES = {
    "arm64": "dd21e79e566314394214906d3338c505d337af536fc580c022ee3fadffad0c97",
    "x86_64": "8aca3c77a1b16b9a3d6b8a380e5e38a0e6abf6d241bb32dcf3cf8b67abbff5d8",
}


def install_script(*, bundled=False):
    acquire = ('cat > "$work/$file"' if bundled else
               f'curl -fL --max-time 180 "https://github.com/deskflow/deskflow/releases/download/v{VERSION}/$file" -o "$work/$file"')
    return f'''set -eu
if [ -d /Applications/Deskflow.app ]; then
  echo ALREADY_PRESENT
  exit 0
fi
case "$(uname -m)" in
  arm64) arch=arm64; checksum={HASHES['arm64']} ;;
  x86_64) arch=x86_64; checksum={HASHES['x86_64']} ;;
  *) echo UNSUPPORTED_ARCH >&2; exit 2 ;;
esac
work=$(mktemp -d "$HOME/Library/Caches/winmaclink-install.XXXXXX")
file="deskflow-{VERSION}-macos-$arch.dmg"
{acquire}
cd "$work"
printf '%s  %s\\n' "$checksum" "$file" | shasum -a 256 -c -
mkdir "$work/mount"
trap 'hdiutil detach "$work/mount" >/dev/null 2>&1 || true' EXIT
printf 'Y\\n' | hdiutil attach "$work/$file" -nobrowse -mountpoint "$work/mount" >/dev/null
codesign --verify --deep --strict "$work/mount/Deskflow.app"
ditto "$work/mount/Deskflow.app" "$work/Deskflow.app"
mv -n "$work/Deskflow.app" /Applications/Deskflow.app
test -d /Applications/Deskflow.app
echo INSTALLED_REQUIRES_OS_PERMISSIONS
'''


def install_mac(p, execute=False, runner=subprocess.run):
    if not execute:
        return {"state": "preview", "component": "Deskflow", "version": VERSION,
                "source": f"https://github.com/deskflow/deskflow/releases/tag/v{VERSION}",
                "sha256": HASHES, "license": "GPL-2.0; execution accepts the disk-image license",
                "effects": "Download on Mac, validate pinned SHA256 and code signature, install only if absent. No permission bypass, no startup or network changes.",
                "rollback": "No automatic app uninstall. Existing apps are never upgraded or replaced."}
    result = runner(ssh_arguments(p) + [install_script()], capture_output=True, text=True, timeout=240, **hidden_console())
    return install_result(result)


def install_result(result):
    if result.returncode:
        raise ValueError("MAC_INSTALL_FAILED: inspect the Mac and official package availability; existing apps were not intentionally replaced")
    if "ALREADY_PRESENT" in result.stdout:
        return {"state": "already-present", "note": "Existing version unchanged; run doctor and inspect version"}
    if "INSTALLED_REQUIRES_OS_PERMISSIONS" not in result.stdout:
        raise ValueError("MAC_INSTALL_UNVERIFIED: expected completion marker not received")
    return {"state": "installed", "next_step": "Grant Accessibility and Local Network in macOS UI, then verify input sharing"}
