#Requires -RunAsAdministrator

Write-Host "========== 计划任务诊断报告 ==========" -ForegroundColor Cyan

# 1. 服务状态
Write-Host "`n[1] Task Scheduler 服务状态:" -ForegroundColor Yellow
$service = Get-Service -Name "Schedule" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "  状态: $($service.Status)" -ForegroundColor $(if($service.Status -eq "Running"){"Green"}else{"Red"})
    Write-Host "  启动类型: $($service.StartType)"
} else {
    Write-Host "  错误: 无法获取服务状态" -ForegroundColor Red
}

# 2. 任务存在性
Write-Host "`n[2] 任务存在性检查:" -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName "坤云平台定时清理" -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "  任务存在: 是" -ForegroundColor Green
    Write-Host "  状态: $($task.State)"
    Write-Host "  已启用: $($task.Settings.Enabled)"
} else {
    Write-Host "  任务存在: 否" -ForegroundColor Red
}

# 3. 系统时间
Write-Host "`n[3] 系统时间信息:" -ForegroundColor Yellow
Write-Host "  当前时间: $(Get-Date)"
Write-Host "  时区: $((Get-TimeZone).DisplayName)"

# 4. 下次运行时间
if ($task) {
    Write-Host "`n[4] 任务执行信息:" -ForegroundColor Yellow
    $info = $task | Get-ScheduledTaskInfo
    Write-Host "  上次运行: $($info.LastRunTime)"
    Write-Host "  上次结果: $($info.LastTaskResult)" -ForegroundColor $(if($info.LastTaskResult -eq 0){"Green"}else{"Red"})
    Write-Host "  下次运行: $($info.NextRunTime)"
}

# 5. 触发器详情
if ($task) {
    Write-Host "`n[5] 触发器详情:" -ForegroundColor Yellow
    foreach ($trigger in $task.Triggers) {
        Write-Host "  类型: $($trigger.CimClass.CimClassName)"
        Write-Host "  启用: $($trigger.Enabled)"
        if ($trigger.Repetition) {
            Write-Host "  间隔: $($trigger.Repetition.Interval)"
        }
    }
}

# 6. 文件存在性
Write-Host "`n[6] 关键文件检查:" -ForegroundColor Yellow
$files = @{
    "启动脚本" = "C:\ky_cleanup_launcher.ps1"
    "清理脚本" = "D:\dist\cleanup.ps1"
    "配置文件" = "D:\dist\config.json"
}
foreach ($name in $files.Keys) {
    $exists = Test-Path $files[$name]
    Write-Host "  $name ($($files[$name])): $(if($exists){'存在'}else{'不存在'})" -ForegroundColor $(if($exists){"Green"}else{"Red"})
}

# 7. 最近任务事件
Write-Host "`n[7] 最近 Task Scheduler 事件:" -ForegroundColor Yellow
try {
    $events = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational'; StartTime=(Get-Date).AddHours(-1)} -MaxEvents 10 -ErrorAction SilentlyContinue
    if ($events) {
        $events | Select-Object TimeCreated, Id, @{N='描述';E={
            switch ($_.Id) {
                107 { '任务启动' }
                108 { '启动失败' }
                110 { '触发器触发' }
                102 { '任务完成' }
                103 { '任务停止' }
                119 { '条件不满足' }
                default { "事件 $_" }
            }
        }} | Format-Table -AutoSize
    } else {
        Write-Host "  最近1小时内无事件（可能需要启用任务历史记录）" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  无法读取事件日志: $_" -ForegroundColor Yellow
}

# 8. 导出任务XML用于对比
if ($task) {
    Write-Host "`n[8] 导出任务配置:" -ForegroundColor Yellow
    $xmlPath = "C:\ky_task_export.xml"
    Export-ScheduledTask -TaskName "坤云平台定时清理" | Out-File $xmlPath
    Write-Host "  任务配置已导出到: $xmlPath" -ForegroundColor Green
    Write-Host "  请将此文件与正常服务器的配置对比" -ForegroundColor Cyan
}

Write-Host "`n========== 诊断完成 ==========" -ForegroundColor Cyan
Write-Host "`n如果[7]中没有任何事件，请运行以下命令启用任务历史记录:" -ForegroundColor Yellow
Write-Host "wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true" -ForegroundColor White
