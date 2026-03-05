# Manual Check Script
# Run this to identify the exact issues

Write-Host "========== Manual Check ==========" -ForegroundColor Cyan

# Check 1: List ALL scheduled tasks
Write-Host "`n[1] All Scheduled Tasks:" -ForegroundColor Yellow
Get-ScheduledTask | Select-Object -ExpandProperty TaskName | Sort-Object

# Check 2: Look for KunYun task specifically
Write-Host "`n[2] Searching for KunYun task..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName "坤云平台定时清理" -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "Found by Chinese name!" -ForegroundColor Green
} else {
    Write-Host "Not found by Chinese name" -ForegroundColor Red
    # Try to find similar
    $similar = Get-ScheduledTask | Where-Object { $_.TaskName -like "*坤*" -or $_.TaskName -like "*Kun*" -or $_.TaskName -like "*KY*" }
    if ($similar) {
        Write-Host "Similar tasks found:" -ForegroundColor Yellow
        $similar | ForEach-Object { Write-Host "  - $($_.TaskName)" }
    }
}

# Check 3: Config file
Write-Host "`n[3] Config file check:" -ForegroundColor Yellow
if (Test-Path "D:\dist\config.json") {
    Write-Host "File exists at D:\dist\config.json" -ForegroundColor Green

    # Check first few bytes for BOM
    $bytes = [System.IO.File]::ReadAllBytes("D:\dist\config.json")
    Write-Host "First 3 bytes: $($bytes[0]) $($bytes[1]) $($bytes[2])" -ForegroundColor Gray
    Write-Host "(239 187 191 = UTF-8 BOM)"

    # Try different encodings
    Write-Host "`nTrying different encodings..." -ForegroundColor Gray
    try {
        $utf8 = Get-Content "D:\dist\config.json" -Raw -Encoding UTF8
        $json = $utf8 | ConvertFrom-Json
        Write-Host "UTF8 encoding: OK" -ForegroundColor Green
    } catch {
        Write-Host "UTF8 encoding: FAILED - $_" -ForegroundColor Red
    }

    try {
        $utf8sig = Get-Content "D:\dist\config.json" -Raw -Encoding UTF8BOM
        $json = $utf8sig | ConvertFrom-Json
        Write-Host "UTF8-BOM encoding: OK" -ForegroundColor Green
    } catch {
        Write-Host "UTF8-BOM encoding: FAILED - $_" -ForegroundColor Red
    }

    # Show first line
    Write-Host "`nFirst line of file:" -ForegroundColor Gray
    (Get-Content "D:\dist\config.json" -TotalCount 1) | ForEach-Object { Write-Host "  $_" }
}

Write-Host "`n========== End ==========" -ForegroundColor Cyan
