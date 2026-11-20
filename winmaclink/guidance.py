"""Local, version-aware setup guidance; OS changes remain user decisions."""
import os
import subprocess
import re
import shlex
from pathlib import Path
from .profile import ssh_arguments
from .process import hidden_console

MAC_PANELS = {
    "network": "x-apple.systempreferences:com.apple.Network-Settings.extension",
    "sharing": "x-apple.systempreferences:com.apple.Sharing-Settings.extension",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "local_network": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_LocalNetwork",
    "filevault": "x-apple.systempreferences:com.apple.preference.security?FileVault",
}
STEPS = [
    ("直結LAN", "両方の初期設定を終え、LANケーブルで直接つなぐ。Windows側は設定画面を開ける。Mac側の初回操作はMacの画面から行う。", None),
    ("最初の共有許可", "Macの一般→共有でリモートログインを許可する。画面共有も本人が設定する。まだSSHが通らないMacの管理画面をWindowsから開くことはできない。Macへ一時的に画面・入力機器をつなぐか、既存の管理経路を利用する。", "sharing"),
    ("接続先と信頼確認", "『直結LANの固定IPを設定』から、候補が0台でも設定を始められます。Macの短いユーザー名と有線IPを登録すると、接続先に合わせたSSHの初回設定コマンドを表示します。", None),
    ("読み取り診断", "診断を実行し、SSH認証、画面共有の待受、FileVaultとOSの情報を確認する。ケーブルのリンクだけでは導入開始条件を満たしたと判断しない。", None),
    ("入力操作の許可", "Deskflowのアクセシビリティを許可。必要ならローカルネットワークも許可。実画面の許可は本人が行う。画面を開けても許可完了を自動で認定しない。", "accessibility"),
    ("ローカルネットワーク", "Deskflowのローカルネットワーク許可を確認。初回の証明書指紋も両端で照合する。", "local_network"),
    ("FileVaultと再起動", "FileVaultは自動で無効化しない。Apple Silicon＋macOS 26以降では条件付きでSSH解除が可能というAppleの案内がある。対応条件と実機検証を優先し、古い環境では現地解除が必要な場合を案内する。無効化を選ぶ場合も暗号化保護への影響を確認し、本人がOS設定で行う。", "filevault"),
    ("完了確認", "SSH接続、左右の実画面でクリック・文字入力、VNCの表示と操作を本人が確認。保存と復元を確認したうえで再起動テストを行う。未確認の項目は未確認として残す。", None),
]


