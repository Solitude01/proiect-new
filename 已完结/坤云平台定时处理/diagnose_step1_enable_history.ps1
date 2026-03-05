# ====================================================================
# 步骤1: 启用任务历史记录
# 功能：启用 Task Scheduler 事件日志记录
# ====================================================================

#Requires -RunAsAdministrator

Write-Host "========== 步骤1: 启用任务历史记录 ==========" -ForegroundColor Cyan

# 启用任务历史记录
Write-Host "`n正在启用任务历史记录..." -ForegroundColor Yellow

$result = wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [成功] 任务历史记录已启用" -ForegroundColor Green
} else {
    Write-Host "  [错误] 启用失败: $result" -ForegroundColor Red
}

# 验证状态
Write-Host "`n验证状态:" -ForegroundColor Yellow
$status = wevtutil gl Microsoft-Windows-TaskScheduler/Operational 2>&1
$enabled = $status | Select-String "enabled"
Write-Host "  $enabled" -ForegroundColor Gray

Write-Host "`n========== 完成 ==========" -ForegroundColor Cyan
Write-Host "任务历史记录现在已启用。" -ForegroundColor Green
Write-Host "接下来请运行: .\diagnose_step2_simple_test.ps1" -ForegroundColor Yellow
