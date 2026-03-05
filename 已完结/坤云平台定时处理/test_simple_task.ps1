#Requires -RunAsAdministrator
# 最简单的测试任务 - 用于验证 Task Scheduler 是否能自动触发

Write-Host "========== Creating Simple Test Task ==========" -ForegroundColor Cyan

# Step 1: Enable Task History
Write-Host "`n[1] Enabling Task History..." -ForegroundColor Yellow
wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true 2>$null
Write-Host "  Task history enabled" -ForegroundColor Green

# Step 2: Create test directory and script
Write-Host "`n[2] Creating test files..." -ForegroundColor Yellow
$testDir = "C:\ky_test_simple"
$testLog = "$testDir\test.log"
$testScript = "$testDir\test.ps1"

mkdir $testDir -Force | Out-Null

# Simple test script that just writes timestamp
$scriptContent = @'
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "C:\ky_test_simple\test.log" -Value "AUTO-EXECUTED at: $timestamp"
'@
Set-Content -Path $testScript -Value $scriptContent -Encoding UTF8
Write-Host "  Test script created: $testScript" -ForegroundColor Green

# Step 3: Remove old test task if exists
Write-Host "`n[3] Cleaning up old test task..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName "KY_Simple_Test" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  Old test task removed (if existed)" -ForegroundColor Green

# Step 4: Create simple test task using PowerShell cmdlets
Write-Host "`n[4] Creating simple test task (2-minute interval)..." -ForegroundColor Yellow

try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$testScript`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-1) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 1)
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Register-ScheduledTask -TaskName "KY_Simple_Test" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "  Test task created successfully!" -ForegroundColor Green
} catch {
    Write-Host "  ERROR creating task: $_" -ForegroundColor Red
    exit 1
}

# Step 5: Show task info
Write-Host "`n[5] Test Task Info:" -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName "KY_Simple_Test"
$info = $task | Get-ScheduledTaskInfo
Write-Host "  TaskName: $($info.TaskName)"
Write-Host "  State: $($task.State)"
Write-Host "  NextRun: $($info.NextRunTime)"
Write-Host "  Enabled: $($task.Settings.Enabled)"

# Step 6: Instructions
Write-Host "`n========== INSTRUCTIONS ==========" -ForegroundColor Cyan
Write-Host "`n1. Wait 2-3 minutes (do NOT manually run the task)" -ForegroundColor Yellow
Write-Host "2. Check if log file was created automatically:" -ForegroundColor Yellow
Write-Host "   notepad C:\ky_test_simple\test.log" -ForegroundColor White
Write-Host "`n3. If you see timestamps in the log = Task Scheduler is working" -ForegroundColor Green
Write-Host "   If no log or empty = System-level issue (check event logs)" -ForegroundColor Red
Write-Host "`n4. Check event logs:" -ForegroundColor Yellow
Write-Host "   Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational'; StartTime=(Get-Date).AddMinutes(-5)}" -ForegroundColor White
Write-Host "`n========== Test Complete ==========" -ForegroundColor Cyan
