# KunYun Scheduled Task Diagnostic Script
# PowerShell 4.0 Compatible, ASCII Only
#Requires -RunAsAdministrator

param(
    [switch]$Fix,
    [switch]$CreateTest,
    [int]$TestInterval = 2
)

# Output Functions
function Info($msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Fail($msg)  { Write-Host "[FAIL]  $msg" -ForegroundColor Red }
function Warn($msg)  { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }

# Global Variables
$TaskName = "KunYun Platform Cleanup"
$TaskNameCN = "坤云平台定时清理"
$LauncherPath = "C:\ky_cleanup_launcher.ps1"
$IssuesFound = @()
$CriticalIssues = @()

# Part 1: System Check
function Check-SystemEnvironment {
    Info "=========================================="
    Info "Part 1: System Environment"
    Info "=========================================="

    $psVer = $PSVersionTable.PSVersion
    Info "PowerShell Version: $($psVer.Major).$($psVer.Minor)"
    if ($psVer.Major -lt 3) {
        $CriticalIssues += "PowerShell version too old"
        Fail "PowerShell version too old: $psVer"
    } else {
        Ok "PowerShell version OK"
    }

    $os = Get-WmiObject Win32_OperatingSystem
    Info "OS: $($os.Caption)"

    if ($os.Caption -match "2012 R2") {
        Warn "Windows Server 2012 R2 detected"
        Info "Note: This version has special trigger requirements"
    }

    $service = Get-Service -Name "Schedule" -ErrorAction SilentlyContinue
    if (-not $service) {
        $CriticalIssues += "Task Scheduler service not found"
        Fail "Task Scheduler service not found"
    } elseif ($service.Status -ne "Running") {
        $CriticalIssues += "Task Scheduler service not running"
        Fail "Task Scheduler service not running"
        if ($Fix) {
            Start-Service -Name "Schedule" -ErrorAction SilentlyContinue
        }
    } else {
        Ok "Task Scheduler service running"
    }

    Info "Current Time: $(Get-Date)"

    # PowerShell 4.0 compatible timezone check
    $tz = [System.TimeZone]::CurrentTimeZone.StandardName
    Info "TimeZone: $tz"
}

# Part 2: Task Configuration Check
function Check-TaskConfiguration {
    Info ""
    Info "=========================================="
    Info "Part 2: Task Configuration"
    Info "=========================================="

    # Try Chinese name first
    $task = Get-ScheduledTask -TaskName $TaskNameCN -ErrorAction SilentlyContinue

    if (-not $task) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    }

    if (-not $task) {
        $CriticalIssues += "Task not found"
        Fail "Task not found"
        return $false
    }

    $actualName = $task.TaskName
    Ok "Task found: $actualName"

    Info "Task State: $($task.State)"
    if (-not $task.Settings.Enabled) {
        $IssuesFound += "Task is disabled"
        Fail "Task is disabled"
        if ($Fix) {
            Enable-ScheduledTask -TaskName $actualName | Out-Null
            Ok "Task enabled"
        }
    } else {
        Ok "Task is enabled"
    }

    $info = $task | Get-ScheduledTaskInfo
    Info "Last Run: $($info.LastRunTime)"
    Info "Last Result: $($info.LastTaskResult)"
    Info "Next Run: $($info.NextRunTime)"

    switch ($info.LastTaskResult) {
        0 { Ok "Last run succeeded (0)" }
        267009 { Warn "Last result: 267009 (running)" }
        267011 { Warn "Last result: 267011 (not run yet)" }
        267012 { Fail "Last result: 267012 (failed to start)"; $CriticalIssues += "Task failed to start" }
        default { Fail "Last result: $($info.LastTaskResult) (error)"; $IssuesFound += "Last run error: $($info.LastTaskResult)" }
    }

    Info ""
    Info "Trigger Check:"
    if ($task.Triggers.Count -eq 0) {
        $CriticalIssues += "Task has no triggers"
        Fail "Task has no triggers"
    } else {
        foreach ($trigger in $task.Triggers) {
            Info "  Type: $($trigger.CimClass.CimClassName)"
            Info "  Enabled: $($trigger.Enabled)"

            if (-not $trigger.Enabled) {
                $IssuesFound += "Trigger disabled"
                Fail "Trigger is disabled"
            }

            if ($trigger.Repetition) {
                Info "  Interval: $($trigger.Repetition.Interval)"
            }
        }
    }

    Info ""
    Info "XML Configuration Check:"
    try {
        $xml = [xml](Export-ScheduledTask -TaskName $actualName)

        $principal = $xml.Task.Principals.Principal
        Info "  RunAs: $($principal.UserId)"

        if ($principal.UserId -ne "S-1-5-18" -and $principal.UserId -ne "SYSTEM") {
            $IssuesFound += "Not running as SYSTEM"
            Warn "Task not using SYSTEM account"
        } else {
            Ok "Using SYSTEM account"
        }

        $action = $xml.Task.Actions.Exec
        $arguments = $action.Arguments
        Info "  Command: $($action.Command)"
        Info "  Arguments: $arguments"

        # CRITICAL CHECK: -File with Chinese path
        if ($arguments -match "-File" -and $arguments -match "[\u4e00-\u9fa5]") {
            $CriticalIssues += "CRITICAL: -File mode with Chinese path detected"
            Fail "CRITICAL: Using -File mode with Chinese path!"
            Fail "This causes SILENT FAILURE with SYSTEM account!"
        }

        # Check for unexpanded variables
        if ($arguments -match '\$[a-zA-Z_][a-zA-Z0-9_]*') {
            $CriticalIssues += "Unexpanded variable in Arguments"
            Fail "CRITICAL: Unexpanded variable: $($matches[0])"
        } else {
            Ok "No unexpanded variables"
        }

        Info "  WorkingDir: $($action.WorkingDirectory)"
    }
    catch {
        Fail "Failed to export XML: $_"
    }

    return $true
}

