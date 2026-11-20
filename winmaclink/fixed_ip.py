"""Interactive Windows Ethernet setup with persistent DHCP recovery."""
import base64
import ipaddress
import os
import subprocess

from .process import hidden_console


def mac_fixed_ip_steps(profile):
    network = ipaddress.IPv4Network(f"{profile.mac_ip}/{profile.prefix}", strict=False)
    return (
        "Mac本体で「システム設定 → ネットワーク → Ethernet → 詳細 → TCP/IP」を開きます。",
        "「IPv4の設定」メニューで「手動」を選び、下の値を入力します。",
        f"  IPアドレス       {profile.mac_ip}",
        f"  サブネットマスク {network.netmask}",
        "  ルーター         空欄",
        "「OK」で保存します。",
        "WindowsのWinMacLinkに戻り、「Windows側を確認してMac登録へ」を押します。",
    )


def windows_script(profile):
    address = ipaddress.IPv4Address(profile.windows_ip)
    if profile.topology != "direct" or address.is_link_local:
        raise ValueError("直結LAN用の固定IPv4設定が必要です。")
    network = ipaddress.IPv4Network(f"{address}/{profile.prefix}", strict=False)
    script = r"""
$ErrorActionPreference = 'Stop'
function Show-MacNextSteps {
    Write-Host ''
    Write-Host '次はMac側のEthernetを設定します。' -ForegroundColor Cyan
@MAC_STEPS@
}
try {
    Add-Type -AssemblyName System.Windows.Forms
    $adapters = @(Get-NetAdapter -Physical | Where-Object NdisPhysicalMedium -eq 14)
    if (!$adapters.Count) { throw '物理イーサネットアダプターが見つかりません。' }
    $connected = @($adapters | Where-Object Status -eq 'Up')
    if ($connected.Count -eq 1) {
        $index = $connected[0].ifIndex
    } elseif ($adapters.Count -eq 1) {
        $index = $adapters[0].ifIndex
    } else {
        $adapters | Format-Table ifIndex, Name, InterfaceDescription, Status
        $index = 0
        if (![int]::TryParse((Read-Host '直結ケーブルを挿した行の ifIndex'), [ref]$index)) {
            throw '表にある数字を入力してください。'
        }
    }
    $adapter = $adapters | Where-Object ifIndex -eq $index
    if (!$adapter) { throw '対象は表にある物理イーサネットだけです。' }
    $stateDir = Join-Path $env:LOCALAPPDATA 'WinMacLink'
    $null = New-Item -ItemType Directory -Force $stateDir
    $record = Join-Path $stateDir ("ethernet-" + [guid]$adapter.InterfaceGuid + ".json")
    $ip = '@IP@'
    $prefix = @PREFIX@
    $netsh = Join-Path $env:WINDIR 'System32\netsh.exe'
    $interface = Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4
    $addresses = @(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $persistent = @(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore PersistentStore -ErrorAction SilentlyContinue)
    $matching = @($persistent | Where-Object { $_.IPAddress -eq $ip -and $_.PrefixLength -eq $prefix })
    # A provider-side filter on AddressFamily reports ObjectNotFound for an empty store.
    # Enumerate first so an empty store is allowed and genuine query errors still stop setup.
    $routes = @(
        Get-NetRoute -PolicyStore ActiveStore | Where-Object AddressFamily -eq 2
        Get-NetRoute -PolicyStore PersistentStore | Where-Object AddressFamily -eq 2
    )
    $defaultRoutes = @($routes | Where-Object { $_.InterfaceIndex -eq $index -and $_.DestinationPrefix -eq '0.0.0.0/0' })
    if (Test-Path -LiteralPath $record) {
        $saved = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
        if ($saved.guid -ne [string][guid]$adapter.InterfaceGuid -or $saved.before -ne 'DHCP') {
            throw '復元記録の対象が一致しません。'
        }
        Write-Host "復元記録: $record"
        if ([Windows.Forms.MessageBox]::Show("$($adapter.Name) をDHCPへ戻しますか？", 'WinMacLink', 'YesNo', 'Warning', 'Button2') -ne 'Yes') {
            if ($matching.Count -eq 1 -and !$defaultRoutes.Count) { Show-MacNextSteps }
            return
        }
        if ($interface.Dhcp -ne 'Enabled') {
            if ($persistent.Count -ne 1 -or $persistent[0].IPAddress -ne $saved.address -or
                $persistent[0].PrefixLength -ne $saved.prefix -or $defaultRoutes.Count -or
                @($addresses | Where-Object IPAddress -ne $saved.address).Count) {
                throw '固定後に設定が変わっています。現在の設定を確認して手動で復元してください。'
            }
            & $netsh interface ipv4 set address "name=$index" source=dhcp store=persistent
            if ($LASTEXITCODE) { throw "DHCPの復元に失敗しました（$LASTEXITCODE）。" }
        }
        if ((Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4).Dhcp -ne 'Enabled') {
            throw 'DHCPの復元を確認できません。復元記録を保持しました。'
        }
        Remove-Item -LiteralPath $record
        Write-Host 'DHCPに戻りました。'
        return
    }
    if ($matching.Count -eq 1 -and $persistent.Count -eq 1 -and !$defaultRoutes.Count -and $interface.Dhcp -eq 'Disabled') {
        Write-Host "対象の固定IPは保存済みです。 $ip/$prefix"
        Show-MacNextSteps
        return
    }
    if ($interface.Dhcp -ne 'Enabled' -or @($persistent | Where-Object PrefixOrigin -eq 'Manual').Count -or $defaultRoutes.Count) {
        throw '既存の固定IPまたはゲートウェイがあるため、直結専用アダプターを選ぶか手動設定を使ってください。'
    }
    function Get-PrefixRange([string]$cidr) {
        $parts = $cidr.Split('/')
        $bytes = [Net.IPAddress]::Parse($parts[0]).GetAddressBytes()
        [array]::Reverse($bytes)
        $value = [uint64][BitConverter]::ToUInt32($bytes, 0)
        $size = [uint64][math]::Pow(2, 32 - [int]$parts[1])
        $start = $value - ($value % $size)
        return @($start, ($start + $size - 1))
    }
    $target = Get-PrefixRange "$ip/$prefix"
    foreach ($route in $routes) {
        if ($route.InterfaceIndex -eq $index -or $route.DestinationPrefix -eq '0.0.0.0/0') { continue }
        $range = Get-PrefixRange $route.DestinationPrefix
        if ($target[0] -le $range[1] -and $range[0] -le $target[1]) {
            throw "別のアダプターの経路 $($route.DestinationPrefix) と重複しています。"
        }
    }
    Write-Host "対象 $($adapter.Name) / 変更前 DHCP / 変更後 $ip/$prefix / ゲートウェイなし"
    if ([Windows.Forms.MessageBox]::Show("$($adapter.Name) をMacへの直結専用として $ip/$prefix に設定しますか？ ゲートウェイは指定しません。", 'WinMacLink', 'YesNo', 'Warning', 'Button2') -ne 'Yes') { return }
    $before = @{guid=[string][guid]$adapter.InterfaceGuid; before='DHCP'; address=$ip; prefix=$prefix}
    New-Item -ItemType File -Path $record -Value ($before | ConvertTo-Json) | Out-Null
    try {
        & $netsh interface ipv4 set address "name=$index" source=static "address=$ip" mask=@MASK@ gateway=none store=persistent
        if ($LASTEXITCODE) { throw "固定IPの設定に失敗しました（$LASTEXITCODE）。" }
        $verified = @(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore PersistentStore |
            Where-Object { $_.IPAddress -eq $ip -and $_.PrefixLength -eq $prefix })
        if ($verified.Count -ne 1) { throw '保存済みIPv4の読み戻しが一致しません。' }
    } catch {
        & $netsh interface ipv4 set address "name=$index" source=dhcp store=persistent
        if (!$LASTEXITCODE -and (Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4).Dhcp -eq 'Enabled') {
            Remove-Item -LiteralPath $record
            Write-Host '変更前のDHCPに戻しました。'
        } else {
            Write-Host "復元を確認できません。復元記録: $record"
        }
        throw
    }
    Write-Host "Windowsに固定IPを保存しました。 $ip/$prefix"
    Show-MacNextSteps
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    $null = Read-Host 'Enterで閉じる'
}
"""
    steps = "\n".join("    Write-Host '" + step.replace("'", "''") + "'" for step in mac_fixed_ip_steps(profile))
    return (script.replace("@IP@", str(address)).replace("@PREFIX@", str(profile.prefix))
            .replace("@MASK@", str(network.netmask)).replace("@MAC_STEPS@", steps))


def open_windows_fixed_ip(profile):
    if os.name != "nt":
        raise ValueError("固定IPの適用画面はWindowsで開いてください。")
    encoded = base64.b64encode(windows_script(profile).encode("utf-16-le")).decode("ascii")
    command = (
        "$ErrorActionPreference='Stop'; "
        "Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs "
        f"-ArgumentList '-NoProfile','-EncodedCommand','{encoded}'"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=120, **hidden_console(),
    )
    if result.returncode:
        raise ValueError("管理者画面を開けませんでした。UACの許可を確認してください。")
