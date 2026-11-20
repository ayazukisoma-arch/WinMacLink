"""Human lookup instructions tailored only to authenticated facts or explicit input."""
import ipaddress
import re
import subprocess
from .profile import ssh_arguments, identifier
from .process import hidden_console
from dataclasses import replace
import uuid
from .profile import Profile

LOOKUP_PROBE = r'''printf 'WML:version\n'; sw_vers -productVersion
printf 'WML:user\n'; whoami
printf 'WML:display\n'; id -F
printf 'WML:services\n'; networksetup -listnetworkserviceorder
printf 'WML:interfaces\n'; /sbin/ifconfig
'''


def parse_context(output, expected_ip):
    sections = {}
    key = None
    for line in output.splitlines():
        if line.startswith("WML:"):
            key = line[4:]; sections[key] = []
        elif key is not None:
            sections[key].append(line)
    def first(name):
        lines = sections.get(name, [])
        value = lines[0].strip() if lines else ""
        return "".join(c for c in value if c.isprintable())[:160]
    version, user = first("version"), first("user")
    if not re.fullmatch(r"\d+(?:\.\d+){1,2}", version):
        raise ValueError("macOSバージョンを確認できません")
    identifier(user, "Mac user")
    interface = None
    current = None
    for line in sections.get("interfaces", []):
        header = re.match(r"^([A-Za-z0-9]+):", line)
        if header:
            current = header.group(1)
        address = re.match(r"\s+inet\s+(\d+\.\d+\.\d+\.\d+)\b", line)
        if address and address.group(1) == expected_ip:
            interface = current
    service = None
    latest = None
    for line in sections.get("services", []):
        match = re.match(r"^\(\d+\) (.+)$", line)
        if match:
            latest = match.group(1).strip()
        if interface and re.search(r"Device:\s*" + re.escape(interface) + r"\)", line):
            service = latest
    return {"verified": True, "version": version, "user": user, "display_name": first("display"),
            "service": service, "interface": interface, "ip": expected_ip}


def collect_context(profile, runner=subprocess.run):
    result = runner(ssh_arguments(profile) + [LOOKUP_PROBE], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=15, **hidden_console())
    if result.returncode:
        raise ValueError("Macの現在の情報を取得できません。未確認向けの手順で案内します。")
    return parse_context(result.stdout, profile.mac_ip)


