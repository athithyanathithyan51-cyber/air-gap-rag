<#
Zero-traffic evidence on the Windows demo laptop (development only; the Ubuntu
deployment uses scripts/capture_traffic.sh + verify_isolation.py).

Run from an ADMIN PowerShell, with Wi-Fi off and the dev server running:

    powershell -ExecutionPolicy Bypass -File scripts\capture-windows.ps1 -Seconds 120

While it runs, use the assistant (log in, ask questions, upload a document).
It records every packet on every network adapter with Windows' built-in Packet
Monitor (pktmon), and separately diffs the OS byte/packet statistics of the
physical adapters (Wi-Fi, Ethernet). Verdict: PASS when the physical adapters
sent and received nothing during the window.

Note: the vEthernet (WSL) adapter is host-only (Docker/WSL <-> Windows) and
carries the app's traffic to the Ollama and Qdrant containers. It shows up in
the pktmon table but cannot reach another machine, so it is not part of the verdict.

Output: data\captures\<UTC timestamp>\{capture.etl, capture.pcapng, pktmon-counters.txt,
adapters-before.csv, adapters-after.csv, verdict.txt, SHA256SUMS.txt}
Open capture.pcapng in Wireshark on another machine to inspect individual packets.
#>
param(
    [int]$Seconds = 120,
    [string]$OutRoot = "data\captures"
)
$ErrorActionPreference = "Stop"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this from an Administrator PowerShell (pktmon needs admin)."; exit 1 }

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root (Join-Path $OutRoot ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")))
New-Item -ItemType Directory -Force $out | Out-Null
$etl = Join-Path $out "capture.etl"

function Stats {
    Get-NetAdapter -Physical | ForEach-Object {
        $s = $_ | Get-NetAdapterStatistics
        [pscustomobject]@{
            Name        = $_.Name
            Status      = $_.Status
            SentBytes   = [int64]$s.SentBytes
            RecvBytes   = [int64]$s.ReceivedBytes
            SentPackets = [int64]($s.SentUnicastPackets + $s.SentMulticastPackets + $s.SentBroadcastPackets)
            RecvPackets = [int64]($s.ReceivedUnicastPackets + $s.ReceivedMulticastPackets + $s.ReceivedBroadcastPackets)
        }
    }
}

Write-Host "`n== Adapters ==" -ForegroundColor Cyan
Get-NetAdapter | Format-Table Name, InterfaceDescription, Status -AutoSize | Out-Host
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0", "::/0" -ErrorAction SilentlyContinue
if ($route) { Write-Warning "A default route exists - the machine is NOT isolated. Turn Wi-Fi off first." }
else { Write-Host "No default route (IPv4 or IPv6)." -ForegroundColor Green }

pktmon stop 2>$null | Out-Null
pktmon filter remove | Out-Null
$before = @(Stats)
$before | Export-Csv -NoTypeInformation (Join-Path $out "adapters-before.csv")
pktmon start --capture --comp nics --pkt-size 0 --file-name $etl | Out-Null
$started = Get-Date

Write-Host "`n== Capturing on all adapters for $Seconds s - use the assistant now ==" -ForegroundColor Cyan
for ($i = $Seconds; $i -gt 0; $i--) {
    Write-Progress -Activity "Packet capture running" -Status "$i s left - ask questions in the assistant" -PercentComplete (100 * ($Seconds - $i) / $Seconds)
    Start-Sleep -Seconds 1
}
Write-Progress -Activity "Packet capture running" -Completed

pktmon counters --zero | Tee-Object -FilePath (Join-Path $out "pktmon-counters.txt") | Out-Null
pktmon stop | Out-Null
$after = @(Stats)
$after | Export-Csv -NoTypeInformation (Join-Path $out "adapters-after.csv")
pktmon etl2pcap $etl --out (Join-Path $out "capture.pcapng") | Out-Null

$rows = foreach ($a in $after) {
    $b = $before | Where-Object Name -eq $a.Name
    if (-not $b) { $b = [pscustomobject]@{ SentBytes = 0; RecvBytes = 0; SentPackets = 0; RecvPackets = 0 } }
    [pscustomobject]@{
        Adapter        = $a.Name
        Status         = $a.Status
        "Sent bytes"   = $a.SentBytes - $b.SentBytes
        "Recv bytes"   = $a.RecvBytes - $b.RecvBytes
        "Sent packets" = $a.SentPackets - $b.SentPackets
        "Recv packets" = $a.RecvPackets - $b.RecvPackets
    }
}
$total = ($rows | ForEach-Object { $_."Sent bytes" + $_."Recv bytes" + $_."Sent packets" + $_."Recv packets" } | Measure-Object -Sum).Sum
$pass = ($total -eq 0) -and (-not $route)

$verdict = @(
    "Window: $($started.ToUniversalTime().ToString('u')) for $Seconds s on $env:COMPUTERNAME"
    "Default route present: $([bool]$route)"
    ($rows | Format-Table -AutoSize | Out-String).TrimEnd()
    "VERDICT: " + $(if ($pass) { "PASS - zero packets on physical network adapters" } else { "FAIL - traffic on a physical adapter or a default route exists" })
) -join "`n"
$verdict | Set-Content -Encoding utf8 (Join-Path $out "verdict.txt")

Write-Host "`n== Packet Monitor counters (all adapters) ==" -ForegroundColor Cyan
Get-Content (Join-Path $out "pktmon-counters.txt") | Out-Host
Write-Host "`n== Physical adapters during the window ==" -ForegroundColor Cyan
Write-Host $verdict -ForegroundColor $(if ($pass) { "Green" } else { "Red" })

Get-ChildItem $out -File | Where-Object Name -ne "SHA256SUMS.txt" | Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "{0}  {1}" -f $_.Hash.ToLower(), (Split-Path -Leaf $_.Path) } |
    Set-Content -Encoding utf8 (Join-Path $out "SHA256SUMS.txt")
Write-Host "`nEvidence saved in $out"
if (-not $pass) { exit 1 }
