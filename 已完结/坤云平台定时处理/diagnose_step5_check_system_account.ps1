# ====================================================================
# 步骤5: 检查 SYSTEM 账户执行能力
# 功能：验证 SYSTEM 账户能否正常执行 PowerShell
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 步骤5: SYSTEM 账户执行能力检查 ==========" -ForegroundColor Cyan

# 检查执行策略
Write-Host "`n[1] 当前执行策略:" -ForegroundColor Yellow
$execPolicy = Get-ExecutionPolicy
Write-Host "  当前策略: $execPolicy" -ForegroundColor Gray

if ($execPolicy -eq 'Restricted') {
    Write-Host "  [警告] 执行策略为 Restricted，可能阻止脚本执行" -ForegroundColor Red
}
else {
    Write-Host "  [成功] 执行策略允许脚本执行" -ForegroundColor Green
}

# 检查系统范围的执行策略
Write-Host "`n[2] 系统范围执行策略:" -ForegroundColor Yellow
$scopePolicies = Get-ExecutionPolicy -List
$scopePolicies | ForEach-Object {
    Write-Host "  $($_.Scope): $($_.ExecutionPolicy)" -ForegroundColor Gray
}

# 创建 SYSTEM 账户测试任务
Write-Host "`n[3] 创建 SYSTEM 账户测试任务..." -ForegroundColor Yellow

$testOutput = "C:\ky_system_test_output.txt"
$testTaskName = "KY_System_Test"

# 清理旧测试
Unregister-ScheduledTask -TaskName $testTaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item $testOutput -Force -ErrorAction SilentlyContinue

# 创建简单的 SYSTEM 测试命令
$testCommand = "whoami > C:\ky_system_test_output.txt; Get-Date >> C:\ky_system_test_output.txt; Get-ExecutionPolicy >> C:\ky_system_test_output.txt"

try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -Command `"$testCommand`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet

    Register-ScheduledTask -TaskName $testTaskName `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    Write-Host "  [成功] SYSTEM 测试任务已创建" -ForegroundColor Green
    Write-Host "  [信息] 任务将在1分钟后自动执行" -ForegroundColor Cyan

    # 立即运行一次
    Start-ScheduledTask -TaskName $testTaskName
    Write-Host "  [信息] 已手动触发任务，等待执行..." -ForegroundColor Cyan

    # 等待几秒后检查结果
    Start-Sleep -Seconds 5

    if (Test-Path $testOutput) {
        Write-Host "`n[4] SYSTEM 账户测试结果:" -ForegroundColor Yellow
        $content = Get-Content $testOutput
        $content | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

        if ($content -match "nt authority\\system") {
            Write-Host "`n  [成功] SYSTEM 账户能正常执行 PowerShell!" -ForegroundColor Green
        }
        else {
            Write-Host "`n  [错误] SYSTEM 账户执行结果异常" -ForegroundColor Red
        }
    }
    else {
        Write-Host "`n  [错误] 测试输出文件未创建，SYSTEM 账户可能无法执行 PowerShell" -ForegroundColor Red
    }
}
catch {
    Write-Host "  [错误] 创建测试任务失败: $_" -ForegroundColor Red
}

# 检查防病毒软件（常见位置）
Write-Host "`n[5] 检查可能影响任务的软件:" -ForegroundColor Yellow

# 常见防病毒软件进程
$avProcesses = @(
    "MsMpEng",           # Windows Defender
    "avp",               # Kaspersky
    "avast",             # Avast
    "mcshield",          # McAfee
    "ccsvchst",          # Symantec
    "egui",              # ESET
    "bdagent",           # BitDefender
    "360Safe",           # 360安全卫士
    "360Tray",           # 360托盘
    "QQPCRTP"            # 电脑管家
)

$foundAV = $false
foreach ($proc in $avProcesses) {
    $process = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "  发现: $($process.Name) - 可能影响脚本执行" -ForegroundColor Yellow
        $foundAV = $true
    }
}

if (-not $foundAV) {
    Write-Host "  未发现明显安全软件进程" -ForegroundColor Gray
}

# 检查组策略限制
Write-Host "`n[6] 检查组策略限制:" -ForegroundColor Yellow
$gpoResult = gpresult /r /scope:computer 2>&1 | Select-String -Pattern "脚本|Script|限制|Restrict" -ErrorAction SilentlyContinue
if ($gpoResult) {
    Write-Host "  发现可能的组策略限制:" -ForegroundColor Yellow
    $gpoResult | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
}
else {
    Write-Host "  未发现明显的组策略限制" -ForegroundColor Gray
}

# 清理测试任务
Write-Host "`n[7] 清理测试任务..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $testTaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item $testOutput -Force -ErrorAction SilentlyContinue

Write-Host "`n========== 结论 ==========" -ForegroundColor Cyan
Write-Host "`n如果上述测试都通过，说明 SYSTEM 账户权限正常。" -ForegroundColor Green
Write-Host "问题可能出在任务配置本身。" -ForegroundColor Yellow
Write-Host "`n接下来运行修复脚本:" -ForegroundColor Yellow
Write-Host "  .\fix_reinstall_with_pscmdlet.ps1  # 使用 PowerShell cmdlet 方式" -ForegroundColor White
Write-Host "  或" -ForegroundColor Gray
Write-Host "  .\fix_reinstall_with_schtasks.ps1  # 使用 schtasks 方式" -ForegroundColor White