def build_lookup_steps(context=None, candidate=None):
    context = context or {}
    candidate = candidate or {}
    verified = context.get("verified") is True
    version = context.get("version") if verified else None
    service = context.get("service") if verified else None
    network = service or "EthernetなどLANケーブルにつながる項目"
    user = context.get("user") if verified else None
    address = context.get("ip") if verified else candidate.get("host")
    from_fixed_ip = candidate.get("from_fixed_ip") is True
    try:
        major = int(version.split(".")[0]) if version else None
    except ValueError:
        major = None
    modern = major is None or major >= 13
    settings = "システム設定" if modern else "システム環境設定"
    ip_path = f"画面左上のAppleマーク → {settings} → ネットワーク → {network} → 詳細 → TCP/IP"
    if from_fixed_ip:
        ip_body = "前の手順でMacのTCP/IP画面に手動で設定したIPです。WinMacLinkが右側に引き継いでいます。確認し直す場合は、上の順番で「IPアドレス」欄を開いてください。"
    elif address:
        ip_body = "「IPアドレス」欄と、右側に入っている有線IPが一致することを確認してください。"
    else:
        ip_body = "「IPアドレス」欄の値を、右側の「Macの有線IPアドレス」に入力してください。"
    sharing_path = f"画面左上のAppleマーク → {settings} → " + ("一般 → 共有" if modern else "共有")
    prefix = f"接続先で確認したバージョンはmacOS {version}です" if verified else "表示されたバージョンを確認してください"
    return [
        {
            "title": "短いユーザー名を確認",
            "path": (
                "以下いずれかの方法でユーザー名を確認できます。\n\n"
                "リモートログイン画面で見る\n"
                f"{sharing_path} →「リモートログイン」の右端のⓘ。\n"
                "上部の ssh ユーザー名@アドレス で、「@」の手前が短い名前です。\n\n"
                "Finderで見る\n"
                "Macの画面下にある青と白の顔のアイコン（Finder）をクリック。\n"
                "画面上部のメニューバーで「移動」→「ホーム」を選びます。\n"
                "開いたウィンドウの上に出るフォルダー名が短い名前です。\n\n"
                "ターミナルで見る\n"
                "MacでFinderを開き、画面上部の「移動」→「ユーティリティ」→「ターミナル」を開きます。"
                "開いたターミナルで whoami を実行し、表示された名前を確認します。"
            ),
            "field": None,
            "value": user,
            "body": (
                "確認した名前を右上の欄に入力します。Apple Account名やフルネームとは別の欄です。"
                "フォルダー名の変更は不要です。"
            ),
            "panel": "home",
        },
        {"title": "Macに設定した固定IP" if from_fixed_ip else "LANケーブル側のIPを確認",
         "path": ip_path, "field": "IPアドレス", "value": address, "body": ip_body, "panel": "network"},
        {"title": "リモートログインの許可を確認", "path": sharing_path + " → リモートログインのⓘ", "field": "許可するユーザーと接続用の表示", "value": None, "body": "自分のアカウントに接続を許可します。接続例が表示される場合、ssh 名前@アドレス の『@より左の名前』も短いユーザー名です。既に設定済みなら変更不要です。", "panel": "sharing"},
        {"title": "画面共有を確認して入力", "path": sharing_path + " → 画面共有のⓘ", "field": "画面共有の設定", "value": None, "body": "画面共有は本人が許可します。パスワードは本アプリへ保存せず、必要な認証画面で入力します。確認したユーザー名と有線IPだけを登録してください。登録だけでは初回の鍵準備・信頼確認は完了しません。", "panel": "sharing"},
        {"title": "画面が案内と違うとき", "path": "Macの画面左上にあるAppleマークをクリック →「このMacについて」", "field": "macOSのバージョン", "value": version, "body": prefix + "。初回でSSHが未設定なら、Macを直接操作できる画面が必要です。", "panel": None},
    ]


def registration_profile(existing, candidate, user, address):
    candidate = candidate or {}
    user, address = user.strip(), address.strip()
    try:
        identifier(user, "user")
    except ValueError as exc:
        raise ValueError("Macのユーザー名には、Finderのホームフォルダー名などで確認した短い名前だけを入力してください。") from exc
    try:
        ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError as exc:
        raise ValueError("Macの有線IPには『IPアドレス』欄の数字だけを入力してください。") from exc
    source = candidate.get("windows_ip") or (existing.windows_ip if existing else None)
    inferred_prefix = None
    if not source:
        matches = []
        for network in candidate.get("windows_networks", []):
            try:
                if ipaddress.IPv4Address(address) in ipaddress.IPv4Network(f"{network['ip']}/{network['prefix']}", strict=False):
                    matches.append(network)
            except (ValueError, KeyError, TypeError):
                continue
        if len(matches) == 1:
            source, inferred_prefix = matches[0]["ip"], matches[0]["prefix"]
    if not source:
        raise ValueError("Windowsの有線接続をまだ検出できません。LANケーブルを確認して『Macを探す』をやり直してください。")
    prefix = candidate.get("windows_prefix") or inferred_prefix or (existing.prefix if existing else None)
    if prefix is None and ipaddress.IPv4Address(source).is_link_local:
        prefix = 16
    if prefix is None:
        raise ValueError("Windowsの有線ネットワークを確認できません。『Macを探す』から再検出してください。")
    base = existing or Profile()
    same = existing is not None and existing.mac_ip == address and existing.user == user
    alias = base.host_key_alias if same else "winmaclink-" + uuid.uuid4().hex
    return replace(base, host=address, mac_ip=address, user=user, windows_ip=source,
                   prefix=prefix, topology="direct", host_key_alias=alias)
