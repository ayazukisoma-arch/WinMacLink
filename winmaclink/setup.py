"""Generate inspectable scripts; never execute generated network changes here."""
import ipaddress
from .profile import Profile


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def render(p: Profile):
    direction = {"left": ("left", "right"), "right": ("right", "left"),
                 "above": ("up", "down"), "below": ("down", "up")}[p.mac_position]
    layout = f"section: links\n    {p.windows_name}:\n        {direction[0]} = {p.mac_name}\n    {p.mac_name}:\n        {direction[1]} = {p.windows_name}\nend\n"
    bind = f"interface={p.windows_ip}\n" if p.topology == "direct" else ""
    server = f"[core]\ncoreMode=2\nprocessMode=1\ncomputerName={p.windows_name}\n{bind}[security]\ntlsEnabled=true\ncheckPeerFingerprints=true\n[computer_{p.windows_name}]\nname={p.windows_name}\n[computer_{p.mac_name}]\nname={p.mac_name}\n[server]\nexternalConfig=true\nexternalConfigFile=layout.conf\n"
    client = f"[core]\ncoreMode=1\nprocessMode=1\ncomputerName={p.mac_name}\n[client]\nremoteHost={p.windows_ip}\n[security]\ntlsEnabled=true\ncheckPeerFingerprints=true\n[gui]\nstartCoreWithGui=true\n"
    # Templates are intentionally staged only. macOS authentication is performed in its UI.
    mac_notes = """# Mac setup (manual OS permissions)
1. Enable Remote Login for your own account only.
2. Verify the SSH host fingerprint on the Mac and pin it on Windows.
3. Install Deskflow from its official distribution. Grant Accessibility and Local Network.
4. Import/adapt mac-client.ini; merge with existing settings, never overwrite them blindly.
5. Enable Screen Sharing if using VNC. Remote Management and Screen Sharing are alternatives.
6. VNC is not made private by an SSH tunnel. Restrict direct access separately.
7. FileVault preboot unlock is outside this tool's control.
8. Desktop-mode input sharing starts after GUI login, not at the login screen.
9. Do not expect native TigerVNC on Windows to fit a full-HD desktop into a smaller window.
"""
    files = {"layout.conf": layout, "windows-server.ini": server,
             "mac-client.ini": client, "mac-permissions.txt": mac_notes}
    if p.topology == "direct" and not ipaddress.IPv4Address(p.windows_ip).is_link_local:
        mask = ipaddress.IPv4Network(f"{p.windows_ip}/{p.prefix}", strict=False).netmask
        files["mac-fixed-ip.sh"] = f"""#!/bin/sh
# REVIEW before running. Replace the service name if this Mac uses a different one.
# No default gateway or DNS is added. Internet remains on the existing connection.
set -eu
if [ "$#" -ne 1 ]; then echo 'Usage: sh mac-fixed-ip.sh Ethernet-service-name' >&2; exit 2; fi
networksetup -getinfo "$1"
printf 'Apply fixed address? Type APPLY: '
read -r answer
[ "$answer" = APPLY ] || exit 2
sudo networksetup -setmanual "$1" {p.mac_ip} {mask}
networksetup -getinfo "$1"
"""
        files["windows-fixed-ip.ps1"] = f"""# Review and run separately in an administrator PowerShell.
# No network changes are executed by winmaclink apply.
param([Parameter(Mandatory=$true)][int]$InterfaceIndex)
$ErrorActionPreference = 'Stop'
$adapter = Get-NetAdapter -InterfaceIndex $InterfaceIndex
$adapter | Format-List Name, InterfaceDescription, Status
$other = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {{$_.InterfaceIndex -ne $InterfaceIndex}}
$networkBytes = [Net.IPAddress]::Parse('{p.windows_ip}').GetAddressBytes()
$maskBytes = [Net.IPAddress]::Parse('{mask}').GetAddressBytes()
foreach ($item in $other) {{
    $bytes = [Net.IPAddress]::Parse($item.IPAddress).GetAddressBytes()
    $same = $true
    for ($i=0; $i -lt 4; $i++) {{ if (($bytes[$i] -band $maskBytes[$i]) -ne ($networkBytes[$i] -band $maskBytes[$i])) {{ $same=$false }} }}
    if ($same) {{ throw 'Subnet conflicts with another local interface. Choose another profile subnet.' }}
}}
if ((Read-Host 'Type APPLY to change only this adapter') -ne 'APPLY') {{ exit 2 }}
& "$env:WINDIR\\System32\\netsh.exe" interface ipv4 set address "name=$InterfaceIndex" source=static address={p.windows_ip} mask={mask} gateway=none store=persistent
if ($LASTEXITCODE -ne 0) {{ throw "netsh failed: $LASTEXITCODE" }}
"""
    return files
