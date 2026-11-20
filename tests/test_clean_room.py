"""Empty-state simulations, not a claim of a clean macOS installation."""
from dataclasses import replace
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from winmaclink.profile import Profile, ssh_arguments
from winmaclink.doctor import diagnose
from winmaclink.guidance import filevault_guidance, open_deskflow_permissions, open_mac_panel, STEPS, format_report
from winmaclink.network import resolve_local


class FileVaultTests(unittest.TestCase):
    def test_modern_apple_silicon_does_not_require_disabling(self):
        code, severity, message = filevault_guidance("FileVault is On.", "arm64", "27.2")
        self.assertEqual(code, "FILEVAULT_SSH_CANDIDATE")
        self.assertIn("自動無効化しない", message)

    def test_old_or_unknown_os_never_claims_remote_unlock(self):
        for arch, version in [("arm64", "25.0"), ("x86_64", "27.0"), ("arm64", "unknown")]:
            self.assertEqual(filevault_guidance("FileVault is On.", arch, version)[0], "FILEVAULT_LOCAL_UNLOCK")

    def test_off_is_not_reboot_success(self):
        code, _, message = filevault_guidance("FileVault is Off.", "arm64", "27.2")
        self.assertEqual(code, "FILEVAULT_OFF")
        self.assertIn("保証されない", message)

    def test_unavailable_and_transition_states(self):
        self.assertEqual(filevault_guidance("operation not permitted", "arm64", "27.2")[0], "FILEVAULT_UNKNOWN")
        self.assertEqual(filevault_guidance("FileVault is On. Decryption in progress", "arm64", "27.2")[0], "FILEVAULT_TRANSITION")


class LocalBoundaryTests(unittest.TestCase):
    def test_public_endpoint_never_reaches_ssh(self):
        with self.assertRaisesRegex(ValueError, "LOCAL_ENDPOINT_REQUIRED"):
            ssh_arguments(replace(Profile(), host="8.8.8.8"))

    def test_mixed_public_private_dns_is_refused(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in ("192.168.250.2", "8.8.8.8")]
        with patch("winmaclink.network.socket.getaddrinfo", return_value=records):
            with self.assertRaises(ValueError):
                resolve_local("test.local")

    def test_local_ranges(self):
        for address in ("192.168.250.2", "169.254.10.20", "100.64.1.2", "10.1.2.3"):
            self.assertEqual(resolve_local(address), address)

    def test_direct_control_binds_to_windows_ethernet(self):
        args = ssh_arguments(Profile())
        self.assertEqual(args[args.index("-b")+1], Profile().windows_ip)
        with self.assertRaisesRegex(ValueError, "DIRECT_ENDPOINT_MISMATCH"):
            ssh_arguments(replace(Profile(), host="100.64.1.2"))

    def test_settings_allowlist_and_no_grant_command(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        result = open_mac_panel(Profile(), "filevault", runner)
        self.assertEqual(result["state"], "open-requested")
        command = runner.call_args.args[0]
        self.assertTrue(command[-1].startswith("open 'x-apple.systempreferences:"))
        self.assertNotIn("sudo", command[-1])
        with self.assertRaises(ValueError):
            open_mac_panel(Profile(), "filevault; disable", runner)

    def test_deskflow_permissions_reveals_the_selected_original(self):
        for target, path in (("app", "/Applications/Deskflow.app"),
                             ("core", "/Applications/Deskflow.app/Contents/MacOS/deskflow-core")):
            with self.subTest(target=target):
                runner = Mock(return_value=subprocess.CompletedProcess([], 0))
                open_deskflow_permissions(Profile(), target, runner=runner)
                command = runner.call_args.args[0][-1]
                self.assertIn("Privacy_Accessibility", command)
                self.assertTrue(command.endswith(f"/usr/bin/open -R {path}"))
        with self.assertRaises(ValueError):
            open_deskflow_permissions(Profile(), "other", runner=runner)
        runner.assert_called_once()

    def test_deskflow_permissions_reports_why_finder_could_not_open(self):
        for code, hint in ((21, "ロックを解除"), (22, "実行ファイルが見つかりません")):
            with self.subTest(code=code):
                runner = Mock(return_value=subprocess.CompletedProcess([], code))
                with self.assertRaisesRegex(ValueError, hint):
                    open_deskflow_permissions(Profile(), runner=runner)


class FreshMachineSimulationTests(unittest.TestCase):
    def test_missing_key_and_disconnected_mac_do_not_bootstrap_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            p = replace(Profile(), identity=str(Path(directory)/"absent-key"))
            runner = Mock()
            result = diagnose(p, runner=runner, probe=lambda *a: False)
            codes = {item["code"] for item in result["checks"] if item["status"] == "error"}
            self.assertIn("SSH_IDENTITY", codes)
            self.assertIn("SSH_PORT", codes)
            runner.assert_not_called()

    def test_trust_required_is_not_auto_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory)/"key"; key.touch()
            runner = Mock(return_value=subprocess.CompletedProcess([], 255, "", "Host key verification failed."))
            with patch("winmaclink.doctor.shutil.which", return_value="ssh"):
                report = diagnose(replace(Profile(), identity=str(key)), runner=runner, probe=lambda *a: True)
            self.assertTrue(any(c["code"] == "SSH_TRUST_REQUIRED" for c in report["checks"]))
            self.assertEqual(runner.call_count, 1)
            self.assertIn("StrictHostKeyChecking=yes", runner.call_args.args[0])

    def test_fresh_mac_missing_sharing_and_apps_with_filevault_on(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory)/"key"; key.touch()
            response = "os=Darwin\narch=arm64\nversion=27.2\nconsole=loginwindow\nfilevault=FileVault is On.\ndeskflow=missing\nvnc=not-listening\nfirewall=Firewall is enabled.\n"
            runner = Mock(return_value=subprocess.CompletedProcess([], 0, response, ""))
            with patch("winmaclink.doctor.shutil.which", return_value="ssh"):
                report = diagnose(replace(Profile(), identity=str(key)), runner=runner, probe=lambda *a: True)
            facts = {c["code"]: c for c in report["checks"]}
            self.assertEqual(facts["MAC_VNC"]["status"], "warning")
            self.assertEqual(facts["MAC_DESKFLOW"]["detail"], "missing")
            self.assertIn("FILEVAULT_SSH_CANDIDATE", facts)
            self.assertNotIn("REBOOT_VERIFIED", facts)

    def test_bootstrap_limit_is_visible_in_guide(self):
        self.assertIn("まだSSHが通らないMac", STEPS[1][1])
        self.assertIn("Mac側の初回操作", STEPS[0][1])

    def test_human_report_keeps_unverified_limits_visible(self):
        result = format_report({"checks": [{"code": "MAC_VNC", "status": "ok", "detail": "listening"}]})
        self.assertIn("待受中", result)
        self.assertIn("再起動後の復帰", result)
        self.assertIn("別途確認", result)


if __name__ == "__main__":
    unittest.main()
