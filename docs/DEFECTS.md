# Defect ledger

| ID | Severity/state | Reproduction / expected vs actual | Root cause / correction | Evidence / related risk |
|---|---|---|---|---|
| B001 | medium / verified | Render mac-fixed-ip.sh, apply, inspect bytes. Shell script should begin `#!`; initially began UTF-8 BOM. | Shared output encoder used PowerShell-compatible BOM for every platform; select encoding by suffix. | Regression: shell has no BOM, PowerShell has BOM; cross-platform startup. |
| B002 | low / verified (test issue) | Unicode path assertion compared slash spelling on Windows; equivalent path became backslashes. | Compare Path values, not serialized slash spelling. | Unicode paths and subprocess argument boundaries. |
| E001 | environment | Initial tests could create sandbox temporary directories but not write files inside them. | Test runner uses explicit workspace-local temporary directory. | No product behavior inferred from this environment failure. |
| B003 | medium / verified | macOS transaction tests failed under the system temporary directory. | macOS `/var` is an OS symlink to `/private/var`; blanket ancestor rejection rejected this normal path. Permit only exact macOS system aliases, continue rejecting user symlinks/junctions. | Run the same matrix on the real Mac, including malicious target symlink rejection. |

This ledger covers this revision and test matrix only. No claim of a vulnerability-free product.

## Cycle 2

| ID | Severity/state | Reproduction / root cause | Fix and evidence |
|---|---|---|---|
| B004 | medium / verified | Broad substring matching could interpret a FileVault error containing `on` as enabled. | Parse the actual `FileVault is On/Off` status; unknown, transition, old OS and modern Apple Silicon cases are tested. |
| B005 | low / verified | Launch diagnosis from pythonw GUI; the SSH child briefly opened a console. | Hide only noninteractive child consoles on Windows; actual GUI diagnosis rerun. Native viewer authentication remains visible. |
| C001 | specification correction | Earlier explanation treated FileVault as a blanket obstacle to remote restart access. | Current Apple documentation describes conditional SSH unlock on Apple Silicon/macOS 26+. Detection guides to verification and never automatically disables encryption. Actual unlock remains unverified. |

The local-only endpoint/source binding and guided GUI are requirement extensions, not evidence that a full fresh OS installation has been reproduced.

## Cycle 3 — first-use automation

| ID | Severity/state | Reproduction / root cause | Fix and evidence |
|---|---|---|---|
| B006 | medium / verified for saved connections | Open GUI without `--profile`: user had to select a developer JSON file. CLI configuration was exposed as the normal user workflow. | Auto-load remembered connections and existing project settings; registration form and untrusted LAN-cache candidates; no JSON selection button in normal GUI. Windows screen verified. Fresh-Mac auto-bootstrap remains partial. |

Regression matrix: 49 tests on Windows (48 pass, 1 OS symlink-privilege skip) and 49/49 on macOS. Added repeated save, Unicode storage, invalid saved config, explicit override, candidate filtering and link-local first-contact cases. Link-local profiles do not generate a misleading fixed-IP setter.

## Cycle 4 — candidate clarity

| ID | Severity/state | Reproduction / root cause | Fix and evidence |
|---|---|---|---|
| B007 | medium / verified for registered direct connection | The direct-connection chooser mixed Ethernet Mac with Wi-Fi router and cached peers, requiring users to interpret bare IPs. | Filter physical wired adapters, prioritize registered endpoint, verify it using pinned SSH and `uname -s`, skip chooser when only the registered Mac is verified. Real Windows run returned exactly one verified Mac. |
| B008 | low / verified | ARP deduplication used destination IP only; same address on different interfaces was lost. | Deduplicate by source-interface IP and peer IP. Regression added. |

54 tests on Windows (53 pass, one symlink-privilege skip), 54/54 on macOS. No registered trust is granted from MAC/IP/ARP alone. First-time OS discovery remains limited.

## Blind first-run audit

| ID | Severity/state | Reproduction / root cause | Next correction |
|---|---|---|---|
| B009 | medium / verified for field entry | Hide all saved connection state and SSH home, open first-use GUI. Registration asked for a key path and host-key alias a novice does not have. | Replaced with two-field lookup guide. Key preparation/bootstrap itself remains an explicit feature gap; no silent trust. |
| G001 | feature gap / observed | Full discovery with an empty ARP response returns no candidates. The implementation is cache-based, not a new-peer discovery mechanism. | Add bounded local discovery; remain explicit about identification vs authentication. |

## Guided lookup cycle

67 tests: Windows 66 passed plus one OS symlink-privilege skip; macOS result recorded in VALIDATION.md. Added actual-interface/service matching, renamed services, short-name vs full-name guidance, unknown/manual OS selection, two-field registration, preserved existing identity, missing/ambiguous Windows-network refusal and manual-Mac-IP registration without an ARP peer. Initial connection is still not fully automated.
