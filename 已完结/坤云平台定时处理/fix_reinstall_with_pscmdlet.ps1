# ====================================================================
# 修复方案 A: 使用 PowerShell Cmdlet 重新创建任务
# 功能：绕过 XML，使用 New-ScheduledTask 等 cmdlet 创建任务
# ====================================================================

#Requires -RunAsAdministrator

param(
    [string]$TaskName = "坤云平台定时清理",
    [string]$ScriptPath = "$PSScriptRoot\cleanup.ps1",
    [string]$ConfigPath = "$PSScriptRoot\config.json",
    [int]$IntervalMinutes = 5
)

function Write-Info { param([string]$Message); Write-Host "[信息] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message); Write-Host "[成功] $Message" -ForegroundColor Green }
function Write-Error { param([string]$Message); Write-Host "[错误] $Message" -ForegroundColor Red }
function Write-Warning { param([string]$Message); Write-Host "[警告] $Message" -ForegroundColor Yellow }

Write-Host "========== 修复方案 A: PowerShell Cmdlet 方式 ==========" -ForegroundColor Cyan

# 检查文件
if (-not (Test-Path $ScriptPath)) {
    Write-Error "清理脚本不存在: $ScriptPath"
    exit 1
}
if (-not (Test-Path $ConfigPath)) {
    Write-Error "配置文件不存在: $ConfigPath"
    exit 1
}

# 步骤1: 卸载旧任务
Write-Host "`n[1] 卸载旧任务..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Success "旧任务已卸载"
} else {
    Write-Info "任务不存在，无需卸载"
}

# 步骤2: 创建启动脚本
Write-Host "`n[2] 创建启动脚本..." -ForegroundColor Yellow
$launcherPath = "C:\ky_cleanup_launcher.ps1"
$launcherContent = @"
# 坤云平台定时清理启动脚本
try {
    & '$ScriptPath' -ConfigPath '$ConfigPath'
} catch {
    `$err = "执行失败: `$_"
    Add-Content -Path "C:\ky_cleanup_error.log" -Value "`$(Get-Date) - `$err"
}
"@
Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8 -Force
Write-Success "启动脚本已创建: $launcherPath"

# 步骤3: 使用 PowerShell Cmdlet 创建任务
Write-Host "`n[3] 创建计划任务..." -ForegroundColor Yellow

try {
    # 创建操作
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$launcherPath`"" `
        -WorkingDirectory "$PSScriptRoot"

    # 创建触发器 - 开机启动（延迟2分钟）
    $bootTrigger = New-ScheduledTaskTrigger -AtStartup
    $bootTrigger.Delay = "PT2M"

    # 创建触发器 - 定时重复
    # 计算开始时间（今天零点）
    $startTime = (Get-Date -Format "yyyy-MM-dd") + "T00:00:00"
    $timeTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date -Format "yyyy-MM-dd") `
        -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)

    # 创建主体（SYSTEM账户）
    $principal = New-ScheduledTaskPrincipal `
        -UserId "SYSTEM" `
        -RunLevel Highest

    # 创建设置
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    # 注册任务
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger @($bootTrigger, $timeTrigger) `
        -Principal $principal `
        -Settings $settings `
        -Force

    Write-Success "任务创建成功！"
}
catch {
    Write-Error "创建任务失败: $_"
    exit 1
}

# 步骤4: 验证
Write-Host "`n[4] 验证任务..." -ForegroundColor Yellow
$newTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($newTask) {
    $info = $newTask | Get-ScheduledTaskInfo
    Write-Success "任务已注册"
    Write-Host "  状态: $($newTask.State)" -ForegroundColor Gray
    Write-Host "  下次运行: $($info.NextRunTime)" -ForegroundColor Gray

    # 显示触发器
    Write-Host "`n  触发器:" -ForegroundColor Gray
    $newTask.Triggers | ForEach-Object {
        Write-Host "    - $($_.CimClass.CimClassName)" -ForegroundColor Gray
        if ($_.Repetition) {
            Write-Host "      间隔: $($_.Repetition.Interval)" -ForegroundColor Gray
        }
    }
} else {
    Write-Error "任务验证失败"
    exit 1
}

Write-Host "`n========== 完成 ==========" -ForegroundColor Cyan
Write-Host "`n任务已使用 PowerShell Cmdlet 方式重新创建。" -ForegroundColor Green
Write-Host "等待 $($IntervalMinutes) 分钟后检查是否自动执行。" -ForegroundColor Yellow
Write-Host "`n检查命令:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor White
Write-Host "  Get-Content C:\ky_cleanup_error.log" -ForegroundColor White