# Part 3: File Check
function Check-Files {
    Info ""
    Info "=========================================="
    Info "Part 3: File Check"
    Info "=========================================="

    $paths = @(
        "D:\dist\cleanup.ps1",
        "C:\坤云平台定时处理\cleanup.ps1",
        "$PSScriptRoot\cleanup.ps1"
    )

    $ScriptPath = $null
    foreach ($path in $paths) {
        if (Test-Path $path) {
            $ScriptPath = $path
            break
        }
    }

    $configPaths = @(
        "D:\dist\config.json",
        "C:\坤云平台定时处理\config.json",
        "$PSScriptRoot\config.json"
    )

    $ConfigPath = $null
    foreach ($path in $configPaths) {
        if (Test-Path $path) {
            $ConfigPath = $path
            break
        }
    }

    if (-not $ScriptPath) {
        $CriticalIssues += "Cleanup script not found"
        Fail "Cleanup script not found"
    } else {
        Ok "Cleanup script: $ScriptPath"
    }

    if (-not $ConfigPath) {
        $CriticalIssues += "Config file not found"
        Fail "Config file not found"
    } else {
        Ok "Config file: $ConfigPath"
        try {
            $null = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            Ok "Config JSON valid"
        }
        catch {
            $IssuesFound += "Config JSON invalid"
            Fail "Config JSON error"
        }
    }

    if (Test-Path $LauncherPath) {
        Ok "Launcher script exists"
        $content = Get-Content $LauncherPath -Raw
        Info "Launcher content:"
        $content -split "`n" | ForEach-Object { Info "  $_" }
    } else {
        Warn "Launcher script not found: $LauncherPath"
    }
}

# Part 4: Event Log Check
function Check-EventLog {
    Info ""
    Info "=========================================="
    Info "Part 4: Event Log Check"
    Info "=========================================="

    Info "Enabling task history..."
    wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true 2>$null
    Ok "Task history enabled"

    Info ""
    Info "Recent events (last 1 hour):"
    $events = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-TaskScheduler/Operational'
        StartTime = (Get-Date).AddHours(-1)
    } -MaxEvents 20 -ErrorAction SilentlyContinue

    if ($events) {
        $taskEvents = $events | Where-Object { $_.Message -match "坤云|KunYun" }

        if ($taskEvents) {
            foreach ($evt in $taskEvents) {
                $desc = switch ($evt.Id) {
                    107 { 'Started' }
                    108 { 'Start Failed' }
                    110 { 'Trigger Fired' }
                    102 { 'Completed' }
                    201 { 'Action Started' }
                    default { "Event $($evt.Id)" }
                }
                Write-Host "  $($evt.TimeCreated.ToString('HH:mm:ss')) - $desc" -ForegroundColor Gray
            }
        } else {
            Warn "No events for target task in last hour"
        }
    } else {
        Warn "No events in last hour"
    }
}

