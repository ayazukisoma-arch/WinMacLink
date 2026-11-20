# Implementation ledger

| ID | Requirement / source | Status | Evidence | Risk/dependency | Next action |
|---|---|---|---|---|---|
| R01 | configurable profiles, SPEC R01 | verified | profile.py; Windows/Mac tests | direct/LAN execution differs | extend route-level overlap diagnosis |
| R02 | read-only diagnosis, SPEC R02 | partial | doctor.py; real Windows→Mac report; mocked failure states | OS privacy permissions not directly introspected | add version/permission-specific probes |
| R03 | explicit plan/apply, SPEC R03 | verified | transaction tests and actual CLI plan/apply/rollback in private directory | applies staged files only, not OS changes | managed integration with existing configs |
| R04 | restore managed changes, confirmed user requirement | partial | staged-file rollback verified by conflict/traversal/symlink tests | OS/network/startup rollback still missing | implement managed OS snapshots before any automatic OS changes |
| R05 | automatic deployment, SPEC R05 | partial | installer commands; Mac existing-install skip observed; pinned hashes from official sums | Windows fresh install and Mac fresh install not exercised by this product | isolated fresh-machine test; download failure guidance |
| R06 | pinned SSH/VNC, SPEC R06 | partial | owned-tunnel tests; source; existing VNC outside product works | new connect command's full GUI path not yet observed | own-port VNC session validation |
| R07 | permissions/exposure limits, SPEC R07 | partial | permissions template; SECURITY.md; actual firewall warning | no automated firewall change or permission grant | actionable permission UI guidance |
| R08 | privacy/publication, SPEC R08 and 2026-11-20 user decision | partial | sanitized doctor tests; .gitignore; WinMacLink terms in LICENSE.md; Deskflow license and exception separate in the release ZIP | GitHub not published; final corresponding-source and distribution audit pending | verify contents and notices before publishing |
| R09 | repeated QA, SPEC R09 | verified | DEFECTS.md; VALIDATION.md | bounded revision/matrix, no bug-free promise | extend matrix with each slice |
| R10 | UI + full automation, SPEC R10 | partial | gui.py; Windows visual inspection of diagnosis and ordered guide | integration/startup/reboot workflow incomplete | implement config conflict and OS-state snapshots |
| R11 | FileVault-aware guidance, user contract | partial | live detection and versioned simulation tests; actual settings opener | conditional SSH unlock not exercised | isolated FileVault-enabled OS test |
| R12 | isolated fresh-state verification, user contract | partial | test_clean_room.py covers missing keys, trust, apps, VNC, FileVault | fixtures are not a fresh OS/VM | disposable Mac VM/new-account plan |
| R13 | local-only sessions, user clarification | partial | public-IP and mixed DNS refusal; direct source binding; pinned tunnel | OS/VPN routing and listener exposure still need audit | verify direct-only control path and firewall integration |

No percentage is used as a substitute for evidence. `verified` applies only to the behavior stated in each row.

2026-11-16 Windows status check: `python -m unittest discover -s tests` ran 67 tests, with 66 passed and the Windows symlink-privilege case skipped. This run did not exercise network settings, initial authentication, or reboot recovery on hardware.

| ID | Requirement | Status | Evidence | Remaining |
|---|---|---|---|---|
| R16 | Fixed IPv4 setup without cached peers | implemented-unverified | Setup GUI with paired values, Windows admin apply and DHCP restore, Mac manual TCP/IP instructions; existing tests and PowerShell parser | Real adapter apply/restore, Mac configuration, reboot and reconnect |

| R14 | no routine profile-file selection, 2026-11-03 user correction | partial | automatic remembered connection and existing project migration; in-app registration; Windows visual check; test_onboarding.py | first-time ARP discovery does not authenticate or fully bootstrap a fresh Mac | authenticated local discovery and missing-key setup guidance |

Blind first-use result: see BLIND_FIRST_RUN.md. With saved profiles and the user SSH directory hidden, a wired device candidate was found but no Mac was authenticated and initial connection did not complete. Empty cache produced zero candidates. Full onboarding is therefore still partial.

