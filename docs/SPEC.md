# Authoritative scope, 2026-11-02

User intent: build a general, controllable Windows/Mac connection utility through diagnosis, implementation, verification and repair loops, with eventual GitHub sharing. User decisions below supersede the initial CLI-first interpretation.

## Confirmed product contract

- First release: Windows 11 controls an Apple Silicon Mac; direct Ethernet. Reverse direction is explicitly deferred after the user's final scope choice. Generic LAN helpers may remain, but are not release acceptance evidence.
- Entry: both operating systems have completed initial setup, the user manages OS settings, and direct-LAN connectivity can be checked. The app opens available settings panels and gives ordered popup guidance. If SSH or screen sharing is still disabled, it must explain the first-access bootstrap limit rather than pretend to operate that Mac.
- Finish: SSH, cross-monitor mouse and keyboard, VNC viewing/input, and reconnection after restart. Single-monitor use is a required path; a permanent second monitor is not assumed.
- Existing settings: snapshot, display differences, let the user resolve conflicts, restore this tool's changes, and preserve subsequent user edits. Full OS-level recovery remains a must-have, not satisfied by staged-file rollback alone.
- GUI: diagnosis, guided setup, open Mac screen, recovery diagnosis, restore. OS authentication/permissions remain the user's action.
- Network policy: control sessions must remain local; internet retrieval is allowed only for explicit official software installation (user clarification). No cloud relay, account, telemetry or cloud storage.
- FileVault: detect version and state, explain limitations, open actual settings upon request. Never automatically decrypt. Apple Silicon/macOS 26+ conditional SSH unlock support must be evaluated before suggesting disabling encryption. Successful unlock remains unverified until tested.
- Test isolation: fresh-state simulations first, then new-account or VM tests for OS behavior. No reset, logout or reboot of the working environment without coordinating active work.

## Requirements

- R01 Profiles: no personal-machine constants in source; support configurable hosts/accounts, dedicated key paths, direct/LAN and four screen positions.
- R02 Diagnosis: read-only probes; distinguish endpoint unreachable, trust errors, authentication, key permissions, absent viewer and absent Mac services. Never claim GUI success from a TCP probe.
- R03 Control: preview is default. Plans are inspectable, revalidated, and unable to inject arbitrary commands or file paths. Staged files only; applying OS changes is a separate operation.
- R04 Recovery: staged-file recovery plus future before/after snapshots of managed OS changes; do not roll back over user edits or unrelated files. No implicit uninstall or broad process termination. Full OS rollback is a release requirement still incomplete.
- R05 Deployment: allowlisted official Windows installers and pinned, verified Mac Deskflow package; report errors and do not replace existing Mac apps.
- R06 Connection: own SSH tunnel on localhost with pinned host key; visible failure; keep credentials in native authentication UI; do not use somebody else's listener.
- R07 Permissions/security: OS permissions are separate user steps. Show exposure limits. Never promise pre-login/reboot recovery without observed evidence.
- R08 Privacy/publication: sanitized diagnostic report; no secrets, private profiles, generated logs, binaries or account-specific constants in publishable files. Publishing and licensing remain separate decisions.
- R09 Loop: run Windows and Mac tests, record defects, rerun original reproductions; mark unsupported/unverified paths explicitly.
- R10 Product UI/full automation: native Windows GUI with real diagnosis, ordered settings guide, staged setup review, connection and recovery actions; existing-settings import, startup management, discovery and OS transitions remain audited gaps.

## Current acceptance matrix

Profiles with invalid host/user, invalid subnet, Windows/macOS separators and UTF-8 BOM; four positions; LAN skips fixed-IP scripts; plan no mutation; modified/tampered plan; new/existing files; rollback with user edits; symlink refusal; auth/trust diagnosis; no raw-stderr leak; allowlisted installation; occupied local port; Mac existing-app skip; actual read-only SSH/service probe.

## Decisions

- 2026-11-02: standard-library Python CLI first, no background web service; reversible implementation default for inspectability and repeatable testing.
- 2026-11-02: stage rather than automatically overwrite existing OS/Deskflow settings; current working integration must stay intact.
- 2026-11-02: Windows 11 and Apple Silicon macOS are the actual integration environment. Intel Mac and fresh-machine paths remain unverified.
- 2026-11-02: no automatic cloud service, secret storage, publishing or license selection.
- 2026-11-02 user decisions: Windows-main only for initial release, direct Ethernet, single-monitor workflow, mandatory restoration, user-led OS changes, guided UI. Official installer downloads are explicitly allowed; session data stays local.
- 2026-11-02 evidence correction: Apple's current FileVault documentation supports conditional SSH unlock on Apple Silicon/macOS 26+. Do not encode a blanket disable-FileVault prerequisite.
- 2026-11-03 user correction: normal GUI users must not create/select JSON profiles. Remember the connection automatically, migrate existing local configuration, and provide candidate discovery plus an in-app registration form for missing values. Never equate a neighbour-cache entry with an authenticated Mac.
- 2026-11-03 user direction: clicking Find Mac must show tailored lookup instructions alongside entry fields. Inspect real Mac screens; specify the navigation and exact field. User enters short account name and wired IPv4; Windows metadata and implementation-specific key paths/aliases are app-managed. OS-specific instructions must distinguish authenticated metadata from unverified/manual OS selection.

## Primary references

- https://support.apple.com/en-mide/guide/security-pdf/sec8447f5049/1/web/1 — FileVault and conditional SSH unlock.
- https://support.apple.com/en-gb/guide/mac-help/mh11848/27/mac/27 — Screen Sharing.
- https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/27/mac/27 — Remote Login prerequisites.
- First setup with an empty connection history: offer persistent IPv4 setup for a selected Windows Ethernet adapter after administrator approval, and show the paired IPv4 address and mask for manual configuration on the Mac. Preserve DHCP recovery for changes made by this workflow. After the user enters the Mac account, show the first SSH connection, fingerprint verification and public-key registration commands. Verify the end-to-end path and persistence separately on hardware.
