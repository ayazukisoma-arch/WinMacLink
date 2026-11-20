# Validation record — development cycle 1

## Environments

- Windows / Python 3.12: profile validation, templates, transactions, diagnosis simulations, installer boundaries and local-port ownership.
- macOS / Python 3.12: same test suite; normal OS temporary aliases and symlink rejection tested on actual macOS.
- Read-only integration: Windows→Mac over existing pinned SSH key, queried macOS/architecture, GUI console state, installed Deskflow, VNC localhost listener and firewall state. No existing network or sharing settings changed.
- CLI journey: init-no-overwrite (test), plan→apply→rollback in an ignored private directory, installation preview, real Mac existing-install skip.

## Loop findings

1. Initial sandbox temp-path permissions prevented tests. Reran with workspace-owned temp directory; not counted as a product defect.
2. Fixed platform-specific text encoding: PowerShell BOM, POSIX shell no BOM (B001).
3. Fixed a slash-spelling assertion in the test (B002).
4. Real macOS run exposed rejection of `/var` system alias. Fixed exact system-alias handling while retaining symlink rejection (B003).
5. Added installer and combined SSH error regression paths.

Final clean pass: Windows ran 27 tests, 26 passed and 1 symlink-privilege skip; macOS ran 27 tests, all passed. Windows compileall and CLI help passed. The skipped Windows symlink path was exercised successfully on macOS. No new reproducible defects were found in this stated matrix; untested areas below remain unverified.

## Not verified

Fresh Windows/macOS installation from zero; administrator/permission UI; Intel Mac; real VNC authentication and screen rendering using this new CLI; reboot recovery via this product; firewall/IPv6/NAT enforcement; crash/power-loss durability; hostile same-user filesystem races.

The existing manually configured integration is not evidence that this tool can automatically reproduce the whole setup on a fresh machine.

## Cycle 2 — user-confirmed product scope

- Windows: 41 tests, 40 passed and 1 symlink-privilege skip. macOS: 41 tests, all passed.
- Added fresh-state simulations: no key, no SSH response, unknown host key, missing Deskflow/VNC, login screen, FileVault enabled on supported/older/unknown OS, transition and unavailable states.
- Added local control boundaries: reject public IPv4 and mixed public/private DNS results; direct mode binds to the Windows Ethernet IP and requires the configured Mac Ethernet destination. This does not replace route/VPN/physical-link auditing.
- Actual read-only probe with direct source binding returned macOS version, FileVault Off, installed Deskflow, VNC waiting and firewall warning. Existing configuration was unchanged.
- Native Windows GUI visually inspected: main window and ordered setup popup rendered. Diagnosis button completed an actual read-only query. OS settings grant, full OS rollback, app install, VNC login and reboot were not executed via the GUI.
- GUI remains a guided prototype; staged-file rollback is not full OS rollback. Fresh-state fixtures are not a newly installed macOS VM. These are explicit release blockers/remaining work, not clean-test claims.

No newly reproducible defects remained in this stated automated matrix at the end of this cycle.

## Cycle 3 — 2026-11-03

- Windows: 49 tests, 48 passed and one OS symlink-privilege skip. macOS: 49 tests, all passed. Compile checks passed.
- GUI launched without a profile argument; found the existing connection, saved it to the per-user application directory and displayed the registered Mac without a file dialog. Native Windows visual inspection confirmed normal buttons no longer require profile selection.
- State tests cover empty install, invalid stored profile, explicit overrides, repeated saves, Japanese paths and temporary-file cleanup. Candidate tests exclude public/multicast/broadcast entries and do not mark candidates as trusted Macs.
- Discovery is cached-neighbour discovery only. No full-network scan, cloud discovery, silent host-key registration, account enumeration or automatic OS change is performed. A fresh Mac absent from the cache and initial credentials/permissions remain a separate bootstrap task.

## Cycle 4 — 2026-11-03

Windows: 54 tests (53 pass, one OS-privilege skip); macOS: 54/54 passed. Real discovery on Windows excluded Wi-Fi entries and returned one registered Mac, verified through the existing SSH host key and macOS response. No network settings were changed. New-device trust remains a user-led bootstrap step.

## Guided lookup cycle — 2026-11-03

- Real Mac inspected read-only: macOS version, short account name vs full name, wired service/interface and IPv4. Finder Home window showed the short account name. Network→Ethernet summary showed the IP-address field. Sharing page navigation was inspected; no toggles/values were changed.
- Lookup metadata maps the profile IP to the actual interface and network-service name, rather than assuming Ethernet/en0 or using Wi-Fi. Private observed values are saved only in ignored local test data, not public templates.
- GUI Find Mac opened the side-by-side lookup guide and two-field entry. Actual OS version appeared; initial/unknown contexts do not receive a machine-specific username or claimed OS verification.
- Windows ran 67 tests: 66 passed and one OS symlink-privilege skip. Compile checks passed. macOS run is checked separately below.
- Blind first-use checks still show no saved profile/SSH home, zero SSH executions, one untrusted live wired peer, and zero peers for empty cache. Manual guided input is now offered, but initial key setup/authentication is still incomplete.

Primary UI references: https://support.apple.com/ja-jp/guide/mac-help/mh14129/27/mac/27 ; https://support.apple.com/ja-jp/guide/mac-help/mchlp1143/27/mac/27 ; https://support.apple.com/ja-jp/guide/mac-help/mh35928/27/mac/27 .


macOS final run: 67/67 tests passed. No new reproducible defects were found in the stated automated matrix.
