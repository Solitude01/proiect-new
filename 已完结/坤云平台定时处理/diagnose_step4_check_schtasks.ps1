# ====================================================================
# 步骤4: 使用 schtasks 检查任务详情
# 功能：对比测试任务和正式任务的详细配置
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 步骤4: schtasks 详细检查 ==========" -ForegroundColor Cyan

# 检查简单测试任务
Write-Host "`n[1] 简单测试任务 (KY_Simple_Test) 详情:" -ForegroundColor Yellow
$testTaskInfo = schtasks.exe /query /tn "KY_Simple_Test" /v /fo list 2>&1
if ($LASTEXITCODE -eq 0) {
    # 提取关键信息
    $testTaskInfo | Select-String "任务名称|下次运行时间|触发器|已启用" | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
}
else {
    Write-Host "  [错误] 无法查询测试任务，请先运行步骤2" -ForegroundColor Red
}

# 检查正式任务
Write-Host "`n[2] 正式任务 (坤云平台定时清理) 详情:" -ForegroundColor Yellow
$prodTaskInfo = schtasks.exe /query /tn "坤云平台定时清理" /v /fo list 2>&1
if ($LASTEXITCODE -eq 0) {
    # 提取关键信息
    $prodTaskInfo | Select-String "任务名称|下次运行时间|触发器|已启用|要运行的任务|开始时间" | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }

    # 导出完整配置用于分析
    $exportPath = "C:\ky_prod_task_export.txt"
    $prodTaskInfo | Out-File $exportPath
    Write-Host "`n  [信息] 完整配置已导出到: $exportPath" -ForegroundColor Cyan
}
else {
    Write-Host "  [警告] 正式任务不存在，需要先安装" -ForegroundColor Yellow
}

# 检查当前系统时间
Write-Host "`n[3] 系统时间检查:" -ForegroundColor Yellow
Write-Host "  当前时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "  时区: $((Get-TimeZone).Id)" -ForegroundColor Gray

# 比较两个任务的差异（如果都存在）
Write-Host "`n[4] 任务对比:" -ForegroundColor Yellow
$testTask = Get-ScheduledTask -TaskName "KY_Simple_Test" -ErrorAction SilentlyContinue
$prodTask = Get-ScheduledTask -TaskName "坤云平台定时清理" -ErrorAction SilentlyContinue

if ($testTask -and $prodTask) {
    $testInfo = $testTask | Get-ScheduledTaskInfo
    $prodInfo = $prodTask | Get-ScheduledTaskInfo

    Write-Host "  对比项            测试任务              正式任务" -ForegroundColor Cyan
    Write-Host "  ────────────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host "  状态:             $($testTask.State)               $($prodTask.State)" -ForegroundColor Gray
    Write-Host "  已启用:           $($testTask.Settings.Enabled)            $($prodTask.Settings.Enabled)" -ForegroundColor Gray
    Write-Host "  下次运行:         $(if($testInfo.NextRunTime){$testInfo.NextRunTime.ToString('HH:mm:ss')}else{'N/A'})          $(if($prodInfo.NextRunTime){$prodInfo.NextRunTime.ToString('HH:mm:ss')}else{'N/A'})" -ForegroundColor Gray

    # 触发器对比
    Write-Host "`n  测试任务触发器:" -ForegroundColor Gray
    $testTask.Triggers | ForEach-Object {
        Write-Host "    - $($_.CimClass.CimClassName): 启用=$($_.Enabled)" -ForegroundColor Gray
        if ($_.Repetition) {
            Write-Host "      间隔: $($_.Repetition.Interval)" -ForegroundColor Gray
        }
    }

    Write-Host "`n  正式任务触发器:" -ForegroundColor Gray
    $prodTask.Triggers | ForEach-Object {
        Write-Host "    - $($_.CimClass.CimClassName): 启用=$($_.Enabled)" -ForegroundColor Gray
        if ($_.Repetition) {
            Write-Host "      间隔: $($_.Repetition.Interval)" -ForegroundColor Gray
        }
    }
}

Write-Host "`n========== 分析 ==========" -ForegroundColor Cyan
Write-Host "`n如果简单测试任务能自动执行而正式任务不能:" -ForegroundColor Yellow
Write-Host "  可能原因1: XML 格式问题（Windows Server 2012 R2 对 XML 要求严格）" -ForegroundColor White
Write-Host "  可能原因2: 参数中有未展开的变量" -ForegroundColor White
Write-Host "  可能原因3: 工作目录设置问题" -ForegroundColor White
Write-Host "`n接下来运行: .\diagnose_step5_check_system_account.ps1" -ForegroundColor Yellow
