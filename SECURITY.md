# Security boundaries

- Run diagnostics before making changes. Never assume successful TCP means trusted identity or working GUI input.
- SSH must have a pre-verified host key. Unknown or changed keys are not automatically accepted or removed.
- No password, passphrase or private-key material is accepted by the profile schema. Identity paths are local references only.
- Private profiles, reviewed plans, backups, journals and logs belong in `.local/`. Plans and journals can contain local paths or the previous contents of a file and are NOT public reports.
- `doctor` redacts endpoint names, account names, addresses and key/viewer paths from its structured report; raw SSH stderr is not included. Do not assume arbitrary terminal screenshots or installer output are redacted.
- Shell commands on the Mac are fixed probes/install scripts; user profile values are not interpolated into remote shell commands. Local commands use argument arrays, not a shell.
- Only predefined generated filenames can be applied or restored. Revalidate the plan before apply and check file hashes before rollback. User symlinks and junctions are rejected; only macOS's exact `/var`, `/tmp`, `/etc` system aliases are permitted.
- These checks are not a hardened sandbox against another process under the same OS account racing filesystem changes or tampering with the local journal. Run without administrator privileges unless a separate operation explicitly needs them.
- The SSH tunnel binds only `127.0.0.1`. The Mac's separate VNC listener may still be reachable from Wi-Fi, Ethernet or IPv6. This tool DOES NOT currently enforce a Mac firewall policy.
- Deskflow templates preserve TLS and fingerprint checks. OS security protections are never disabled. The macOS installer verifies official pinned package hashes and code signatures, but requires subsequent user permission and functional testing.
- Desktop input sharing is different from pre-login screen control. FileVault preboot unlock cannot be solved by a logged-in user agent.
- On Apple Silicon/macOS 26+, Apple documents conditional SSH FileVault unlock. This tool only detects and guides; it has not implemented or verified that unlock workflow. It never disables FileVault automatically.
- Control endpoints resolve only to allowed local IPv4 ranges. Direct mode also checks the configured Mac Ethernet IP and binds SSH to the configured Windows Ethernet IP. This does not replace an OS routing/VPN audit. Software acquisition from official sources is allowed only on explicit installer execution; no session relay or cloud account is used.
- Updating pinned packages needs review of upstream releases, supported OS versions, hashes and regression results. Offline setup, fresh-install and recovery paths are not assumed verified by existing-install tests.

No vulnerability-free or internet-exposure guarantee is made. No telemetry, cloud account, VNC relay or GitHub upload is implemented. Package installation and model-independent upstream downloads use their respective internet services.
