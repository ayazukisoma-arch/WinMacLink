from dataclasses import replace
import unittest
from winmaclink.lookup import parse_context, build_lookup_steps, registration_profile
from winmaclink.profile import Profile

PROBE = '''WML:version
27.2
WML:user
sampleuser
WML:display
Sample Person
WML:services
(1) 有線LAN（作業用）
(Hardware Port: Ethernet, Device: en7)
(2) Wi-Fi
(Hardware Port: Wi-Fi, Device: en1)
WML:interfaces
en1: flags=0
    inet 10.1.2.5 netmask 0xffffff00
en7: flags=0
    inet 172.22.37.2 netmask 0xfffffffc
'''


class LookupTests(unittest.TestCase):
    def test_renamed_service_is_matched_by_actual_ip_not_wifi(self):
        context = parse_context(PROBE, "172.22.37.2")
        self.assertEqual(context["service"], "有線LAN（作業用）")
        self.assertEqual(context["interface"], "en7")
        self.assertEqual(context["user"], "sampleuser")
        guide = build_lookup_steps(context)
        self.assertIn("有線LAN（作業用）", guide[1]["path"])
        self.assertEqual(guide[0]["value"], "sampleuser")
        self.assertEqual(guide[1]["value"], "172.22.37.2")

    def test_first_user_is_not_prefilled_from_a_machine_specific_example(self):
        guide = build_lookup_steps(candidate={"host":"169.254.20.2"})
        self.assertIsNone(guide[-1]["value"])
        self.assertIsNone(guide[0]["value"])
        self.assertIn("青と白の顔", guide[0]["path"])
        self.assertIn("以下いずれかの方法でユーザー名を確認できます。", guide[0]["path"])
        self.assertEqual(guide[1]["value"], "169.254.20.2")
        self.assertIn("右側に入っている有線IPが一致", guide[1]["body"])

    def test_setup_address_is_shown_as_previously_configured(self):
        guide = build_lookup_steps(candidate={"host": "192.168.250.2", "from_fixed_ip": True})
        self.assertEqual(guide[1]["title"], "Macに設定した固定IP")
        self.assertEqual(guide[1]["value"], "192.168.250.2")
        self.assertIn("詳細 → TCP/IP", guide[1]["path"])
        self.assertIn("右側に引き継いで", guide[1]["body"])

    def test_full_name_and_apple_account_are_not_the_requested_name(self):
        step = build_lookup_steps()[0]
        body = step["body"]
        self.assertIn("フルネーム", body)
        self.assertIn("Apple Account", body)
        self.assertIn("変更は不要", body)
        self.assertIn("「@」の手前", step["path"])
        self.assertIn("whoami", step["path"])

    def test_invalid_remote_version_or_user_is_rejected(self):
        for output in (PROBE.replace("27.2", "not-a-version"), PROBE.replace("sampleuser", "bad;command")):
            with self.assertRaises(ValueError):
                parse_context(output, "172.22.37.2")

    def test_old_os_uses_old_settings_names(self):
        context = parse_context(PROBE.replace("27.2", "12.7"), "172.22.37.2")
        self.assertIn("システム環境設定", build_lookup_steps(context)[1]["path"])
        self.assertNotIn("一般", build_lookup_steps(context)[2]["path"])

    def test_unregistered_mac_uses_current_settings_labels(self):
        guide = build_lookup_steps()
        self.assertIn("システム設定 → ネットワーク", guide[1]["path"])
        self.assertIn("システム設定 → 一般 → 共有 → リモートログイン", guide[2]["path"])
        self.assertIsNone(guide[-1]["value"])
        self.assertIsNone(guide[0]["value"])


class TwoFieldRegistrationTests(unittest.TestCase):
    def test_initial_form_needs_only_name_and_mac_ip(self):
        candidate = {"host":"172.22.37.2", "windows_ip":"172.22.37.1", "windows_prefix":30}
        profile = registration_profile(None, candidate, "sampleuser", "172.22.37.2")
        self.assertEqual(profile.user, "sampleuser")
        self.assertEqual(profile.windows_ip, "172.22.37.1")
        self.assertEqual(profile.prefix, 30)
        self.assertTrue(profile.host_key_alias.startswith("winmaclink-"))

    def test_existing_identity_and_trust_alias_are_preserved_for_same_mac(self):
        p = Profile()
        result = registration_profile(p, {}, p.user, p.mac_ip)
        self.assertEqual(result.identity, p.identity)
        self.assertEqual(result.host_key_alias, p.host_key_alias)

    def test_invalid_entries_have_field_specific_messages(self):
        candidate={"windows_ip":"172.22.37.1", "windows_prefix":30}
        with self.assertRaisesRegex(ValueError, "短い名前"):
            registration_profile(None, candidate, "Sample Person", "172.22.37.2")
        with self.assertRaisesRegex(ValueError, "数字だけ"):
            registration_profile(None, candidate, "sampleuser", "ssh name@host")

    def test_missing_windows_information_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "まだ検出できません"):
            registration_profile(None, {}, "sampleuser", "172.22.37.2")
        with self.assertRaisesRegex(ValueError, "再検出"):
            registration_profile(None, {"windows_ip":"172.22.37.1"}, "sampleuser", "172.22.37.2")

    def test_link_local_first_contact_uses_link_local_prefix(self):
        p = registration_profile(None, {"windows_ip":"169.254.20.1"}, "sampleuser", "169.254.20.2")
        self.assertEqual(p.prefix, 16)

    def test_manual_mac_ip_can_match_detected_windows_network_without_arp(self):
        candidate = {"windows_networks":[{"ip":"172.22.37.1", "prefix":30}]}
        p = registration_profile(None, candidate, "sampleuser", "172.22.37.2")
        self.assertEqual(p.windows_ip, "172.22.37.1")
        self.assertEqual(p.prefix, 30)

    def test_ambiguous_wired_network_is_not_guessed(self):
        candidate = {"windows_networks":[{"ip":"172.22.37.1", "prefix":24}, {"ip":"172.22.37.3", "prefix":24}]}
        with self.assertRaisesRegex(ValueError, "まだ検出できません"):
            registration_profile(None, candidate, "sampleuser", "172.22.37.2")


if __name__ == '__main__':
    unittest.main()
