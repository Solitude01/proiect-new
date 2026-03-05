# Check specific issues
#Requires -RunAsAdministrator

Write-Host "========== Issue Check ==========" -ForegroundColor Cyan
Write-Host ""

# 1. List all tasks with "坤" or "Kun" in name
Write-Host "[1] Searching for KunYun tasks..." -ForegroundColor Yellow
$allTasks = Get-ScheduledTask | Where-Object { $_.TaskName -match "坤|Kun" }
if ($allTasks) {
    foreach ($t in $allTasks) {
        Write-Host "  Found: $($t.TaskName) [$($t.State)]" -ForegroundColor Green
    }
} else {
    Write-Host "  No tasks found with '坤' or 'Kun'" -ForegroundColor Red
}

# 2. Check config.json encoding
Write-Host ""
Write-Host "[2] Checking config.json..." -ForegroundColor Yellow

$configPaths = @(
    "D:\dist\config.json",
    "C:\坤云平台定时处理\config.json"
)

foreach ($path in $configPaths) {
    if (Test-Path $path) {
        Write-Host "  Found: $path" -ForegroundColor Green

        # Read raw bytes to check BOM
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $hasBOM = ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)

        if ($hasBOM) {
            Write-Host "  Has UTF-8 BOM: YES" -ForegroundColor Yellow
        } else {
            Write-Host "  Has UTF-8 BOM: NO" -ForegroundColor Gray
        }

        # Try to parse JSON
        try {
            # Use utf-8-sig to handle BOM
            $content = Get-Content $path -Raw -Encoding UTF8
            $json = $content | ConvertFrom-Json
            Write-Host "  JSON Parse: OK" -ForegroundColor Green
        }
        catch {
            Write-Host "  JSON Parse: FAILED - $_" -ForegroundColor Red

            # Show first 100 chars
            $preview = [System.IO.File]::ReadAllText($path).Substring(0, [Math]::Min(100, (Get-Item $path).Length))
            Write-Host "  First 100 chars:" -ForegroundColor Gray
            Write-Host "  $preview" -ForegroundColor Gray
        }
    }
}

# 3. Check if we can create a test task
Write-Host ""
Write-Host "[3] Testing task creation..." -ForegroundColor Yellow

$testName = "KY_Test_$(Get-Date -Format 'HHmmss')"
$testScript = "C:\ky_test_$(Get-Date -Format 'HHmmss').ps1"
"Write-Host 'Test'" | Out-File $testScript

# Try creating with schtasks
$cmd = "powershell.exe -ExecutionPolicy Bypass -Command `"& '$testScript'`""
$result = schtasks.exe /create /tn $testName /tr "$cmd" /sc once /st "23:59" /ru SYSTEM /f 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Test task created: OK" -ForegroundColor Green
    schtasks.exe /delete /tn $testName /f 2>&1 | Out-Null
} else {
    Write-Host "  Test task creation: FAILED" -ForegroundColor Red
    Write-Host "  Error: $result" -ForegroundColor Red
}

Remove-Item $testScript -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========== Done ==========" -ForegroundColor Cyan
