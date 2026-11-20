import hashlib
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from winmaclink import deskflow_bundle, deskflow_pair
from winmaclink.mac_install import RELEASE_URL, VERSION
from winmaclink.profile import Profile


class DeskflowDownloadTests(unittest.TestCase):
    def test_windows_acquires_only_once(self):
        folder = f"deskflow-{VERSION}-win-x64-portable"
        name = f"{folder}.zip"
        archive = BytesIO()
        with ZipFile(archive, "w") as zip_file:
            zip_file.writestr(f"{folder}/deskflow-core.exe", b"fixture")
        payload = archive.getvalue()
        with TemporaryDirectory() as directory, \
                patch.object(deskflow_bundle.platform, "machine", return_value="AMD64"), \
                patch.dict(deskflow_bundle.PAYLOADS, {name: hashlib.sha256(payload).hexdigest()}), \
                patch.object(deskflow_bundle, "urlopen", return_value=BytesIO(payload)) as fetch:
            core = deskflow_bundle.install_windows_package(destination=directory)
            self.assertEqual(core.read_bytes(), b"fixture")
            self.assertEqual(deskflow_bundle.install_windows_package(destination=directory), core)
            fetch.assert_called_once_with(f"{RELEASE_URL}/{name}", timeout=30)

    def test_windows_rejects_changed_archive_and_can_retry(self):
        with TemporaryDirectory() as directory, \
                patch.object(deskflow_bundle.platform, "machine", return_value="AMD64"), \
                patch.object(deskflow_bundle, "urlopen", side_effect=[BytesIO(b"wrong"), TimeoutError()]) as fetch:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                deskflow_bundle.install_windows_package(destination=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
            with self.assertRaisesRegex(ValueError, "ネット接続"):
                deskflow_bundle.install_windows_package(destination=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(fetch.call_count, 2)

    def test_mac_download_is_only_needed_when_missing(self):
        for installed in (True, False):
            with self.subTest(installed=installed), TemporaryDirectory() as directory, \
                    patch.object(deskflow_pair, "ssh_arguments", return_value=["ssh", "mac"]), \
                    patch.object(deskflow_pair, "settings_directory", return_value=Path(directory)), \
                    patch.object(deskflow_pair, "install_windows_package", return_value="deskflow-core.exe"), \
                    patch.object(deskflow_pair, "download_payload") as fetch:
                dmg = Path(directory) / "deskflow.dmg"
                dmg.write_bytes(b"verified image")
                fetch.return_value = dmg
                uploads = []

                def ssh(args, **options):
                    command = args[-1]
                    if "uname -s" in command:
                        return CompletedProcess(args, 0, "arm64\n")
                    if command == "test -d /Applications/Deskflow.app":
                        return CompletedProcess(args, 0 if installed else 1)
                    if "stdin" in options:
                        self.assertIn("codesign --verify", command)
                        self.assertIn("shasum -a 256", command)
                        uploads.append(options["stdin"].read())
                        return CompletedProcess(args, 0, b"INSTALLED_REQUIRES_OS_PERMISSIONS\n")
                    if command.endswith("--version"):
                        return CompletedProcess(args, 0, f"deskflow-core v{VERSION}\n")
                    return CompletedProcess(args, 0)

                deskflow_pair.prepare_pair(Profile(), runner=ssh)
                if installed:
                    fetch.assert_not_called()
                    self.assertEqual(uploads, [])
                else:
                    self.assertEqual(fetch.call_args.args[1], f"deskflow-{VERSION}-macos-arm64.dmg")
                    self.assertEqual(uploads, [b"verified image"])


class DeskflowConnectionTests(unittest.TestCase):
    def test_disconnect_during_startup_does_not_report_success(self):
        connection = 'client "mac-mini" has connected'
        disconnection = 'client "mac-mini" has disconnected'
        process = Mock()
        process.poll.return_value = None
        log = Mock()
        log.read_text.side_effect = [connection, f"{connection}\n{disconnection}"]
        with patch.object(deskflow_pair.time, "monotonic", side_effect=[0, 0, 0, 0.1, 0.4, 1.0]), \
                patch.object(deskflow_pair.time, "sleep"):
            self.assertFalse(deskflow_pair._wait_for_client(process, log, "mac-mini", timeout=1))

    def test_persistent_connection_reports_success(self):
        process = Mock()
        process.poll.return_value = None
        log = Mock()
        log.read_text.return_value = 'client "mac-mini" has connected'
        with patch.object(deskflow_pair.time, "monotonic", side_effect=[0, 0, 0, 0.1, 3, 3]), \
                patch.object(deskflow_pair.time, "sleep"):
            self.assertTrue(deskflow_pair._wait_for_client(process, log, "mac-mini"))
