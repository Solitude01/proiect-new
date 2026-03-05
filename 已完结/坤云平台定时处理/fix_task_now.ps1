# KunYun Task Quick Fix Script
# Fixes -File + Chinese path issue
# PowerShell 4.0 Compatible
#Requires -RunAsAdministrator

$TaskNameCN = "坤云平台定时清理"
$TaskNameEN = "KunYun Platform Cleanup"
$ScriptPath = "C:\坤云平台定时处理\cleanup.ps1"
$ConfigPath = "C:\坤云平台定时处理\config.json"
$LauncherPath = "C:\ky_cleanup_launcher.ps1"

Write-Host "========== KunYun Task Quick Fix ==========" -ForegroundColor Cyan
Write-Host ""

# Step 1: Find existing task
Write-Host "[INFO] Looking for existing task..." -ForegroundColor Cyan
$task = Get-ScheduledTask -TaskName $TaskNameCN -ErrorAction SilentlyContinue
if (-not $task) {
    $task = Get-ScheduledTask -TaskName $TaskNameEN -ErrorAction SilentlyContinue
}

if (-not $task) {
    Write-Host "[WARNING] Task not found, will create new" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Found task: $($task.TaskName)" -ForegroundColor Green
}

# Step 2: Check current configuration
if ($task) {
    Write-Host ""
    Write-Host "[INFO] Checking current configuration..." -ForegroundColor Cyan
    $xml = [xml](Export-ScheduledTask -TaskName $task.TaskName)
    $currentArgs = $xml.Task.Actions.Exec.Arguments
    Write-Host "Current Arguments: $currentArgs" -ForegroundColor Gray

    if ($currentArgs -match "-File" -and $currentArgs -match "坤云") {
        Write-Host "[WARNING] Detected -File mode with Chinese path!" -ForegroundColor Red
        Write-Host "[WARNING] This causes SILENT FAILURE!" -ForegroundColor Red
    }
}

# Step 3: Create launcher script
Write-Host ""
Write-Host "[INFO] Creating launcher script..." -ForegroundColor Cyan
$launcherContent = @"
# KunYun Cleanup Launcher (Auto-generated)
`$ErrorActionPreference = "Stop"
try {
    if (Test-Path '$ScriptPath') {
        & '$ScriptPath' -ConfigPath '$ConfigPath'
    } else {
        # Fallback to D:\dist
        & 'D:\dist\cleanup.ps1' -ConfigPath 'D:\dist\config.json'
    }
} catch {
    `$msg = "ERROR: `$_"
    Add-Content -Path "C:\ky_cleanup_error.log" -Value "`$(Get-Date) - `$msg"
}
"@
Set-Content -Path $LauncherPath -Value $launcherContent -Encoding UTF8 -Force
Write-Host "[OK] Launcher created: $LauncherPath" -ForegroundColor Green

# Step 4: Delete old task
Write-Host ""
Write-Host "[INFO] Deleting old task..." -ForegroundColor Cyan
if ($task) {
    schtasks.exe /delete /tn $task.TaskName /f 2>&1 | Out-Null
    Write-Host "[OK] Old task deleted" -ForegroundColor Green
}

# Step 5: Create new task using schtasks (most compatible method)
Write-Host ""
Write-Host "[INFO] Creating fixed task..." -ForegroundColor Cyan

# Build command using -Command instead of -File
# Use simple path without spaces to avoid quote issues
$command = 'powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "& ''C:\ky_cleanup_launcher.ps1''"'

# Create task with schtasks
$result = schtasks.exe /create /tn $TaskNameCN /tr $command /sc minute /mo 5 /ru SYSTEM /rl HIGHEST /f 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to create task: $result" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Fixed task created!" -ForegroundColor Green

# Step 6: Add boot trigger
Write-Host ""
Write-Host "[INFO] Adding boot trigger..." -ForegroundColor Cyan
$bootResult = schtasks.exe /create /tn "${TaskNameCN}_Boot" /tr $command /sc onstart /ru SYSTEM /rl HIGHEST /f 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Boot trigger added" -ForegroundColor Green
}

# Step 7: Verify
Write-Host ""
Write-Host "[INFO] Verifying..." -ForegroundColor Cyan
$newTask = Get-ScheduledTask -TaskName $TaskNameCN -ErrorAction SilentlyContinue
if ($newTask) {
    $info = $newTask | Get-ScheduledTaskInfo
    Write-Host "[OK] Task verified" -ForegroundColor Green
    Write-Host "  Next Run: $($info.NextRunTime)" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] Verification failed" -ForegroundColor Red
}

Write-Host ""
Write-Host "========== Fix Complete ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Key Changes:" -ForegroundColor Yellow
Write-Host "  1. Changed -File to -Command mode" -ForegroundColor White
Write-Host "  2. Using launcher script at ASCII path" -ForegroundColor White
Write-Host "  3. Running as SYSTEM with highest privileges" -ForegroundColor White
Write-Host ""
Write-Host "Wait 5-10 minutes, then check:" -ForegroundColor Yellow
Write-Host "  Get-Content C:\ky_cleanup_error.log (for errors)" -ForegroundColor White
Write-Host "  Or check your log directory" -ForegroundColor White
Write-Host ""
Write-Host "Check task status:" -ForegroundColor Yellow
Write-Host '  Get-ScheduledTask -TaskName "坤云平台定时清理" | Get-ScheduledTaskInfo' -ForegroundColor White
Write-Host ""
