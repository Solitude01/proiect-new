# ====================================================================
# 步骤2: 创建最简单的测试任务
# 功能：创建绝对简单的测试任务，排除所有复杂因素
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 步骤2: 创建简单测试任务 ==========" -ForegroundColor Cyan

# 配置
$TestDir = "C:\ky_test_simple"
$TestLog = "$TestDir\test.log"
$TestScript = "$TestDir\test.ps1"
$TaskName = "KY_Simple_Test"

# 步骤1: 创建测试目录和脚本
Write-Host "`n[1] 创建测试文件..." -ForegroundColor Yellow
mkdir $TestDir -Force | Out-Null

# 简单的测试脚本 - 只写日志
$scriptContent = @'
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "C:\ky_test_simple\test.log" -Value "AUTO-EXECUTED at: $timestamp"
'@
Set-Content -Path $TestScript -Value $scriptContent -Encoding UTF8
Write-Host "  [成功] 测试脚本: $TestScript" -ForegroundColor Green

# 步骤2: 删除旧测试任务
Write-Host "`n[2] 清理旧测试任务..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  [成功] 旧任务已清理" -ForegroundColor Green

# 步骤3: 创建简单测试任务（使用 PowerShell cmdlet，不使用 XML）
Write-Host "`n[3] 创建测试任务（2分钟间隔）..." -ForegroundColor Yellow

try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -File `"$TestScript`""

    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-1) `
        -RepetitionInterval (New-TimeSpan -Minutes 2) `
        -RepetitionDuration (New-TimeSpan -Days 1)

    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable

    Register-ScheduledTask -TaskName $TaskName `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    Write-Host "  [成功] 测试任务已创建: $TaskName" -ForegroundColor Green
}
catch {
    Write-Host "  [错误] 创建失败: $_" -ForegroundColor Red
    exit 1
}

# 显示任务信息
Write-Host "`n[4] 测试任务信息:" -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName $TaskName
$info = $task | Get-ScheduledTaskInfo
Write-Host "  任务名称: $($info.TaskName)"
Write-Host "  状态: $($task.State)"
Write-Host "  下次运行: $($info.NextRunTime)"
Write-Host "  已启用: $($task.Settings.Enabled)"

# 指导
Write-Host "`n========== 操作指南 ==========" -ForegroundColor Cyan
Write-Host "`n1. 等待 3-5 分钟（不要手动运行任务）" -ForegroundColor Yellow
Write-Host "2. 检查日志文件是否自动创建:" -ForegroundColor Yellow
Write-Host "   notepad C:\ky_test_simple\test.log" -ForegroundColor White
Write-Host "`n3. 如果看到时间戳 = Task Scheduler 正常工作" -ForegroundColor Green
Write-Host "   如果日志为空/不存在 = 系统级问题" -ForegroundColor Red
Write-Host "`n4. 接下来运行: .\diagnose_step3_check_events.ps1" -ForegroundColor Yellow
