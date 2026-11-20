from dataclasses import replace
from pathlib import Path
import copy
import json
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from winmaclink.profile import Profile, ssh_arguments
from winmaclink.doctor import classify_ssh, diagnose
from winmaclink.setup import render
from winmaclink.transaction import plan, apply, rollback
from winmaclink.runtime import connect, install_command, tunnel_arguments
from winmaclink.cli import main
from winmaclink.mac_install import install_mac, install_script, HASHES


class ProfileTests(unittest.TestCase):
    def test_reject_shell_injection(self):
        for field, value in [("host", "-oProxyCommand=evil"), ("user", "a;touch x"),
                             ("mac_name", "x\nend"), ("host_key_alias", "x y")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(Profile(), **{field: value})

    def test_network_boundaries(self):
        for values in [dict(windows_ip="192.168.250.0"), dict(mac_ip="192.168.250.3"),
                       dict(mac_ip="192.168.250.1"), dict(mac_ip="192.168.251.2"),
                       dict(mac_ip="8.8.8.8"), dict(local_port=True), dict(prefix=True),
                       dict(windows_ip="0.0.0.1", mac_ip="0.0.0.2"), dict(prefix=8)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(Profile(), **values)

    def test_unknown_secrets_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.json"
            path.write_text(json.dumps({"password": "secret"}))
            with self.assertRaisesRegex(ValueError, "Unknown profile"):
                Profile.load(path)

    def test_bom_profile_and_unicode_key_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "設定.json"
            path.write_text(json.dumps({"identity": "C:/利用者/鍵/key"}), encoding="utf-8-sig")
            p = Profile.load(path)
            self.assertEqual(p.identity, "C:/利用者/鍵/key")
            args = ssh_arguments(p)
            self.assertIn("StrictHostKeyChecking=yes", args)
            self.assertIn(str(Path("C:/利用者/鍵/key")), args)

    def test_public_redaction(self):
        p = replace(Profile(), user="private-user", host="private-host")
        text = json.dumps(p.public())
        self.assertNotIn("private-user", text)
        self.assertNotIn("private-host", text)


class RenderingTests(unittest.TestCase):
    def test_all_positions(self):
        for position, a, b in [("left", "left", "right"), ("right", "right", "left"),
                               ("above", "up", "down"), ("below", "down", "up")]:
            content = render(replace(Profile(), mac_position=position))["layout.conf"]
            self.assertIn(f"{a} = mac-mini", content)
            self.assertIn(f"{b} = windows-main", content)

    def test_lan_does_not_render_fixed_network_mutations(self):
        files = render(replace(Profile(), topology="lan"))
        self.assertNotIn("windows-fixed-ip.ps1", files)
        self.assertNotIn("mac-fixed-ip.sh", files)
        self.assertNotIn("interface=", files["windows-server.ini"])

    def test_tls_and_desktop_mode_preserved(self):
        for name in ("windows-server.ini", "mac-client.ini"):
            text = render(Profile())[name]
            self.assertIn("processMode=1", text)
            self.assertIn("tlsEnabled=true", text)
            self.assertIn("checkPeerFingerprints=true", text)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "日本語 空白"
        self.p = Profile()

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_is_read_only(self):
        plan(self.p, self.root)
        self.assertFalse(self.root.exists())

    def test_apply_then_rollback_restores_bytes_and_unrelated_files(self):
        self.root.mkdir()
        before = b"original\r\n"
        (self.root / "layout.conf").write_bytes(before)
        (self.root / "unrelated.txt").write_text("keep")
        apply(self.p, plan(self.p, self.root))
        rollback(self.root)
        self.assertEqual((self.root / "layout.conf").read_bytes(), before)
        self.assertEqual((self.root / "unrelated.txt").read_text(), "keep")
        self.assertFalse((self.root / "mac-client.ini").exists())

    def test_tampered_plan_rejected(self):
        original = plan(self.p, self.root)
        for field, value in [("name", "../escape"), ("content", "malicious")]:
            modified = copy.deepcopy(original)
            modified["files"][0][field] = value
            with self.assertRaises(ValueError):
                apply(self.p, modified)
            self.assertFalse(self.root.exists())

    def test_changed_after_review_rejected(self):
        p = plan(self.p, self.root)
        self.root.mkdir()
        (self.root / "layout.conf").write_text("new user change")
        with self.assertRaises(ValueError):
            apply(self.p, p)
        self.assertEqual((self.root / "layout.conf").read_text(), "new user change")

    def test_rollback_refuses_all_when_any_file_edited(self):
        apply(self.p, plan(self.p, self.root))
        (self.root / "mac-client.ini").write_text("user editing")
        before = (self.root / "layout.conf").read_bytes()
        with self.assertRaisesRegex(ValueError, "User edits"):
            rollback(self.root)
        self.assertEqual((self.root / "layout.conf").read_bytes(), before)
        self.assertEqual((self.root / "mac-client.ini").read_text(), "user editing")

    def test_duplicate_apply_refused(self):
        p = plan(self.p, self.root)
        apply(self.p, p)
        with self.assertRaises(ValueError):
            apply(self.p, p)

    def test_platform_specific_encoding(self):
        apply(self.p, plan(self.p, self.root))
        self.assertTrue((self.root / "mac-fixed-ip.sh").read_bytes().startswith(b"#!/bin/sh"))
        self.assertTrue((self.root / "windows-fixed-ip.ps1").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_rollback_malformed_journal_does_not_traverse(self):
        apply(self.p, plan(self.p, self.root))
        path = self.root / "transaction.json"
        journal = json.loads(path.read_text())
        journal["files"][0]["name"] = "../escape"
        path.write_text(json.dumps(journal))
        with self.assertRaises(ValueError):
            rollback(self.root)

    def test_symlink_target_refused(self):
        self.root.mkdir()
        target = self.root / "unrelated"
        target.write_text("keep")
        try:
            (self.root / "layout.conf").symlink_to(target)
        except OSError:
            self.skipTest("OS does not allow symlink creation for this account")
        with self.assertRaises(ValueError):
            plan(self.p, self.root)


class DiagnosisTests(unittest.TestCase):
    def test_classifications(self):
        for error, code in [("Host key verification failed.", "SSH_TRUST_REQUIRED"),
                            ("Permission denied (publickey)", "SSH_AUTH_FAILED"),
                            ("Connection timed out", "SSH_UNREACHABLE"),
                            ("WARNING: UNPROTECTED PRIVATE KEY FILE! Permission denied (publickey)", "SSH_KEY_PERMISSIONS")]:
            self.assertEqual(classify_ssh(error), code)

    def test_read_only_probe_and_no_user_name_in_report(self):
        with tempfile.TemporaryDirectory() as d:
            key = Path(d) / "private-key"; key.write_text("not read by doctor")
            p = replace(Profile(), identity=str(key), user="private-user")
            commands = []
            def run(command, **kwargs):
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, "os=Darwin\narch=arm64\nconsole=private-user\ndeskflow=present\nvnc=listening\nfirewall=Firewall is disabled. (State = 0)\n", "")
            with patch("winmaclink.doctor.shutil.which", return_value="ssh"):
                result = diagnose(p, runner=run, probe=lambda *a: True)
            self.assertEqual(len(commands), 1)
            self.assertNotIn("private-user", json.dumps(result))
            self.assertTrue(any(x["code"] == "MAC_FIREWALL" and x["status"] == "warning" for x in result["checks"]))

    def test_auth_failure_does_not_leak_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            key = Path(d) / "key"; key.touch()
            p = replace(Profile(), identity=str(key))
            with patch("winmaclink.doctor.shutil.which", return_value="ssh"):
                report = diagnose(p, runner=lambda *a, **k: subprocess.CompletedProcess([], 255, "", "Permission denied private-host private-user"), probe=lambda *a: True)
            self.assertNotIn("private-host", json.dumps(report))
            self.assertTrue(any(c["code"] == "SSH_AUTH_FAILED" for c in report["checks"]))


class ExecutionTests(unittest.TestCase):
    def test_mac_install_preview_never_executes(self):
        runner = unittest.mock.Mock()
        result = install_mac(Profile(), runner=runner)
        self.assertEqual(result["state"], "preview")
        runner.assert_not_called()
        for checksum in HASHES.values():
            self.assertRegex(checksum, r"^[a-f0-9]{64}$")

    def test_mac_existing_app_is_not_overwritten(self):
        runner = unittest.mock.Mock(return_value=subprocess.CompletedProcess([], 0, "ALREADY_PRESENT\n", ""))
        self.assertEqual(install_mac(Profile(), True, runner)["state"], "already-present")
        script = install_script()
        self.assertLess(script.index("ALREADY_PRESENT"), script.index("curl -fL"))
        self.assertNotIn("xattr", script)
        self.assertNotIn("spctl --master-disable", script)

    def test_mac_install_failure_is_never_success(self):
        for result in [subprocess.CompletedProcess([], 1, "", "failure"), subprocess.CompletedProcess([], 0, "", "")]:
            with self.assertRaises(ValueError):
                install_mac(Profile(), True, unittest.mock.Mock(return_value=result))

    def test_installer_allowlist(self):
        self.assertIn("Deskflow.Deskflow", install_command("deskflow"))
        with self.assertRaises(ValueError):
            install_command("attacker.package")

    def test_tunnel_is_local_and_pinned(self):
        args = tunnel_arguments(Profile())
        self.assertIn("127.0.0.1:15900:127.0.0.1:5900", args)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertNotIn("-g", args)

    def test_occupied_port_does_not_start_or_kill_process(self):
        with tempfile.TemporaryDirectory() as d, socket.socket() as sock:
            viewer = Path(d) / "viewer.exe"; viewer.touch()
            sock.bind(("127.0.0.1", 0)); sock.listen()
            p = replace(Profile(), viewer=str(viewer), local_port=sock.getsockname()[1])
            with patch("winmaclink.runtime.subprocess.Popen") as start:
                with self.assertRaisesRegex(ValueError, "occupied"):
                    connect(p)
                start.assert_not_called()

    def test_cli_init_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d, patch("sys.stdout"):
            target = Path(d) / "profile.json"
            self.assertEqual(main(["init", str(target)]), 0)
            before = target.read_bytes()
            self.assertEqual(main(["init", str(target)]), 2)
            self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
