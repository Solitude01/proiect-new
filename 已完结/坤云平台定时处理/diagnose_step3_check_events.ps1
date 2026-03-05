# ====================================================================
# 步骤3: 检查事件日志
# 功能：查看 Task Scheduler 事件日志，寻找错误信息
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 步骤3: 检查事件日志 ==========" -ForegroundColor Cyan

# 检查任务历史记录是否启用
Write-Host "`n[1] 检查任务历史记录状态..." -ForegroundColor Yellow
$status = wevtutil gl Microsoft-Windows-TaskScheduler/Operational 2>&1
$enabledLine = $status | Select-String "enabled"
Write-Host "  $enabledLine" -ForegroundColor Gray

if ($enabledLine -match "enabled: false") {
    Write-Host "`n  [警告] 任务历史记录未启用！请先运行步骤1" -ForegroundColor Red
    Write-Host "  .\diagnose_step1_enable_history.ps1" -ForegroundColor Yellow
}

# 查看最近的事件日志
Write-Host "`n[2] 最近1小时的 Task Scheduler 事件:" -ForegroundColor Yellow

try {
    $events = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-TaskScheduler/Operational'
        StartTime = (Get-Date).AddHours(-1)
    } -MaxEvents 20 -ErrorAction SilentlyContinue

    if ($events) {
        $events | Select-Object TimeCreated, Id, LevelDisplayName, @{
            Name='描述'; Expression={
                switch ($_.Id) {
                    107 { '任务启动' }
                    108 { '启动失败' }
                    110 { '触发器触发' }
                    102 { '任务完成' }
                    103 { '任务停止' }
                    119 { '条件不满足' }
                    201 { '操作启动' }
                    202 { '操作完成' }
                    322 { '启动请求被抑制' }
                    default { "事件 $_" }
                }
            }
        } | Format-Table -AutoSize

        # 特别关注错误
        $errors = $events | Where-Object { $_.LevelDisplayName -eq '错误' -or $_.Id -eq 108 -or $_.Id -eq 103 }
        if ($errors) {
            Write-Host "`n  [警告] 发现错误事件:" -ForegroundColor Red
            $errors | ForEach-Object {
                Write-Host "    $($_.TimeCreated) - ID $($_.Id): $($_.Message.Substring(0, [Math]::Min(100, $_.Message.Length)))..." -ForegroundColor Red
            }
        }
    }
    else {
        Write-Host "  [警告] 最近1小时内无事件" -ForegroundColor Yellow
        Write-Host "  说明：任务历史记录可能刚刚启用，或者任务完全没有被触发" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  [错误] 无法读取事件日志: $_" -ForegroundColor Red
}

# 特别关注 KY_Simple_Test 任务的事件
Write-Host "`n[3] 测试任务 KY_Simple_Test 的相关事件:" -ForegroundColor Yellow
$testEvents = $events | Where-Object { $_.Message -like "*KY_Simple_Test*" }
if ($testEvents) {
    $testEvents | Select-Object TimeCreated, Id, @{
        Name='事件'; Expression={
            switch ($_.Id) {
                107 { '任务启动' }
                108 { '启动失败' }
                110 { '触发器触发' }
                201 { '操作启动' }
                default { "事件 $_" }
            }
        }
    } | Format-Table -AutoSize
}
else {
    Write-Host "  未找到 KY_Simple_Test 相关事件" -ForegroundColor Yellow
}

# 查看日志文件
Write-Host "`n[4] 测试日志文件内容:" -ForegroundColor Yellow
$logPath = "C:\ky_test_simple\test.log"
if (Test-Path $logPath) {
    $logs = Get-Content $logPath -ErrorAction SilentlyContinue
    if ($logs) {
        Write-Host "  找到 $($logs.Count) 条执行记录:" -ForegroundColor Green
        $logs | Select-Object -Last 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    }
    else {
        Write-Host "  [警告] 日志文件存在但为空" -ForegroundColor Yellow
    }
}
else {
    Write-Host "  [错误] 日志文件不存在！任务可能从未自动执行" -ForegroundColor Red
}

Write-Host "`n========== 结果分析 ==========" -ForegroundColor Cyan
Write-Host "`n如果:"
Write-Host "  - 有事件110（触发器触发）+ 有日志 = 系统正常工作" -ForegroundColor Green
Write-Host "  - 有事件110 + 无日志 = 任务被触发但执行失败" -ForegroundColor Red
Write-Host "  - 无事件110 = 触发器未工作，检查系统时间/触发器配置" -ForegroundColor Red
Write-Host "  - 有事件108 = 任务启动失败，检查权限/执行策略" -ForegroundColor Red
Write-Host "`n接下来运行: .\diagnose_step4_check_schtasks.ps1" -ForegroundColor Yellow