def register_ssh_key(profile):
    if os.name != "nt":
        raise ValueError("SSHの初回確認はWindowsで開いてください。")
    key_path = Path(str(Path(profile.identity).expanduser()) + ".pub")
    fields = key_path.read_text(encoding="ascii").split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", fields[1]):
        raise ValueError("接続専用のEd25519公開鍵を確認できません。")
    key = shlex.quote(" ".join(fields[:2]))
    command = f"""set -eu
test "$(uname -s)" = Darwin
umask 077
mkdir -p "$HOME/.ssh"
test ! -L "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
file="$HOME/.ssh/authorized_keys"
test ! -L "$file"
touch "$file"
chmod 600 "$file"
key={key}
if ! grep -Fqx -- "$key" "$file"; then
    printf '\n%s\n' "$key" >> "$file"
fi
grep -Fqx -- "$key" "$file"
"""
    args = ssh_arguments(profile)
    args[args.index("BatchMode=yes")] = "BatchMode=no"
    args[args.index("StrictHostKeyChecking=yes")] = "StrictHostKeyChecking=ask"
    options = ["-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "IdentitiesOnly=yes"]
    result = subprocess.run([*args[:-1], *options, args[-1], command],
                            creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=240)
    if result.returncode:
        raise ValueError("公開鍵を登録できませんでした。Macのリモートログイン、指紋、ログイン情報を確認して再試行してください。")


def filevault_guidance(status, arch, version):
    text = status.lower()
    if "decryption" in text or "encryption in progress" in text:
        return ("FILEVAULT_TRANSITION", "warning", "FileVaultの処理中。状態が確定してから再起動・復旧方法を確認する。")
    match = re.search(r"\bfilevault is (on|off)\b", text)
    if match and match.group(1) == "off":
        return ("FILEVAULT_OFF", "info", "FileVaultは無効。これだけでは再起動後の遠隔ログイン成功は保証されない。")
    if not match:
        return ("FILEVAULT_UNKNOWN", "warning", "FileVaultの状態を取得できない。Macの実設定で確認する。")
    try:
        major = int(version.split(".")[0])
    except (ValueError, AttributeError):
        major = 0
    if arch == "arm64" and major >= 26:
        return ("FILEVAULT_SSH_CANDIDATE", "warning", "FileVaultは有効。Appleの条件付きSSH解除対象候補。Remote Login・起動時ネットワーク・解除資格を確認し、実機で検証する。自動無効化しない。")
    return ("FILEVAULT_LOCAL_UNLOCK", "warning", "FileVaultは有効。ログイン後の利用は可能でも、再起動時に現地解除が必要になる可能性がある。無効化を前提にせず、利用条件を選択する。")


def open_windows_network():
    if os.name != "nt":
        raise ValueError("Windowsの設定画面はWindows上で開いてください")
    os.startfile("ms-settings:network-ethernet")


def open_mac_panel(p, panel, runner=subprocess.run):
    if panel == "home":
        command = 'open "$HOME"'
    elif panel in MAC_PANELS:
        command = "open '" + MAC_PANELS[panel] + "'"
    else:
        raise ValueError("Unknown settings panel")
    result = runner(ssh_arguments(p) + [command],
                    capture_output=True, text=True, timeout=12, **hidden_console())
    if result.returncode:
        raise ValueError("Mac設定画面を開けません。SSH接続とGUIログイン状態を確認し、初回はMac側で操作してください。")
    return {"state": "open-requested", "note": "画面が表示され、本人が許可したかは別途確認が必要です。"}


def format_report(report):
    labels = {"HOST_OS": "操作元OS", "TOOL_SSH": "SSHクライアント", "TOOL_WINGET": "ソフト導入ツール",
              "SSH_IDENTITY": "認証鍵のファイル", "VNC_VIEWER": "画面ビューアー", "SSH_PORT": "Macへの到達性",
              "SSH_AUTH": "MacへのSSH認証", "REMOTE_ARCH": "MacのCPU種別", "MAC_VERSION": "macOSバージョン",
              "CONSOLE_SESSION": "Macの物理画面側のログイン状態", "MAC_DESKFLOW": "入力共有アプリ", "MAC_VNC": "画面共有の待受",
              "MAC_FIREWALL": "Macのファイアウォール", "SSH_TRUST_REQUIRED": "Macのホスト鍵を確認してください",
              "SSH_AUTH_FAILED": "SSHの認証を確認してください", "LOCAL_ENDPOINT_REQUIRED": "ローカル接続先を確認してください"}
    statuses = {"ok": "確認済み", "info": "情報", "warning": "要確認", "error": "未成立"}
    values = {"available": "利用可能", "present": "あり", "missing": "なし", "reachable": "到達可能", "unreachable": "到達できません",
              "listening": "待受中", "not-listening": "待受なし", "disabled": "無効", "macOS probe succeeded": "接続成功",
              "login screen": "ログイン画面", "user session (name redacted)": "ログイン済み（名前は非表示）"}
    lines = ["接続診断の結果（状態は確認した時点のものです）", ""]
    for item in report["checks"]:
        label = "FileVault" if item["code"].startswith("FILEVAULT_") else labels.get(item["code"], item["code"])
        lines.append(f"[{statuses.get(item['status'], item['status'])}] {label}：{values.get(item['detail'], item['detail'])}")
    lines += ["", "画面でのクリック・文字入力、再起動後の復帰、OSの許可完了は別途確認します。",
              "画面共有をSSHで暗号化しても、Macの共有ポートが他から見えなくなるわけではありません。"]
    return "\n".join(lines)