2026-11-19: The target is a first-time installer for both Deskflow across two physical monitors and VNC in a Windows window. New GUI registrations now create a dedicated Windows SSH key and save its path. An isolated real connection attempt reached strict host-key verification before user authentication. The remaining first-time steps are host-key verification and public-key registration, then provisioning and exercising each display mode. The working network and macOS sharing setup were retained for this run.

User decision for R10 and R14: guide the user through manual macOS actions. Present the proposed action before running automation from a button. The initial SSH window now guides Remote Login and host fingerprint verification, opens OpenSSH on confirmation, exposes the public key for manual registration, and offers a post-registration connection check. End-to-end first-time authentication and setup for both display modes remain unverified.

Windows setup automation (R05, R10, R16): the GUI checks for Deskflow and TigerVNC, requests consent for missing packages, runs WinGet, then verifies executable presence. Fixed IPv4 setup preselects the sole connected Ethernet adapter when available and shows apply or restore confirmation. The Tk consent checks used a simulated missing package, and the generated PowerShell parsed successfully. Fresh installation, real adapter changes, automatic SSH public-key registration, and Deskflow configuration and startup still need implementation or hardware verification.

Revised R10 and R14 per the user's setup flow: the main window now starts with connection setup and exposes separate Deskflow and VNC mode buttons. A fresh connection starts with the Mac Remote Login instructions and opens the Windows Ethernet apply dialog as part of setup. After native SSH trust and authentication, the setup automatically adds the dedicated public key and runs the strict SSH diagnosis. VNC mode can install its missing Windows viewer and open the tunnel session. Deskflow mode can install the applications and stage settings. Applying and launching the Deskflow configuration on both hosts, automatically applying the Mac Ethernet settings, and verifying actual fresh setup and reboot recovery remain open. Tk entry points and SSH command construction were checked on Windows. No real fresh SSH registration, installation, or reboot was exercised in this cycle.

Deskflow bundle and pairing (R05, R10): the local distribution contains the pinned Deskflow 1.27.0 builds for both Windows and Mac architectures, the upstream source archive, and license. The two-monitor action installs from the bundle and writes paired configuration into WinMacLink-owned directories on both hosts. Certificate pairing, loading those configurations in running Deskflow processes, and a complete test on the reset Mac remain open.

Deskflow activation (R10): the two-monitor action now generates per-host TLS certificates, exchanges their fingerprints over pinned SSH, launches the Windows core and a Mac GUI-session job, and checks the Windows server log for the configured client. Windows OpenSSL or Git for Windows' native OpenSSL is required. The bundled Windows core opened a loopback listener using generated settings; Windows certificate generation and Mac's installed 1.27.0, GUI session, and launch plist parsing were verified. Actual paired TLS connection and pointer/keyboard input are pending live approval and verification.

2026-11-20 live Deskflow reinstall: after active application copies and WinMacLink pair settings were moved aside on both hosts, the user ran the two-monitor setup and reported success. Verified the bundled Windows core and new configuration, the new Mac installation at version 1.27.0 and running GUI-session job, and the configured client connection in the Windows server log. The hosts retained their operating-system permission history, and Windows already had Python and Git for Windows. A fresh OS/user with neither prerequisite and first-time OS permission prompts was not tested.

2026-11-20 live VNC reinstall: verified Windows had no TigerVNC executable or installer registration and Mac Screen Sharing was off before the test. After setup, verified a TigerVNC window titled for the Mac and an established connection to the WinMacLink loopback tunnel port. The Mac retained its existing VNC password configuration. Pointer and keyboard delivery were not independently observed.

| R15 | tailored field-lookup guide, 2026-11-03 user request | verified for stated paths | lookup.py/test_lookup.py; actual Mac Finder Home and Ethernet summary inspected; guide popup visually checked | older OS screen names use guidance, not actual-machine observation; first authentication remains separate | complete key/bootstrap workflow |