# Part 5: Execution Policy Check
function Check-ExecutionPolicy {
    Info ""
    Info "=========================================="
    Info "Part 5: Execution Policy Check"
    Info "=========================================="

    $policy = Get-ExecutionPolicy
    Info "Current Policy: $policy"

    if ($policy -eq 'Restricted') {
        $CriticalIssues += "Execution policy is Restricted"
        Fail "Execution policy is Restricted"
    } elseif ($policy -eq 'AllSigned') {
        $IssuesFound += "Execution policy is AllSigned"
        Warn "Execution policy is AllSigned"
    } else {
        Ok "Execution policy OK"
    }
}

# Part 6: Create Test Task
function Create-SimpleTestTask {
    Info ""
    Info "=========================================="
    Info "Part 6: Create Test Task"
    Info "=========================================="

    $testDir = "C:\ky_test_simple"
    $testScript = "$testDir\test.ps1"
    $testTaskName = "KY_Test_Task"
    $testLog = "$testDir\test.log"

    Unregister-ScheduledTask -TaskName $testTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $testDir -Force -Recurse -ErrorAction SilentlyContinue

    New-Item -ItemType Directory -Path $testDir -Force | Out-Null

    $scriptContent = "Add-Content -Path '$testLog' -Value `"`$(Get-Date) - AUTO`""
    Set-Content -Path $testScript -Value $scriptContent -Encoding UTF8

    Ok "Test script created"

    # Use schtasks for PowerShell 4.0 compatibility
    $startTime = (Get-Date).AddMinutes(1).ToString("HH:mm")
    schtasks.exe /create /tn $testTaskName /tr "powershell.exe -ExecutionPolicy Bypass -Command `"& '$testScript'`"" /sc once /st $startTime /ru SYSTEM /f 2>&1 | Out-Null

    Ok "Test task created"
    Info "Check log in 2 minutes: Get-Content $testLog"
}

# Part 7: Report
function Show-DiagnosisReport {
    Info ""
    Info "######################################################################"
    Info "#                     DIAGNOSIS REPORT                                #"
    Info "######################################################################"

    Info ""
    Info "Issues Found:"

    if ($CriticalIssues.Count -eq 0 -and $IssuesFound.Count -eq 0) {
        Ok "No issues found"
    } else {
        if ($CriticalIssues.Count -gt 0) {
            Info ""
            Fail "CRITICAL Issues:"
            $CriticalIssues | ForEach-Object { Fail "  - $_" }
        }

        if ($IssuesFound.Count -gt 0) {
            Info ""
            Warn "Warnings:"
            $IssuesFound | ForEach-Object { Warn "  - $_" }
        }
    }

    Info ""
    Info "######################################################################"
    Info "#                     FIX RECOMMENDATIONS                             #"
    Info "######################################################################"

    $hasFileIssue = $false
    foreach ($issue in $CriticalIssues) {
        if ($issue -match "-File|Chinese path") {
            $hasFileIssue = $true
        }
    }

    if ($hasFileIssue) {
        Info ""
        Fail "CORE ISSUE: Using -File mode with Chinese path"
        Info "SYSTEM account + -File + Chinese path = SILENT FAILURE"
        Info ""
        Info "Fix: Run the fix script:"
        Info "  .\fix_task_now.ps1"
    }

    if ($CriticalIssues.Count -gt 0 -or $IssuesFound.Count -gt 0) {
        Info ""
        Info "Or manually fix:"
        Info "  1. Delete current task"
        Info "  2. Run: .\install.ps1 -IntervalMinutes 5"
    }

    Info ""
    Info "Check commands:"
    Info '  Get-ScheduledTask -TaskName "坤云平台定时清理" | Get-ScheduledTaskInfo'
}

# Main
function Main {
    Info ""
    Info "######################################################################"
    Info "#              KunYun Task Diagnostic Tool                            #"
    Info "######################################################################"
    Info ""
    Info "Time: $(Get-Date)"
    Info ""

    Check-SystemEnvironment
    Check-TaskConfiguration
    Check-Files
    Check-EventLog
    Check-ExecutionPolicy

    if ($CreateTest) {
        Create-SimpleTestTask
    }

    Show-DiagnosisReport

    Info ""
    Info "######################################################################"
    Info "Diagnostic Complete"
    Info "######################################################################"

    if ($CriticalIssues.Count -gt 0) { exit 1 } else { exit 0 }
}

Main
