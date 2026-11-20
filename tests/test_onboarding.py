from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import Mock

from winmaclink.profile import Profile
from winmaclink.onboarding import find_profile, remember_profile, parse_neighbours, direct_candidates, verify_registered, candidate_label
from winmaclink.setup import render


class RememberedConnectionTests(unittest.TestCase):
    def test_second_launch_needs_no_file_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory)/"日本語 設定"
            p = replace(Profile(), user="testuser")
            remember_profile(p, storage=storage)
            found, path, errors = find_profile(storage=storage, project=Path(directory)/"empty-project")
            self.assertEqual(found, p)
            self.assertEqual(path, (storage/"connection.json").absolute())
            self.assertFalse(errors)

    def test_explicit_profile_beats_remembered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remember_profile(Profile(), storage=root/"saved")
            chosen = replace(Profile(), user="otheruser")
            explicit = remember_profile(chosen, storage=root/"chosen")
            self.assertEqual(find_profile(explicit, storage=root/"saved")[0], chosen)

    def test_existing_project_connection_is_migratable_without_json_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root/"project"; (project/".local").mkdir(parents=True)
            import json
            from dataclasses import asdict
            (project/".local"/"profile.json").write_text(json.dumps(asdict(Profile())))
            self.assertEqual(find_profile(storage=root/"new-store", project=project)[0], Profile())

    def test_invalid_saved_profile_is_not_silently_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"connection.json").write_text('{"password":"do-not-copy"}')
            found, _, errors = find_profile(storage=root, project=root/"empty")
            self.assertIsNone(found)
            self.assertTrue(errors)
            self.assertNotIn("do-not-copy", "".join(errors))

    def test_repeated_save_and_no_stale_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remember_profile(Profile(), storage=root)
            remember_profile(replace(Profile(), user="newuser"), storage=root)
            self.assertEqual(find_profile(storage=root)[0].user, "newuser")
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_link_local_first_contact_is_supported_without_static_ip_script(self):
        p = replace(Profile(), host="169.254.20.2", windows_ip="169.254.20.1", mac_ip="169.254.20.2", prefix=16)
        self.assertNotIn("mac-fixed-ip.sh", render(p))
        self.assertNotIn("windows-fixed-ip.ps1", render(p))


class CandidateTests(unittest.TestCase):
    def test_wifi_candidates_are_excluded_in_direct_mode(self):
        neighbours = [{"host":"192.168.250.2", "windows_ip":"192.168.250.1", "identity_verified":False},
                      {"host":"100.80.42.1", "windows_ip":"100.80.42.32", "identity_verified":False}]
        result = direct_candidates(neighbours, ["192.168.250.1"], Profile())
        self.assertEqual([item["host"] for item in result], ["192.168.250.2"])
        self.assertTrue(result[0]["registered"])

    def test_saved_mac_can_be_checked_without_arp_entry(self):
        candidates = direct_candidates([], [], Profile())
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "Darwin\n", ""))
        result = verify_registered(candidates, Profile(), runner)
        self.assertTrue(result[0]["identity_verified"])
        self.assertIn("確認済み", candidate_label(result[0]))
        self.assertIn("StrictHostKeyChecking=yes", runner.call_args.args[0])
        self.assertEqual(runner.call_args.args[0][-1], "uname -s")

    def test_failed_auth_or_wrong_os_never_marks_mac_verified(self):
        for result in [subprocess.CompletedProcess([], 255, "", "Permission denied"), subprocess.CompletedProcess([], 0, "Linux\n", "")]:
            candidates = direct_candidates([], [], Profile())
            checked = verify_registered(candidates, Profile(), Mock(return_value=result))
            self.assertFalse(checked[0]["identity_verified"])

    def test_no_wired_metadata_does_not_show_every_wifi_peer(self):
        self.assertEqual(direct_candidates([{"host":"100.80.42.1", "windows_ip":"100.80.42.32"}], []), [])

    def test_same_ip_on_different_interfaces_is_not_collapsed(self):
        text = "Interface: 192.168.1.1 --- 0xa\n192.168.1.2 02-00-00-00-00-01 dynamic\nInterface: 192.168.1.3 --- 0xb\n192.168.1.2 02-00-00-00-00-02 dynamic"
        self.assertEqual(len(parse_neighbours(text)), 2)

    def test_cached_neighbours_are_candidates_not_trusted_macs(self):
        text = '''インターフェイス: 169.254.20.1 --- 0xa
  169.254.20.2  c8-80-6d-01-02-03  動的
  169.254.255.255 ff-ff-ff-ff-ff-ff 静的
  224.0.0.251 01-00-5e-00-00-fb 静的
Interface: 100.80.42.32 --- 0xb
  8.8.8.8 02-00-00-00-00-01 dynamic
  100.80.42.1 02-00-00-00-00-02 dynamic
'''
        candidates = parse_neighbours(text)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["windows_ip"], "169.254.20.1")
        self.assertFalse(any(c["identity_verified"] for c in candidates))

    def test_missing_interface_and_duplicate_entries(self):
        self.assertEqual(parse_neighbours("192.168.250.2 02-00-00-00-00-01 dynamic"), [])
        text = "Interface: 192.168.250.1 --- 0xa\n192.168.250.2 02-00-00-00-00-01 dynamic\n192.168.250.2 02-00-00-00-00-01 dynamic"
        self.assertEqual(len(parse_neighbours(text)), 1)


if __name__ == "__main__":
    unittest.main()
