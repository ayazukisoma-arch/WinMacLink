"""Plan/apply/rollback staged files, detecting concurrent or user edits."""
import base64
import hashlib
import json
import sys
from pathlib import Path
from .setup import render


def digest(data):
    return hashlib.sha256(data).hexdigest()


def artifact_bytes(name, content):
    # Windows PowerShell 5 reads non-BOM UTF-8 as ANSI; POSIX shell needs no BOM.
    return content.encode("utf-8-sig" if name.endswith(".ps1") else "utf-8")


def file_hash(path):
    return digest(path.read_bytes()) if path.exists() else None


def checked_root(path):
    path = Path(path).absolute()
    system_aliases = {Path("/var"): Path("/private/var"), Path("/tmp"): Path("/private/tmp"),
                      Path("/etc"): Path("/private/etc")} if sys.platform == "darwin" else {}
    for parent in (path, *path.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            if parent in system_aliases and parent.resolve() == system_aliases[parent]:
                continue
            raise ValueError("Symlink/junction destinations are not supported")
    return path.resolve()


def checked_file(root, name):
    if Path(name).name != name or name in (".", ".."):
        raise ValueError("Unsafe staged filename")
    path = root / name
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("Symlink/junction target refused")
    if path.exists() and not path.is_file():
        raise ValueError("Target is not a regular file")
    return path


def plan(profile, destination):
    root = checked_root(destination)
    if (root / "transaction.json").exists():
        raise ValueError("Existing transaction: rollback it or use another output directory")
    files = []
    for name, content in render(profile).items():
        path = checked_file(root, name)
        files.append({"name": name, "content": content, "before_sha256": file_hash(path)})
    return {"schema": 1, "destination": str(root), "files": files,
            "effects": "staged files only; no network, permissions, startup or downloads are changed"}


def apply(profile, expected):
    # A plan is not a command language: regenerate all permitted contents.
    current = plan(profile, expected.get("destination", ""))
    if expected != current:
        raise ValueError("Plan changed or target files changed; generate and review a new plan")
    root = checked_root(current["destination"])
    root.mkdir(parents=True, exist_ok=True)
    journal_path = root / "transaction.json"
    journal = {"schema": 1, "state": "applying", "files": []}
    for item in current["files"]:
        path = checked_file(root, item["name"])
        previous = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
        journal["files"].append({"name": item["name"], "before": previous,
                                 "after_sha256": digest(artifact_bytes(item["name"], item["content"]))})
    # Exclusive journal creation avoids overwriting an existing transaction.
    with journal_path.open("x", encoding="utf-8") as f:
        json.dump(journal, f, indent=2)
    try:
        for item in current["files"]:
            path = checked_file(root, item["name"])
            if file_hash(path) != item["before_sha256"]:
                raise ValueError("File changed during apply")
            path.write_bytes(artifact_bytes(item["name"], item["content"]))
        journal["state"] = "applied"
        journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
    except Exception:
        # Keep durable recovery information; do not erase user changes.
        raise
    return {"state": "applied", "files": len(current["files"]), "destination": str(root)}


def rollback(destination):
    root = checked_root(destination)
    journal_path = checked_file(root, "transaction.json")
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("schema") != 1 or journal.get("state") not in ("applied", "applying"):
        raise ValueError("No active transaction")
    allowed = {"layout.conf", "windows-server.ini", "mac-client.ini", "mac-permissions.txt", "mac-fixed-ip.sh", "windows-fixed-ip.ps1"}
    prepared = []
    seen = set()
    for item in journal["files"]:
        name = item["name"]
        if name not in allowed or name in seen:
            raise ValueError("Invalid journal filename")
        seen.add(name)
        path = checked_file(root, name)
        before = base64.b64decode(item["before"], validate=True) if item["before"] is not None else None
        now = file_hash(path)
        prior_hash = digest(before) if before is not None else None
        if now not in (item["after_sha256"], prior_hash):
            raise ValueError(f"User edits detected in {name}; rollback refused without changing any files")
        prepared.append((path, before))
    for path, before in prepared:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)
    journal["state"] = "rolled-back"
    journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
    return {"state": "rolled-back", "files": len(prepared)}
