"""Provision Deskflow and apply matched settings to an isolated pair."""
import base64
import hashlib
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import tempfile
import time

from .deskflow_bundle import download_payload, install_windows_package
from .mac_install import VERSION, HASHES, install_script, install_result
from .onboarding import settings_directory
from .process import hidden_console
from .profile import ssh_arguments
from .setup import render


CLIENT_LOG_MARKER = "[WinMacLink client start]"


class DeskflowPermissionError(ValueError):
    """The Mac client stopped because macOS did not trust its input process."""


def prepare_pair(profile, *, runner=subprocess.run):
    if profile.topology != "direct":
        raise ValueError("Deskflowの設定には直結LANの接続が必要です。")
    args = ssh_arguments(profile)
    target = runner(args + ['test "$(uname -s)" = Darwin && uname -m'],
                    capture_output=True, text=True, timeout=20, **hidden_console())
    arch = target.stdout.strip()
    if target.returncode or arch not in HASHES:
        raise ValueError("インストール先のMacとCPUをSSHで確認できません。")
    present = runner(args + ["test -d /Applications/Deskflow.app"],
                     capture_output=True, timeout=20, **hidden_console())
    if present.returncode not in (0, 1):
        raise ValueError("MacのDeskflow導入状況をSSHで確認できません。")
    core = install_windows_package()
    if present.returncode != 0:
        with tempfile.TemporaryDirectory() as directory:
            dmg = download_payload(directory, f"deskflow-{VERSION}-macos-{arch}.dmg")
            with dmg.open("rb") as source:
                result = runner(args + [install_script(upload=True)], stdin=source,
                                capture_output=True, timeout=240, **hidden_console())
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        install_result(result)
    version = runner(args + ["/Applications/Deskflow.app/Contents/MacOS/deskflow-core --version"],
                     capture_output=True, text=True, timeout=15, **hidden_console())
    if version.returncode or not re.search(rf"\bv{re.escape(VERSION)}(?=,|\s|$)", version.stdout):
        raise ValueError(f"MacのDeskflowのバージョンを確認してください。この構成は{VERSION}を使用します。")

    folder = settings_directory() / "deskflow-pairs" / profile.host_key_alias
    folder.mkdir(parents=True, exist_ok=True)
    configs = render(profile)
    layout = folder / "layout.conf"
    server = folder / "Deskflow.conf"
    server_text = configs["windows-server.ini"].replace(
        "externalConfigFile=layout.conf", f"externalConfigFile={layout.as_posix()}")
    for path, text in ((layout, configs["layout.conf"]), (server, server_text)):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)

    relative_path = f"Library/Application Support/WinMacLink/Deskflow/{profile.host_key_alias}"
    payload = base64.b64encode(configs["mac-client.ini"].encode("utf-8")).decode("ascii")
    command = f"""set -eu
umask 077
cd "$HOME"
folder={shlex.quote(relative_path)}
mkdir -p "$folder"
file=$(mktemp "$folder/Deskflow.conf.XXXXXX")
trap 'rm -f "$file"' EXIT
printf '%s' {shlex.quote(payload)} | base64 -D > "$file"
mv -f "$file" "$folder/Deskflow.conf"
test -s "$folder/Deskflow.conf"
"""
    deployed = runner(args + [command], capture_output=True, timeout=20, **hidden_console())
    if deployed.returncode:
        raise ValueError("Mac側にDeskflow設定を保存できませんでした。SSH接続を確認してやり直してください。")
    return {"windows_core": str(core), "windows_settings": str(server),
            "mac_settings": relative_path + "/Deskflow.conf"}


def _fingerprint(pem):
    certificate = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem, re.S)
    if not certificate:
        raise ValueError("Deskflowの証明書を読み取れません。")
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.group())).hexdigest()


def _wait_for_client(process, log, mac_name, *, timeout=16, stable_for=2.5):
    connected = f'client "{mac_name}" has connected'
    disconnected = f'client "{mac_name}" has disconnected'
    deadline = time.monotonic() + timeout
    connection = -1
    connected_at = deadline
    while process.poll() is None and time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8", errors="replace")
        latest = text.rfind(connected)
        if latest > text.rfind(disconnected):
            if latest != connection:
                connection = latest
                connected_at = time.monotonic()
            if time.monotonic() - connected_at >= stable_for:
                return True
        else:
            connection = -1
        time.sleep(0.4)
    return False


