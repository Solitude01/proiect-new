# ====================================================================
# 修复方案 B: 使用 schtasks.exe 重新创建任务
# 功能：绕过 PowerShell cmdlet，直接使用 schtasks.exe 创建
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

Write-Host "========== 修复方案 B: schtasks.exe 方式 ==========" -ForegroundColor Cyan

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
$null = schtasks.exe /query /tn $TaskName 2>&1
if ($LASTEXITCODE -eq 0) {
    $null = schtasks.exe /delete /tn $TaskName /f 2>&1
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

# 步骤3: 使用 schtasks.exe 创建任务
Write-Host "`n[3] 使用 schtasks.exe 创建任务..." -ForegroundColor Yellow

# 命令行（注意转义）
$command = "powershell.exe -ExecutionPolicy Bypass -NoProfile -File `"$launcherPath`""

# 创建定时任务（每 N 分钟）
$result = schtasks.exe /create `
    /tn $TaskName `
    /tr "$command" `
    /sc minute `
    /mo $IntervalMinutes `
    /ru SYSTEM `
    /rl HIGHEST `
    /f 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "创建任务失败: $result"
    exit 1
}
Write-Success "定时触发器已创建（每 $IntervalMinutes 分钟）"

# 添加开机触发器
Write-Host "`n[4] 添加开机触发器..." -ForegroundColor Yellow
$result = schtasks.exe /create `
    /tn "${TaskName}_Boot" `
    /tr "$command" `
    /sc onstart `
    /ru SYSTEM `
    /rl HIGHEST `
    /f 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Success "开机触发器已添加"
} else {
    Write-Warning "开机触发器创建失败（可能已有同名任务）: $result"
}

# 步骤5: 验证
Write-Host "`n[5] 验证任务..." -ForegroundColor Yellow
$null = schtasks.exe /query /tn $TaskName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "任务已注册"

    # 显示详细信息
    Write-Host "`n  任务详情:" -ForegroundColor Gray
    $info = schtasks.exe /query /tn $TaskName /v /fo list 2>&1
    $info | Select-String "任务名称|下次运行时间|要运行的任务|开始时间|已启用" | ForEach-Object {
        Write-Host "    $_" -ForegroundColor Gray
    }
} else {
    Write-Error "任务验证失败"
    exit 1
}

Write-Host "`n========== 完成 ==========" -ForegroundColor Cyan
Write-Host "`n任务已使用 schtasks.exe 方式重新创建。" -ForegroundColor Green
Write-Host "等待 $($IntervalMinutes) 分钟后检查是否自动执行。" -ForegroundColor Yellow
Write-Host "`n检查命令:" -ForegroundColor Cyan
Write-Host "  schtasks.exe /query /tn '$TaskName' /v /fo list" -ForegroundColor White
Write-Host "  Get-Content C:\ky_cleanup_error.log" -ForegroundColor White
