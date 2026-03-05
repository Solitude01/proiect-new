# ====================================================================
# 清理所有测试任务和文件
# 功能：清理诊断过程中创建的所有临时任务和文件
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 清理所有测试任务和文件 ==========" -ForegroundColor Cyan

# 要清理的任务名称模式
$taskPatterns = @(
    "KY_Simple_Test",
    "KY_System_Test",
    "KY_Diag_*",
    "KY_Test_*",
    "坤云平台定时清理_Boot"
)

# 要清理的文件和目录
$pathsToClean = @(
    "C:\ky_test_simple",
    "C:\ky_test_results",
    "C:\ky_test_launcher.ps1",
    "C:\ky_test_launcher2.ps1",
    "C:\ky_cleanup_launcher.ps1",
    "C:\ky_cleanup_error.log",
    "C:\ky_system_test_output.txt",
    "C:\test_task_marker.txt",
    "C:\test_system.ps1",
    "C:\ky_task_export.xml",
    "C:\ky_prod_task_export.txt",
    "C:\task_config_*.xml",
    "C:\task_info_*.txt"
)

Write-Host "`n[1] 清理测试任务..." -ForegroundColor Yellow

foreach ($pattern in $taskPatterns) {
    $tasks = Get-ScheduledTask -TaskName $pattern -ErrorAction SilentlyContinue
    if ($tasks) {
        foreach ($task in $tasks) {
            try {
                Unregister-ScheduledTask -TaskName $task.TaskName -Confirm:$false -ErrorAction Stop
                Write-Host "  [成功] 已删除任务: $($task.TaskName)" -ForegroundColor Green
            }
            catch {
                Write-Host "  [错误] 删除失败: $($task.TaskName) - $_" -ForegroundColor Red
            }
        }
    }
}

Write-Host "`n[2] 清理临时文件和目录..." -ForegroundColor Yellow

foreach ($path in $pathsToClean) {
    try {
        # 处理通配符
        if ($path -match '\*') {
            $items = Get-Item $path -ErrorAction SilentlyContinue
            if ($items) {
                $items | Remove-Item -Force -Recurse -ErrorAction Stop
                Write-Host "  [成功] 已清理: $path" -ForegroundColor Green
            }
        }
        # 处理文件
        elseif (Test-Path $path -PathType Leaf) {
            Remove-Item $path -Force -ErrorAction Stop
            Write-Host "  [成功] 已删除文件: $path" -ForegroundColor Green
        }
        # 处理目录
        elseif (Test-Path $path -PathType Container) {
            Remove-Item $path -Force -Recurse -ErrorAction Stop
            Write-Host "  [成功] 已删除目录: $path" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "  [警告] 清理失败: $path - $_" -ForegroundColor Yellow
    }
}

Write-Host "`n[3] 保留的正式任务:" -ForegroundColor Yellow
$mainTask = Get-ScheduledTask -TaskName "坤云平台定时清理" -ErrorAction SilentlyContinue
if ($mainTask) {
    $info = $mainTask | Get-ScheduledTaskInfo
    Write-Host "  任务: 坤云平台定时清理" -ForegroundColor Green
    Write-Host "  状态: $($mainTask.State)" -ForegroundColor Gray
    Write-Host "  下次运行: $($info.NextRunTime)" -ForegroundColor Gray
}
else {
    Write-Host "  未发现正式任务" -ForegroundColor Yellow
}

Write-Host "`n========== 清理完成 ==========" -ForegroundColor Cyan
Write-Host "所有测试任务和临时文件已清理。" -ForegroundColor Green
