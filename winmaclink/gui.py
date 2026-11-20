"""Native local GUI; no web server, telemetry or password collection."""
import json
from pathlib import Path
from queue import Queue, Empty
import subprocess
import time
import threading
import uuid
from dataclasses import replace
import ipaddress

from .doctor import diagnose
from .guidance import STEPS, open_mac_panel, open_windows_network, format_report, register_ssh_key
from .guidance import open_deskflow_permissions
from .profile import Profile
from .transaction import plan, apply, rollback
from .runtime import connect, install, windows_setup_packages
from .onboarding import find_profile, remember_profile, discover, candidate_label, wired_networks, prepare_new_connection
from .lookup import build_lookup_steps, collect_context, registration_profile
from .fixed_ip import mac_fixed_ip_steps, open_windows_fixed_ip
from .network import direct_ssh_ready
from .deskflow_pair import activate_pair
from .desktop import ICON


def launch(profile_path=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title("WinMacLink — WindowsからMacを使う")
    if root.tk.call("tk", "windowingsystem") == "win32" and ICON.is_file():
        root.iconbitmap(default=str(ICON))
    root.geometry("940x700")
    root.minsize(760, 580)
    root.configure(padx=20, pady=16)
    state = {"profile": None, "path": None, "busy": False}
    jobs = Queue()
    status = tk.StringVar()
    ttk.Label(root, text="WinMacLink", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ttk.Label(root, text="直結LAN / ローカル操作限定 / OS設定は本人が管理", font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 12))
    tools = ttk.Frame(root)
    tools.pack(fill="x")
    mac_side_label = tk.StringVar(value="左")
    mac_side = {"左": "left", "右": "right", "上": "above", "下": "below"}
    input_options = ttk.Frame(root)
    input_options.pack(fill="x", pady=(8, 0))
    ttk.Label(input_options, text="入力共有でMacへ移る方向").pack(side="left", padx=(0, 6))
    ttk.Combobox(input_options, textvariable=mac_side_label, values=tuple(mac_side),
                 state="readonly", width=4).pack(side="left")
    ttk.Label(root, textvariable=status, wraplength=880).pack(anchor="w", pady=8)
    output = ScrolledText(root, wrap="word", height=23, font=("Consolas", 10))
    output.pack(fill="both", expand=True)
    first_use = "初回は「接続セットアップ」を押してください。Macのリモートログインを有効にして接続する手順が表示されます。"
    linked = "Mac連携済み。使いたい共有方法を選んでください。\n\n「2モニターで入力共有」または「Windows内にMacを表示」"
    unverified = "Macの接続設定は保存済みです。\nMacの電源とLANケーブルを確認し、「診断」または「接続セットアップ」を押してください。"
    output.insert("end", "保存済みのMacを確認しています…")

    def display(value):
        output.delete("1.0", "end")
        output.insert("end", value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))

    def loaded():
        if state["profile"] is None:
            raise ValueError("『Macを探す』から接続先を登録してください。設定ファイルの作成は不要です。")
        return state["profile"]

    def accept_profile(p, *, save=True):
        if save:
            path = remember_profile(p)
        else:
            path = state["path"]
        state.update(profile=p, path=str(path))
        mac_side_label.set(next(label for label, side in mac_side.items() if side == p.mac_position))

    def load(path=None):
        if state["busy"]:
            return
        path = path or filedialog.askopenfilename(title="秘密情報を含めないローカル設定", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            p = Profile.load(path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("設定を読めません", str(exc), parent=root)
            return
        accept_profile(p)
        check_home_connection(p)

    def background(label, work, on_done=None, *, on_error=None):
        if state["busy"]:
            status.set("実行中の処理が終わるまでお待ちください。")
            return
        state["busy"] = True
        status.set(label + "…")
        def worker():
            try:
                jobs.put((True, work(), on_done))
            except Exception as exc:
                jobs.put((False, str(exc), on_error))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            success, value, on_done = jobs.get_nowait()
            if success is not None:
                state["busy"] = False
                status.set("処理が終わりました。未確認項目や次の手順も確認してください。" if success else "処理を完了できませんでした。理由を確認してください。")
            if on_done:
                guarded(lambda: on_done(value))()
            else:
                display(value)
        except Empty:
            pass
        root.after(100, poll)

    def guarded(fn):
        def call():
            try:
                fn()
            except (OSError, ValueError, TypeError) as exc:
                messagebox.showerror("確認が必要です", str(exc), parent=root)
        return call

    def doctor():
        p = loaded()
        background("読み取り診断中", lambda: format_report(diagnose(p)))

    def approve_change(title, message, parent):
        return messagebox.askyesno(title, message, icon=messagebox.WARNING,
                                   default=messagebox.NO, parent=parent)

    def first_ssh(p):
        dialog = tk.Toplevel(root)
        dialog.title("初回のSSH接続")
        dialog.geometry("760x410")
        dialog.transient(root)
        ttk.Label(dialog, text=(
            "1. Macで「システム設定 → 一般 → 共有 → リモートログイン」をオンにし、接続するユーザーを許可します。"
            "\n\n2. Macの画面下にあるFinder（青と白の顔）をクリックします。画面上部の「移動」→「ユーティリティ」を開き、"
            "「ターミナル」をダブルクリックします。"
            "\n開いたターミナルに次のコマンドを入力し、Return を押して指紋を表示します。"
            "\nssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub"
            "\n\n3. Windowsで下の「SSH接続を設定する」を押します。"
        ), wraplength=700, justify="left").pack(fill="x", padx=20, pady=20)

        def bootstrap():
            report = diagnose(p)
            if any(c["code"] == "SSH_AUTH" and c["status"] == "ok" for c in report["checks"]):
                return report
            register_ssh_key(p)
            return diagnose(p)

        def completed(report):
            dialog.destroy()
            connection_result(report)

        def start():
            if state["busy"]:
                return
            if approve_change("MacへのSSH公開鍵登録",
                    f"Mac（{p.mac_ip}）へ接続します。指紋を照合して認証した後、Macの公開鍵リストへ接続専用の鍵を追加します。続けますか？", dialog):
                background("MacのSSH接続を設定中", bootstrap, completed)

        ttk.Button(dialog, text="SSH接続を設定する", command=guarded(start)).pack(anchor="w", padx=20)
        ttk.Label(dialog, text=(
            "MacとWindowsのターミナルに表示された「SHA256:」から始まる指紋を見比べます。"
            "\n完全に一致したら、Windowsのターミナルで yes と入力して Enter を押してください。"
            "\n一致しなければ、no と入力して接続を中止してください。"
            "\n\n求められたらMacのログインパスワードを入力します。認証後、WinMacLinkが公開鍵を登録し、新しい鍵で接続を確認します。"
        ), wraplength=700, justify="left").pack(fill="x", padx=20, pady=(10, 16))

    def connection_result(report):
        ready = any(c["code"] == "SSH_AUTH" and c["status"] == "ok" for c in report["checks"])
        if ready:
            status.set("")
            display(linked)
        else:
            status.set("Macへの接続を確認できませんでした。")
            display(unverified + "\n\n" + format_report(report))

    def check_home_connection(p):
        display("保存した設定でMacとの接続を確認しています…")
        background("Macとの接続を確認中", lambda: diagnose(p), connection_result,
                   on_error=lambda message: display(unverified + "\n\n" + message))

    def register(candidate=None):
        if state["busy"]:
            return
        candidate = candidate or {}
        base = state["profile"]
        context = candidate.get("lookup_context")
        from_fixed_ip = candidate.get("from_fixed_ip") is True
        steps = build_lookup_steps(context, candidate)
        pop = tk.Toplevel(root)
        pop.title("Macを確認する — 左の手順を見ながら右に入力")
        pop.geometry("1080x700")
        pop.minsize(860, 600)
        pop.transient(root)
        intro = ("Macの固定IPは前の手順から引き継ぎました。短いユーザー名を入力してください。"
                 if from_fixed_ip else "Macの短いユーザー名と、LANケーブル側のIPを確認してください。")
        ttk.Label(pop, text=intro, wraplength=1000).pack(anchor="w", padx=20, pady=12)
        columns = ttk.Frame(pop); columns.pack(fill="both", expand=True, padx=20)
        left = ttk.Frame(columns); left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(columns, width=300); right.pack(side="right", fill="y", padx=(18,0))
        index = tk.IntVar(value=0)
        heading = ttk.Label(left, font=("Segoe UI", 14, "bold")); heading.pack(anchor="w", pady=(0,10))
        instructions = ScrolledText(left, wrap="word", height=21, font=("Segoe UI",11))
        instructions.pack(fill="both", expand=True)
        values = {"host": candidate.get("host") or (base.host if base else ""),
                  "user": (context.get("user") if context and context.get("verified") else None) or (base.user if base else "")}
        entries = {}
        for key, label in [("user", "Macのユーザー名（短い名前）"), ("host", "Macの有線IPアドレス")]:
            ttk.Label(right, text=label).pack(anchor="w", pady=(12,5))
            var = tk.StringVar(value=values[key]); entries[key] = var
            ttk.Entry(right, textvariable=var, width=30,
                      state="readonly" if key == "host" and from_fixed_ip else "normal").pack(fill="x")
        ttk.Label(right, text="名前はApple Account名やフルネームではありません。\nIPはWi-Fi側ではなくLANケーブル側です。", wraplength=280, justify="left").pack(anchor="w", pady=14)
        badge = "登録済みMacから読み取り確認" if context and context.get("verified") else "初回・未確認：実画面で照合してください"
        ttk.Label(right, text=badge, wraplength=280).pack(anchor="w", pady=6)
        ttk.Label(right, text="初回はWindowsで接続専用の鍵を用意します。Macでの接続許可と鍵の登録は、次の画面で案内します。", wraplength=280).pack(anchor="w", pady=12)
        open_button = ttk.Button(left, text="Macの確認画面を開く（接続済みの場合）")
        open_button.pack(anchor="w", pady=8)
        def update():
            step = steps[index.get()]
            heading.configure(text=f"{index.get()+1}/{len(steps)}  {step['title']}")
            sections = [step["path"]]
            if step["field"]:
                sections.append(f"見る欄\n{step['field']}")
            if step["value"]:
                label = "前の手順で設定したMacの固定IP" if step["panel"] == "network" and from_fixed_ip else (
                    "接続先から確認した値" if context and context.get("verified") else "有線IPの候補")
                sections.append(f"{label}\n{step['value']}")
            sections.append(step["body"])
            text = "\n\n".join(sections)
            instructions.configure(state="normal"); instructions.delete("1.0","end"); instructions.insert("end", text); instructions.configure(state="disabled")
            enabled = base is not None and candidate.get("identity_verified") and step["panel"] is not None
            open_button.configure(state="normal" if enabled else "disabled", command=guarded(lambda: background("Macの確認画面を開く", lambda: open_mac_panel(base, step["panel"]))))
        def move(delta):
            index.set(max(0, min(len(steps)-1,index.get()+delta))); update()
        nav = ttk.Frame(left); nav.pack(fill="x", pady=8)
        ttk.Button(nav, text="前の手順", command=lambda: move(-1)).pack(side="left")
        ttk.Button(nav, text="次の手順", command=lambda: move(1)).pack(side="left", padx=8)
        ttk.Button(right, text="ユーザー名の見方", command=lambda: (index.set(0), update())).pack(fill="x", pady=5)
        ttk.Button(right, text="有線IPの見方", command=lambda: (index.set(1), update())).pack(fill="x", pady=5)
        def save():
            if state["busy"]:
                return
            values = {key: variable.get().strip() for key, variable in entries.items()}
            p = registration_profile(base, candidate, values["user"], values["host"])
            new_connection = base is None or p.host_key_alias != base.host_key_alias
            if new_connection and not approve_change(
                    "Macの新規登録", f"Mac（{p.mac_ip}）をこのPCに保存し、接続専用のSSH鍵を作成します。続けますか？", pop):
                return
            def finish(prepared):
                accept_profile(prepared)
                if pop.winfo_exists():
                    pop.destroy()
                first_ssh(prepared)
            if new_connection:
                background("接続専用のSSH鍵を準備しています", lambda: prepare_new_connection(p), finish)
            else:
                finish(p)
        ttk.Label(
            right,
            text=("ユーザー名を入力したら「確認した内容でMacを記憶」を押します。"
                  if from_fixed_ip else "ユーザー名と有線IPを確認したら「確認した内容でMacを記憶」を押します。"),
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(14, 4))
        ttk.Button(right, text="確認した内容でMacを記憶", command=guarded(save)).pack(fill="x", pady=(0, 12))
        update()

    def found(candidates):
        if isinstance(candidates, dict):
            networks = candidates["networks"]
            candidates = candidates["candidates"]
        else:
            networks = []
        if not candidates:
            status.set("接続履歴に候補がありません。Macの有線IPを確認するか、セットアップ案内へ進んでください。")
            register({"windows_networks": networks})
            return
        if len(candidates) == 1 and candidates[0].get("identity_verified") and state["profile"]:
            item = candidates[0]
            status.set(f"{item['name']}：登録済みの鍵で接続とmacOSを確認しました。")
            display("使うMacを確認できました。\n\n" + candidate_label(item) + "\n有線IP：" + item["host"] + "\n\n一覧からIPを選ぶ必要はありません。『Mac画面を開く』へ進めます。")
            register(item)
            return
        if len(candidates) == 1 and not candidates[0].get("registered"):
            register(candidates[0])
            return
        pop = tk.Toplevel(root); pop.title("有線LANの接続先 — Wi-Fi側の機器は除外")
        pop.geometry("850x420")
        ttk.Label(pop, text="登録済みMacを上に表示しています。『未確認』の機器をMacと決めつけないでください。", wraplength=790).pack(pady=14)
        listing = tk.Listbox(pop, height=10)
        listing.pack(fill="both", expand=True, padx=20)
        for candidate in candidates:
            listing.insert("end", candidate_label(candidate))
        def choose():
            selected = listing.curselection()
            if not selected:
                return
            candidate = candidates[selected[0]]; pop.destroy()
            if candidate.get("identity_verified") and state["profile"]:
                status.set("登録済みMacを確認しました。『Mac画面を開く』へ進めます。")
                register(candidate)
            else:
                register(candidate)
        ttk.Button(pop, text="選んだ候補で続ける", command=choose).pack(pady=12)

    def search():
        p = state["profile"]
        def work():
            candidates = discover(p)
            if p:
                saved = next((item for item in candidates if item.get("identity_verified")), None)
                if saved is not None:
                    try:
                        saved["lookup_context"] = collect_context(p)
                    except (OSError, ValueError):
                        pass
            networks = []
            if not candidates:
                try:
                    networks = wired_networks()
                except (OSError, ValueError):
                    pass
            return {"candidates": candidates, "networks": networks}
        background("有線LANの候補とMacに合った確認手順を準備しています", work, found)

    def fixed_ip(*, start_windows=False):
        p = state["profile"] or Profile()
        if p.topology != "direct" or ipaddress.IPv4Address(p.windows_ip).is_link_local:
            defaults = Profile()
            p = replace(p, topology="direct", host=defaults.mac_ip,
                        windows_ip=defaults.windows_ip, mac_ip=defaults.mac_ip, prefix=defaults.prefix)
        pop = tk.Toplevel(root)
        pop.title("直結LANの固定IP")
        pop.geometry("780x540")
        pop.transient(root)
        values = ttk.Frame(pop)
        values.pack(fill="x", padx=16, pady=(12, 0))
        fields = {}
        for column, (name, label) in enumerate((
            ("windows_ip", "WindowsのIPv4"), ("mac_ip", "MacのIPv4"), ("prefix", "プレフィックス長")
        )):
            ttk.Label(values, text=label).grid(row=0, column=column, sticky="w", padx=(0, 12))
            fields[name] = tk.StringVar(value=str(getattr(p, name)))
            ttk.Entry(values, textvariable=fields[name], width=18).grid(row=1, column=column, padx=(0, 12))

        def selected_profile():
            mac_ip = fields["mac_ip"].get().strip()
            return replace(p, host=mac_ip, mac_ip=mac_ip,
                           windows_ip=fields["windows_ip"].get().strip(),
                           prefix=int(fields["prefix"].get()), topology="direct")

        instructions = ScrolledText(pop, wrap="word", font=("Segoe UI", 11))
        instructions.pack(fill="both", expand=True, padx=16, pady=12)

        def update_instructions():
            selected = selected_profile()
            if ipaddress.IPv4Address(selected.windows_ip).is_link_local:
                raise ValueError("固定IPには169.254で始まるアドレス以外を指定してください。")
            mask = ipaddress.IPv4Network(f"{selected.windows_ip}/{selected.prefix}", strict=False).netmask
            mac_steps = "\n".join(mac_fixed_ip_steps(selected))
            instructions.configure(state="normal")
            instructions.delete("1.0", "end")
            instructions.insert("end", f"""1. WindowsとMacの直結専用ポートを確認する
接続履歴が0台でも始められます。Windowsでは専用アダプターを選びます。Macは初回に本体の画面と入力機器を使います。

2. Windowsに固定IPを設定する
「Windowsの固定IPを設定・復元」を押し、UACで許可します。有効な有線ポートが1つなら自動で選びます。候補が複数の場合は直結ポートを選び、表示された変更内容を確認します。
WindowsのIPv4: {selected.windows_ip} / {selected.prefix}（マスク {mask}）

3. Macに固定IPを設定する
復元に備えて、変更前のIPv4設定を控えます。
{mac_steps}

4. SSHを設定して確認する
Macの一般 → 共有 → リモートログインで接続するアカウントを許可します。応答が届けば初回セットアップは自動で登録画面に進みます。待機が終わっていたら「Windows側を確認してMac登録へ」を押します。Macの短いユーザー名を入力し、SSHの指紋を照合すると、WinMacLinkが公開鍵の登録と接続テストを行います。

5. Macの画面を確認する
Macの一般 → 共有で画面共有を許可します。Windowsで「Mac画面を開く」を押し、TigerVNCの認証画面で認証します。画面が表示されたらクリックと文字入力を試します。

元に戻す
Windowsは同じボタンから復元の確認を開きます。Macは控えた値をTCP/IP画面で戻します。
""")
            instructions.configure(state="disabled")
            return selected

        deadline = 0

        def start_monitoring():
            nonlocal deadline
            deadline = time.monotonic() + 180
            continue_setup(automatic=True)

        def apply_windows():
            selected = update_instructions()
            background("管理者画面を開く", lambda: open_windows_fixed_ip(selected),
                       lambda _: start_monitoring() if start_windows and pop.winfo_exists() else None)

        buttons = ttk.Frame(pop)
        buttons.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(buttons, text="案内の数値を更新", command=guarded(update_instructions)).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Windowsの固定IPを設定・復元",
                   command=guarded(apply_windows)).pack(side="left")
        def continue_setup(*, automatic=False):
            if not pop.winfo_exists() or (automatic and time.monotonic() >= deadline):
                return
            if state["busy"]:
                return
            selected = update_instructions()

            def check():
                matching = [network for network in wired_networks()
                            if network["ip"] == selected.windows_ip and network["prefix"] == selected.prefix]
                return len(matching) == 1 and direct_ssh_ready(selected)

            def checked(ready):
                if not pop.winfo_exists():
                    return
                if ready and selected_profile() == selected:
                    pop.destroy()
                    register({"host": selected.mac_ip, "windows_ip": selected.windows_ip,
                              "windows_prefix": selected.prefix, "from_fixed_ip": True})
                else:
                    status.set("MacのEthernetを設定し、リモートログインをオンにすると登録へ進めます。")
                    if automatic:
                        pop.after(2500, guarded(lambda: continue_setup(automatic=True)))

            background("直結LANでMacのSSH応答を待っています", check, checked)

        ttk.Button(buttons, text="Windows側を確認してMac登録へ",
                   command=guarded(continue_setup)).pack(side="left", padx=8)
        update_instructions()
        if start_windows:
            guarded(apply_windows)()

    def guide():
        pop = tk.Toplevel(root)
        pop.title("WinMacLinkのセットアップ")
        pop.geometry("800x650")
        pop.transient(root)
        index = tk.IntVar(value=0)
        title = ttk.Label(pop, font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", padx=20, pady=16)
        body = ttk.Label(pop, wraplength=710, justify="left")
        body.pack(fill="x", padx=20, pady=8)
        settings = ttk.Frame(pop)
        settings.pack(fill="x", padx=20, pady=12)

        def prepare_windows():
            if state["busy"]:
                return
            p = state["profile"] or Profile()
            missing = windows_setup_packages(p.viewer)
            if not missing:
                messagebox.showinfo("Windowsの準備", "DeskflowとTigerVNCは導入済みです。固定IPの設定またはMacの登録へ進めます。", parent=pop)
                return
            names = {"deskflow": "Deskflow", "tigervnc": "TigerVNC"}
            packages = "、".join(names[name] for name in missing)
            if not approve_change("Windowsへのソフトの導入",
                    f"{packages}をWinGetからインストールします。配布元とパッケージの利用条件に同意します。管理者の許可画面が出る場合があります。続けますか？", pop):
                return
            def run_installers():
                completed = []
                for component in missing:
                    try:
                        install(component, execute=True)
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        done = "、".join(completed) or "なし"
                        raise ValueError(f"{names[component]}の導入で停止しました。完了分は {done} です。\n{exc}") from exc
                    completed.append(names[component])
                remaining = windows_setup_packages(p.viewer)
                if remaining:
                    pending = "、".join(names[name] for name in remaining)
                    raise ValueError(f"{pending}の実行ファイルを確認できません。")
                return f"Windowsへの導入を確認しました。{packages}"
            def finished(result):
                display(result)
                if pop.winfo_exists():
                    messagebox.showinfo("Windowsの準備", result, parent=pop)
            background("Windows用のソフトを導入中", run_installers, finished)

        ttk.Button(settings, text="Windowsを準備する", command=guarded(prepare_windows)).pack(anchor="w", pady=4)
        def open_connection_setup():
            pop.destroy()
            if state["profile"] is None:
                search()
            else:
                first_ssh(state["profile"])
        ttk.Button(settings, text="直結LANの固定IPを設定", command=guarded(fixed_ip)).pack(anchor="w", pady=4)
        ttk.Button(settings, text="Macの登録・初回SSH接続", command=guarded(open_connection_setup)).pack(anchor="w", pady=4)
        ttk.Button(settings, text="Windowsの有線LAN設定を開く", command=guarded(open_windows_network)).pack(anchor="w", pady=4)
        mac_button = ttk.Button(settings, text="Macの該当設定を開く")
        mac_button.pack(anchor="w", pady=4)
        ttk.Button(settings, text="Windows内のVNC窓を開く", command=guarded(screen)).pack(anchor="w", pady=4)
        ttk.Label(pop, text="『次へ』は手順を読む操作です。許可完了や機能の成功を証明するものではありません。", wraplength=710).pack(anchor="w", padx=20, pady=8)
        nav = ttk.Frame(pop)
        nav.pack(side="bottom", fill="x", padx=20, pady=16)

        def update():
            name, text, panel = STEPS[index.get()]
            title.configure(text=f"{index.get()+1}/{len(STEPS)}  {name}")
            body.configure(text=text)
            mac_button.configure(state="normal" if panel else "disabled",
                                 command=guarded(lambda: background("Macの設定画面を開く", lambda: open_mac_panel(loaded(), panel))))

        def move(delta):
            index.set(max(0, min(len(STEPS)-1, index.get()+delta)))
            update()

        def stage():
            p = loaded()
            base = Path(state["path"]).parent / ("staged-" + uuid.uuid4().hex[:8])
            expected = plan(p, base)
            review = tk.Toplevel(pop)
            review.title("適用前の確認 — 作業フォルダーへの保存のみ")
            review.geometry("820x600")
            view = ScrolledText(review, wrap="word")
            view.pack(fill="both", expand=True)
            view.insert("end", json.dumps(expected, ensure_ascii=False, indent=2))
            def save():
                if not approve_change("設定ファイルの作成", "表示した設定ファイルをWinMacLinkの作業フォルダーに保存します。続けますか？", review):
                    return
                result = apply(p, expected)
                review.destroy()
                display(result)
                status.set("設定ファイルを保存しました。OS設定は変更していません。")
            ttk.Button(review, text="この内容を作業フォルダーへ保存", command=guarded(save)).pack(pady=10)
        ttk.Button(nav, text="戻る", command=lambda: move(-1)).pack(side="left")
        ttk.Button(nav, text="次へ", command=lambda: move(1)).pack(side="left", padx=8)
        ttk.Button(nav, text="設定案を作って内容を確認", command=guarded(stage)).pack(side="right")
        update()

    def screen():
        p = loaded()
        background("画面接続中・認証はビューアーへ入力（終了するにはVNC窓を閉じる）", lambda: connect(p))

    def connection_setup():
        pop = tk.Toplevel(root)
        pop.title("接続セットアップ")
        pop.geometry("680x275")
        pop.transient(root)
        ttk.Label(pop, text=(
            "Mac本体で「システム設定 → 一般 → 共有 → リモートログイン」をオンにします。"
            "\n接続するMacユーザーを許可し、WindowsとMacをLANケーブルで直結してください。"
        ), wraplength=630, justify="left").pack(anchor="w", padx=20, pady=20)

        def start():
            if state["busy"]:
                return
            pop.destroy()
            p = state["profile"]
            if p is None or p.topology != "direct" or ipaddress.ip_address(p.mac_ip).is_link_local:
                fixed_ip(start_windows=True)
            else:
                first_ssh(p)

        ttk.Button(pop, text="セットアップを進める", command=guarded(start)).pack(anchor="w", padx=20)

    def setup_deskflow():
        if state["busy"]:
            return
        direction = mac_side_label.get()
        p = replace(loaded(), mac_position=mac_side[direction])
        current = state.get("deskflow_process")
        if not approve_change(
            "2モニターで入力共有",
            "Deskflowが入っていない場合、Windowsから公式配布元に接続して必要な版を取得し、両機に導入します。"
            "\nその後、設定と証明書を揃えて入力共有を開始します。"
            f"\nWindows画面の{direction}端をMacへの切り替えに使います。実行中の入力共有があれば切り替えます。"
            "\n\nMacでアクセシビリティやローカルネットワークの許可を求められた場合は、Mac本体で許可してください。"
            "\n\n開始しますか？",
            root,
        ):
            return

        cancel = threading.Event()
        permission_window = None

        def show_permission(error):
            nonlocal permission_window
            status.set("Macの入力許可を待っています。許可されると自動で続きます。")
            permission_window = tk.Toplevel(root)
            permission_window.title("MacでDeskflowの入力を許可")
            permission_window.transient(root)
            instructions = (
                "1. Windowsで下のボタンを押し、MacのFinderに追加するファイルを表示します。"
                "Macで「＋」から開いたファイル選択画面が出ている場合は、先に「キャンセル」で閉じます。\n\n"
                "2. MacのFinderで選択されたファイルを「デバイスの制御とデータへのアクセス」または"
                "「アクセシビリティ」のアプリが並んでいる一覧へドラッグします。"
                "Finderのファイルをダブルクリックする必要はありません。\n\n"
                "3. Deskflow本体と deskflow-core のスイッチを両方オンにします。既に一覧にある項目はスイッチだけ確認します。"
                "WinMacLinkが接続を再試行します。待機が終わっていたら、Windowsで「2モニターで入力共有」を押し直します。"
            )
            ttk.Label(permission_window, text=instructions, wraplength=540, justify="left").pack(anchor="w", padx=18, pady=16)
            feedback = tk.StringVar(value=error or "MacのFinderに deskflow-core を表示するよう指示しました。")
            buttons = ttk.Frame(permission_window)
            buttons.pack(anchor="w", padx=18)
            ttk.Label(permission_window, textvariable=feedback, wraplength=540).pack(anchor="w", padx=18, pady=12)

            def reveal(target, name):
                for button in buttons.winfo_children():
                    button.state(["disabled"])
                feedback.set("Macでファイルを表示しています…")

                def finished(message):
                    if permission_window.winfo_exists():
                        feedback.set(message)
                        for button in buttons.winfo_children():
                            button.state(["!disabled"])

                def work():
                    try:
                        open_deskflow_permissions(p, target)
                        message = f"MacのFinderに {name} を表示するよう指示しました。"
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        message = str(exc)
                    jobs.put((None, message, finished))

                threading.Thread(target=work, daemon=True).start()

            for target, name in (("app", "Deskflow本体"), ("core", "deskflow-core")):
                ttk.Button(buttons, text=f"Macで {name} を表示", command=lambda t=target, n=name: reveal(t, n)).pack(side="left", padx=(0, 6))
            ttk.Button(permission_window, text="中止", command=cancel.set).pack(pady=(0, 12))
            permission_window.protocol("WM_DELETE_WINDOW", cancel.set)

        def request_permission():
            error = None
            try:
                open_deskflow_permissions(p)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                error = str(exc)
            jobs.put((None, error, show_permission))
            return cancel

        def show_result(value):
            if permission_window is not None:
                permission_window.destroy()
            display(value)

        def connected(process):
            state["deskflow_process"] = process
            show_result(f"Deskflowの接続を確認しました。Windows画面の{direction}端からMacに移動できます。")

        def work():
            report = diagnose(p)
            if not any(check["code"] == "SSH_AUTH" and check["status"] == "ok" for check in report["checks"]):
                raise ValueError("先に『接続セットアップ』でMacへのSSH接続を設定してください。")
            if current and current.poll() is None:
                current.terminate()
                current.wait(timeout=5)
            return activate_pair(p, request_permission=request_permission)

        background("Deskflowを導入・設定し、接続を確認しています", work, connected, on_error=show_result)

    def setup_vnc():
        existing = state.get("vnc_setup_dialog")
        if existing and existing.winfo_exists():
            existing.lift()
            return
        if state["busy"]:
            return
        p = loaded()
        missing = "tigervnc" in windows_setup_packages(p.viewer)
        if missing and not approve_change(
            "Windows内にMacを表示",
            "TigerVNCをWinGetから導入し、配布元とパッケージの利用条件に同意します。"
            "Macの画面共有をオンにすると、WinMacLinkが接続を続けます。開始しますか？",
            root,
        ):
            return

        pop = tk.Toplevel(root)
        state["vnc_setup_dialog"] = pop
        pop.title("Windows内にMacを表示")
        pop.geometry("720x315")
        pop.transient(root)
        ttk.Label(pop, text=(
            "Macの画面共有をオンにする必要がある場合は、WinMacLinkがMacの共有設定を開きます。"
            "\nMac本体で「システム設定 → 一般 → 共有 → 画面共有」のⓘを開き、画面共有をオンにします。"
            "VNC用のパスワードを指定する場合は、Macの設定画面で入力してください。"
            "\n\n画面共有の応答を確認すると、WindowsでVNCビューアーが自動で開きます。"
        ), wraplength=670, justify="left").pack(anchor="w", padx=20, pady=16)
        ttk.Label(pop, textvariable=status, wraplength=670, justify="left").pack(anchor="w", padx=20, pady=(0, 12))
        ttk.Button(pop, text="閉じる", command=pop.destroy).pack(anchor="w", padx=20)

        def sharing_ready():
            report = diagnose(p)
            checks = {check["code"]: check["status"] for check in report["checks"]}
            if checks.get("SSH_AUTH") != "ok":
                raise ValueError("先に『接続セットアップ』でMacへのSSH接続を設定してください。")
            return checks.get("MAC_VNC") == "ok"

        def prepare():
            ready = sharing_ready()
            if not ready:
                try:
                    open_mac_panel(p, "sharing")
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass  # The same navigation is available on the Mac itself.
            if missing:
                install("tigervnc", execute=True)
                if "tigervnc" in windows_setup_packages(p.viewer):
                    raise ValueError("TigerVNCの実行ファイルを確認できません。")
            return ready

        deadline = None

        def advance(ready):
            nonlocal deadline
            if not pop.winfo_exists():
                return
            if ready:
                pop.destroy()
                background("Macの画面共有を開いています", lambda: connect(p))
                return
            if deadline is None:
                deadline = time.monotonic() + 180
            if time.monotonic() >= deadline:
                pop.destroy()
                status.set("画面共有の待機を終了しました。Macでオンにして「Windows内にMacを表示」を押してください。")
                return
            status.set("Macの画面共有を待っています。オンになるとVNC窓を開きます。")
            pop.after(2000, check_again)

        def check_again():
            if not pop.winfo_exists():
                return
            if state["busy"]:
                pop.after(1000, check_again)
                return
            background("Macの画面共有を確認しています", sharing_ready, advance, on_error=failed)

        def failed(message):
            if pop.winfo_exists():
                pop.destroy()
            display(message)

        background("画面共有の確認とTigerVNCの準備中", prepare, advance, on_error=failed)

    def undo():
        destination = filedialog.askdirectory(title="このツールが生成した作業フォルダーを選択")
        if destination and approve_change("生成した設定の復元", "選んだ作業フォルダー内の生成ファイルを復元します。続けますか？", root):
            background("生成ファイルを復元中", lambda: rollback(destination))

    for text, action in [("接続セットアップ", connection_setup),
                         ("2モニターで入力共有", setup_deskflow),
                         ("Windows内にMacを表示", setup_vnc),
                         ("診断", doctor), ("詳細設定", guide), ("変更を戻す", undo)]:
        ttk.Button(tools, text=text, command=guarded(action)).pack(side="left", padx=(0, 6))
    root.after(100, poll)
    def close():
        if state["busy"]:
            messagebox.showinfo("処理中", "診断の終了を待つか、開いているVNC窓を閉じてください。接続用トンネルを片付けてから終了します。", parent=root)
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    def startup():
        p, path, errors = find_profile(profile_path)
        if p:
            state["path"] = str(path)
            accept_profile(p, save=False)
            check_home_connection(p)
        else:
            display(first_use + ("\n\n" + "\n".join(errors) if errors else ""))
    root.after(150, guarded(startup))
    root.mainloop()
