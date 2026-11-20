import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from .profile import Profile
from .doctor import diagnose
from .transaction import plan, apply, rollback
from .runtime import install, connect
from .mac_install import install_mac


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="WinMacLink: diagnose first; review changes; apply explicitly")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create an example profile (never overwrites)")
    init.add_argument("path")
    doctor = sub.add_parser("doctor", help="Read-only diagnosis; JSON reports redact endpoint identities")
    doctor.add_argument("--profile", required=True)
    doctor.add_argument("--output")
    stage = sub.add_parser("plan", help="Preview staged files; does not change the OS")
    stage.add_argument("--profile", required=True)
    stage.add_argument("--destination", required=True)
    stage.add_argument("--output", required=True)
    commit = sub.add_parser("apply", help="Write only reviewed staged files, not network settings")
    commit.add_argument("--profile", required=True)
    commit.add_argument("--plan", required=True)
    undo = sub.add_parser("rollback", help="Restore staged files; refuse to erase user edits")
    undo.add_argument("--destination", required=True)
    package = sub.add_parser("install", help="Preview a Windows installer; --execute opts in")
    package.add_argument("component", choices=["deskflow", "tigervnc"])
    package.add_argument("--execute", action="store_true")
    screen = sub.add_parser("connect", help="Foreground VNC via an owned SSH tunnel")
    screen.add_argument("--profile", required=True)
    mac = sub.add_parser("install-mac", help="Preview pinned Mac Deskflow install; --execute opts in")
    mac.add_argument("--profile", required=True)
    mac.add_argument("--execute", action="store_true")
    gui = sub.add_parser("gui", help="Open the native local setup/diagnosis window")
    gui.add_argument("--profile")
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import launch
            launch(args.profile)
        elif args.command == "init":
            with Path(args.path).open("x", encoding="utf-8") as file:
                json.dump(asdict(Profile()), file, ensure_ascii=False, indent=2)
            emit({"state": "created", "next_step": "Edit endpoint, user, identity and host-key alias locally. Never add passwords."})
        elif args.command == "install":
            emit(install(args.component, args.execute))
        elif args.command == "rollback":
            emit(rollback(args.destination))
        else:
            p = Profile.load(args.profile)
            if args.command == "install-mac":
                emit(install_mac(p, args.execute))
            elif args.command == "doctor":
                report = diagnose(p)
                if args.output:
                    # Private profile, plans and journals must not be committed.
                    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                emit(report)
                return 2 if any(c["status"] == "error" for c in report["checks"]) else 0
            if args.command == "plan":
                result = plan(p, args.destination)
                with Path(args.output).open("x", encoding="utf-8") as file:
                    json.dump(result, file, ensure_ascii=False, indent=2)
                emit({"state": "planned", "files": len(result["files"]), "effects": result["effects"]})
            elif args.command == "apply":
                result = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
                emit(apply(p, result))
            elif args.command == "connect":
                emit(connect(p))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        # Keep remote raw logs out of public reports. Console remains visible.
        emit({"state": "failed", "error_type": type(exc).__name__, "message": str(exc)})
        return 2
    except KeyboardInterrupt:
        emit({"state": "cancelled"})
        return 130


if __name__ == "__main__":
    sys.exit(main())
