# Duck Feeder test tool for Windows.
# Right-click -> "Run with PowerShell", or double-click Test-DuckFeeder.bat
# Checks the Pi is reachable, shows its status, and can trigger a test feed.

$ErrorActionPreference = "Stop"
$configPath = Join-Path $PSScriptRoot "feeder-settings.txt"

if (Test-Path $configPath) {
    $lines = Get-Content $configPath
    $piAddr = $lines[0]; $key = $lines[1]
    Write-Host "Using saved settings: $piAddr  (delete feeder-settings.txt to change)"
} else {
    $piAddr = Read-Host "Pi address (e.g. duckfeeder.local:5000 or 192.168.1.50:5000)"
    $key = Read-Host "Feeder key (shown at the end of install.sh)"
    Set-Content -Path $configPath -Value @($piAddr, $key)
}
$base = "http://$piAddr"

Write-Host "`nChecking $base/status ..."
try {
    $s = Invoke-RestMethod "$base/status" -TimeoutSec 5
    Write-Host ("Reachable. Fed today: {0}/{1}  Queue: {2}  Cooldown: {3}s" -f $s.fed_today, $s.daily_max, $s.waiting, $s.cooldown_seconds) -ForegroundColor Green
} catch {
    Write-Host "Can't reach the Pi. Check it's powered on, on the same Wi-Fi, and try its IP address instead of .local" -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

$tikfinityUrl = "$base/feed?key=$key"
Write-Host "`nTikFinity webhook URL (copied to clipboard):`n  $tikfinityUrl" -ForegroundColor Cyan
Set-Clipboard -Value $tikfinityUrl

$ans = Read-Host "`nSend a test feed now? (y/n)"
if ($ans -eq "y") {
    try {
        $r = Invoke-RestMethod "$base/feed?key=$key&user=windows-test" -TimeoutSec 5
        Write-Host "Pi says: $($r.status)" -ForegroundColor Green
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "Wrong key. Delete feeder-settings.txt and run again." -ForegroundColor Red
        } else { Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red }
    }
}
Read-Host "`nPress Enter to close"