def activate_pair(profile, *, request_permission=None):
    """Pair only app-owned certificates, then start the two Deskflow cores."""
    if profile.topology != "direct":
        raise ValueError("Deskflowの起動には直結LANの接続が必要です。")
    with socket.socket() as endpoint:
        endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            endpoint.bind((profile.windows_ip, 24800))
        except OSError as exc:
            raise ValueError("Windowsの有線IPにDeskflowのポートを確保できません。既存のDeskflowが動いている場合は停止してください。") from exc
    openssl = shutil.which("openssl")
    if not openssl:
        git_openssl = Path("C:/Program Files/Git/mingw64/bin/openssl.exe")
        if not git_openssl.is_file():
            raise ValueError("WindowsにDeskflow証明書を作るOpenSSLが見つかりません。")
        openssl = str(git_openssl)
    pair = prepare_pair(profile)
    args = ssh_arguments(profile)
    settings = Path(pair["windows_settings"])
    with settings.open("a", encoding="utf-8") as file:
        file.write("\n[log]\nlevel=Debug\n")
    tls = settings.parent / "tls"
    tls.mkdir(exist_ok=True)
    certificate = tls / "deskflow.pem"
    if not certificate.exists():
        with tempfile.TemporaryDirectory(dir=tls) as temp:
            key, cert = Path(temp) / "private.pem", Path(temp) / "certificate.pem"
            result = subprocess.run(
                [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1825",
                 "-subj", "/CN=WinMacLink-Windows", "-keyout", str(key), "-out", str(cert)],
                capture_output=True, timeout=30, **hidden_console())
            if result.returncode:
                raise ValueError("WindowsのDeskflow証明書を作成できません。")
            combined = Path(temp) / "deskflow.pem"
            combined.write_bytes(cert.read_bytes() + key.read_bytes())
            combined.replace(certificate)
    windows_hash = _fingerprint(certificate.read_text(encoding="ascii"))
    mac_settings_path = pair["mac_settings"]
    mac_settings = shlex.quote(mac_settings_path)
    mac_client_log = shlex.quote(mac_settings_path.rsplit("/", 1)[0] + "/client.log")
    prepare_mac = f"""set -eu
umask 077
cd "$HOME"
settings={mac_settings}
folder=$(dirname "$settings")
mkdir -p "$folder/tls"
cert="$folder/tls/deskflow.pem"
if [ ! -s "$cert" ]; then
  work=$(mktemp -d "$folder/tls/cert.XXXXXX")
  trap 'rm -f "$work/key.pem" "$work/cert.pem" "$work/combined.pem"; rmdir "$work"' EXIT
  /usr/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 1825 -subj /CN=WinMacLink-Mac \
    -keyout "$work/key.pem" -out "$work/cert.pem" >/dev/null 2>&1
  cat "$work/cert.pem" "$work/key.pem" > "$work/combined.pem"
  mv "$work/combined.pem" "$cert"
fi
printf '%s\n' 'v2:sha256:{windows_hash}' > "$folder/tls/trusted-servers"
/usr/bin/openssl x509 -in "$cert" -outform PEM
"""
    result = subprocess.run(args + [prepare_mac], capture_output=True, text=True,
                            timeout=35, **hidden_console())
    if result.returncode:
        raise ValueError("MacのDeskflow証明書を用意できません。")
    (tls / "trusted-clients").write_text(
        f"v2:sha256:{_fingerprint(result.stdout)}\n", encoding="ascii")

    label = f"local.winmaclink.deskflow.{profile.host_key_alias}"
    start_mac = f"""set -eu
cd "$HOME"
settings={mac_settings}
label={shlex.quote(label)}
folder=$(dirname "$settings")
log="$folder/client.log"
core=/Applications/Deskflow.app/Contents/MacOS/deskflow-core
test -x "$core"
domain="gui/$(id -u)"
launchctl print "$domain" >/dev/null 2>&1
printf '\\n%s\\n' '{CLIENT_LOG_MARKER}' >> "$log"
if launchctl print "$domain/$label" >/dev/null 2>&1; then
    launchctl kickstart -k "$domain/$label"
else
    plist=$(mktemp "$folder/client.XXXXXX")
    trap 'rm -f "$plist"' EXIT
    plutil -create xml1 "$plist"
    plutil -insert Label -string "$label" "$plist"
    plutil -insert ProgramArguments -json '[]' "$plist"
    plutil -insert ProgramArguments.0 -string "$core" "$plist"
    plutil -insert ProgramArguments.1 -string client "$plist"
    plutil -insert ProgramArguments.2 -string --settings "$plist"
    plutil -insert ProgramArguments.3 -string "$HOME/$settings" "$plist"
    plutil -insert StandardOutPath -string "$HOME/$log" "$plist"
    plutil -insert StandardErrorPath -string "$HOME/$log" "$plist"
    plutil -insert RunAtLoad -bool YES "$plist"
    mv -f "$plist" "$folder/client.plist"
    launchctl bootstrap "$domain" "$folder/client.plist"
fi
"""
    log = settings.parent / "server.log"
    with log.open("wb") as output:
        process = subprocess.Popen([pair["windows_core"], "server", "--settings", str(settings)],
                                   stdout=output, stderr=subprocess.STDOUT, **hidden_console())
    mac_started = False
    try:
        result = subprocess.run(args + [start_mac], capture_output=True, timeout=20, **hidden_console())
        if result.returncode:
            raise ValueError("MacのDeskflowを起動できません。Macにログインしているか確認してください。")
        mac_started = True
        if _wait_for_client(process, log, profile.mac_name):
            return process
        mac_log = subprocess.run(args + [f'tail -n 100 "$HOME"/{mac_client_log}'],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, **hidden_console())
        last_run = mac_log.stdout.rpartition(CLIENT_LOG_MARKER)[2].lower()
        if "failed to create quartz event tap" in last_run or "process is not trusted" in last_run:
            if request_permission is not None:
                cancel = request_permission()
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline and process.poll() is None:
                    if cancel.wait(2):
                        raise ValueError("入力共有の設定を中止しました。")
                    result = subprocess.run(args + [start_mac], capture_output=True, timeout=20, **hidden_console())
                    if result.returncode:
                        raise ValueError("MacのDeskflowを再起動できません。Macへの接続を確認してください。")
                    if _wait_for_client(process, log, profile.mac_name, timeout=6):
                        return process
            raise DeskflowPermissionError("Macの入力許可を確認できませんでした。許可した後で『2モニターで入力共有』をもう一度押してください。")
        raise ValueError(f"Deskflowの接続を確認できません。MacのアクセシビリティとWindowsの通信許可を確認してください。ログ {log}")
    except (OSError, ValueError, subprocess.SubprocessError):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if mac_started:
            try:
                subprocess.run(args + [f'launchctl bootout "gui/$(id -u)/{label}"'],
                               capture_output=True, timeout=8, **hidden_console())
            except (OSError, subprocess.SubprocessError):
                pass
        raise
