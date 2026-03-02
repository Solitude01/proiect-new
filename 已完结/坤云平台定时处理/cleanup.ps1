# ====================================================================
# 坤云平台定时清理脚本
# 功能：清理图片、视频、日志文件，释放磁盘空间
# 支持两种清理模式：byDays（按天数）、bySize（按目录大小）
# 作者：坤云平台
# 日期：2026-01-13
# ====================================================================

param(
    [string]$ConfigPath = "$PSScriptRoot\config.json"
)

# 设置编码为UTF-8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ====================================================================
# 全局日志文件路径（每次运行生成独立日志）
# ====================================================================
$global:currentLogFile = $null

# ====================================================================
# 初始化日志文件
# ====================================================================
function Initialize-LogFile {
    param([string]$LogDir)

    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }

        # 生成独立日志文件名: cleanup_YYYYMMDD_HHmmss.log
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $global:currentLogFile = Join-Path $LogDir "cleanup_$timestamp.log"

        Write-Host "日志文件: $($global:currentLogFile)" -ForegroundColor Cyan
    }
    catch {
        Write-Host "初始化日志目录失败: $_" -ForegroundColor Red
    }
}

# ====================================================================
# 清理旧日志文件
# ====================================================================
function Clear-OldLogs {
    param(
        [string]$LogDir,
        [int]$RetentionDays
    )

    if ($RetentionDays -le 0) { return }

    try {
        $cutoffDate = (Get-Date).AddDays(-$RetentionDays)
        $oldLogs = Get-ChildItem -Path $LogDir -Filter "cleanup_*.log" -ErrorAction SilentlyContinue |
                   Where-Object { $_.LastWriteTime -lt $cutoffDate }

        foreach ($log in $oldLogs) {
            Remove-Item -Path $log.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "已清理旧日志: $($log.Name)" -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "清理旧日志失败: $_" -ForegroundColor Yellow
    }
}

# ====================================================================
# 日志函数
# ====================================================================
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"

    # 输出到控制台
    switch ($Level) {
        "ERROR" { Write-Host $logMessage -ForegroundColor Red }
        "WARN"  { Write-Host $logMessage -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logMessage -ForegroundColor Green }
        default { Write-Host $logMessage }
    }

    # 写入日志文件
    if ($global:currentLogFile) {
        try {
            Add-Content -Path $global:currentLogFile -Value $logMessage -Encoding UTF8
        }
        catch {
            Write-Host "写入日志文件失败: $_" -ForegroundColor Red
        }
    }
}

# ====================================================================
# 格式化文件大小
# ====================================================================
function Format-FileSize {
    param([long]$Size)

    if ($Size -gt 1TB) { return "{0:N2} TB" -f ($Size / 1TB) }
    if ($Size -gt 1GB) { return "{0:N2} GB" -f ($Size / 1GB) }
    if ($Size -gt 1MB) { return "{0:N2} MB" -f ($Size / 1MB) }
    if ($Size -gt 1KB) { return "{0:N2} KB" -f ($Size / 1KB) }
    return "{0} Bytes" -f $Size
}

# ====================================================================
# 获取目录大小
# ====================================================================
function Get-DirectorySize {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return 0
    }

    try {
        $size = (Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum).Sum
        if ($null -eq $size) { return 0 }
        return [long]$size
    }
    catch {
        Write-Log "获取目录大小失败 [$Path]: $_" "WARN"
        return 0
    }
}

# ====================================================================
# 按天数清理文件
# ====================================================================
function Clear-ByDays {
    param(
        [string]$Path,
        [int]$RetentionDays,
        [array]$FileExtensions
    )

    $cutoffDate = (Get-Date).AddDays(-$RetentionDays)
    Write-Log "清理模式: 按天数 | 删除修改时间早于 $($cutoffDate.ToString('yyyy-MM-dd HH:mm:ss')) 的文件" "INFO"

    $deletedCount = 0
    $freedSpace = 0

    try {
        $files = Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue |
                 Where-Object {
                     $FileExtensions -contains $_.Extension.ToLower() -and
                     $_.LastWriteTime -lt $cutoffDate
                 }

        $fileCount = ($files | Measure-Object).Count
        Write-Log "找到 $fileCount 个需要删除的文件" "INFO"

        foreach ($file in $files) {
            $fileSize = $file.Length
            $fileName = $file.FullName

            if ($global:config.settings.dryRun) {
                Write-Log "[模拟] 将删除: $fileName ($(Format-FileSize $fileSize))" "INFO"
            }
            else {
                try {
                    Remove-Item -Path $fileName -Force -ErrorAction Stop
                    Write-Log "已删除: $fileName ($(Format-FileSize $fileSize))" "SUCCESS"
                }
                catch {
                    Write-Log "删除失败: $fileName - $_" "ERROR"
                    continue
                }
            }

            $deletedCount++
            $freedSpace += $fileSize
        }
    }
    catch {
        Write-Log "按天数清理失败: $_" "ERROR"
    }

    return @{ DeletedCount = $deletedCount; FreedSpace = $freedSpace }
}

# ====================================================================
# 按目录大小清理文件
# ====================================================================
function Clear-BySize {
    param(
        [string]$Path,
        [double]$MaxSizeGB,
        [array]$FileExtensions
    )

    $maxSize = [long]($MaxSizeGB * 1GB)
    $currentSize = Get-DirectorySize -Path $Path

    Write-Log "清理模式: 按大小 | 当前: $(Format-FileSize $currentSize), 阈值: $(Format-FileSize $maxSize)" "INFO"

    $deletedCount = 0
    $freedSpace = 0

    if ($currentSize -le $maxSize) {
        Write-Log "目录大小未超过阈值，无需清理" "INFO"
        return @{ DeletedCount = 0; FreedSpace = 0 }
    }

    Write-Log "目录大小超过阈值，开始清理最早的文件..." "WARN"

    try {
        # 获取所有匹配的文件并按修改时间排序（最早的在前）
        $files = Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue |
                 Where-Object { $FileExtensions -contains $_.Extension.ToLower() } |
                 Sort-Object LastWriteTime

        foreach ($file in $files) {
            if ($currentSize -le $maxSize) {
                Write-Log "已达到目标大小，停止删除" "SUCCESS"
                break
            }

            $fileSize = $file.Length
            $fileName = $file.FullName

            if ($global:config.settings.dryRun) {
                Write-Log "[模拟] 将删除: $fileName ($(Format-FileSize $fileSize))" "INFO"
            }
            else {
                try {
                    Remove-Item -Path $fileName -Force -ErrorAction Stop
                    Write-Log "已删除: $fileName ($(Format-FileSize $fileSize))" "SUCCESS"
                }
                catch {
                    Write-Log "删除失败: $fileName - $_" "ERROR"
                    continue
                }
            }

            $deletedCount++
            $freedSpace += $fileSize
            $currentSize -= $fileSize
        }

        $finalSize = Get-DirectorySize -Path $Path
        Write-Log "最终大小: $(Format-FileSize $finalSize)" "INFO"
    }
    catch {
        Write-Log "按大小清理失败: $_" "ERROR"
    }

    return @{ DeletedCount = $deletedCount; FreedSpace = $freedSpace }
}

# ====================================================================
# 统一清理函数
# ====================================================================
function Clear-Files {
    param($TaskConfig)

    if (-not $TaskConfig.enabled) {
        Write-Log "[$($TaskConfig.name)] 已禁用，跳过" "INFO"
        return @{ DeletedCount = 0; FreedSpace = 0 }
    }

    Write-Log "========== [$($TaskConfig.name)] 开始清理 ==========" "INFO"
    Write-Log "路径: $($TaskConfig.path)" "INFO"
    Write-Log "文件类型: $($TaskConfig.fileExtensions -join ', ')" "INFO"

    $path = $TaskConfig.path
    if (-not (Test-Path $path)) {
        Write-Log "路径不存在，跳过: $path" "WARN"
        return @{ DeletedCount = 0; FreedSpace = 0 }
    }

    $result = @{ DeletedCount = 0; FreedSpace = 0 }

    switch ($TaskConfig.cleanupMode) {
        "byDays" {
            if (-not $TaskConfig.retentionDays) {
                Write-Log "错误: byDays 模式需要配置 retentionDays" "ERROR"
                return $result
            }
            $result = Clear-ByDays -Path $path -RetentionDays $TaskConfig.retentionDays -FileExtensions $TaskConfig.fileExtensions
        }
        "bySize" {
            if (-not $TaskConfig.maxSizeGB) {
                Write-Log "错误: bySize 模式需要配置 maxSizeGB" "ERROR"
                return $result
            }
            $result = Clear-BySize -Path $path -MaxSizeGB $TaskConfig.maxSizeGB -FileExtensions $TaskConfig.fileExtensions
        }
        default {
            Write-Log "错误: 未知的清理模式 '$($TaskConfig.cleanupMode)'，支持: byDays, bySize" "ERROR"
            return $result
        }
    }

    Write-Log "[$($TaskConfig.name)] 完成: 删除 $($result.DeletedCount) 个文件, 释放 $(Format-FileSize $result.FreedSpace)" "SUCCESS"
    return $result
}

# ====================================================================
# 主函数
# ====================================================================
function Main {
    $startTime = Get-Date

    # 检查配置文件
    if (-not (Test-Path $ConfigPath)) {
        Write-Host "配置文件不存在: $ConfigPath" -ForegroundColor Red
        exit 1
    }

    # 读取配置
    try {
        $global:config = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Host "读取配置文件失败: $_" -ForegroundColor Red
        exit 1
    }

    # 初始化日志文件（每次运行生成独立日志）
    Initialize-LogFile -LogDir $global:config.settings.logDir

    # 清理旧日志文件
    Clear-OldLogs -LogDir $global:config.settings.logDir -RetentionDays $global:config.settings.logRetentionDays

    Write-Log "============================================" "INFO"
    Write-Log "坤云平台定时清理任务开始" "INFO"
    Write-Log "执行时间: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" "INFO"
    Write-Log "============================================" "INFO"

    Write-Log "配置文件加载成功: $ConfigPath" "INFO"
    Write-Log "平台: $($global:config.platform)" "INFO"

    if ($global:config.settings.dryRun) {
        Write-Log "========== 模拟运行模式（不会实际删除文件）==========" "WARN"
    }

    # 统计信息
    $totalStats = @{
        DeletedCount = 0
        FreedSpace = 0
    }

    # 遍历所有清理任务
    $taskCount = ($global:config.cleanupTasks | Measure-Object).Count
    Write-Log "共有 $taskCount 个清理任务" "INFO"

    foreach ($task in $global:config.cleanupTasks) {
        try {
            $taskStats = Clear-Files -TaskConfig $task
            $totalStats.DeletedCount += $taskStats.DeletedCount
            $totalStats.FreedSpace += $taskStats.FreedSpace
        }
        catch {
            Write-Log "清理任务出现异常 [$($task.name)]: $_" "ERROR"
        }
    }

    # 输出总结
    $endTime = Get-Date
    $duration = $endTime - $startTime

    Write-Log "============================================" "INFO"
    Write-Log "清理任务完成" "SUCCESS"
    Write-Log "总共删除文件: $($totalStats.DeletedCount) 个" "INFO"
    Write-Log "总共释放空间: $(Format-FileSize $totalStats.FreedSpace)" "INFO"
    Write-Log "执行耗时: $($duration.ToString('hh\:mm\:ss'))" "INFO"
    Write-Log "============================================" "INFO"
}

# 执行主函数
try {
    Main
}
catch {
    Write-Log "程序执行出现严重错误: $_" "ERROR"
    Write-Log $_.ScriptStackTrace "ERROR"
    exit 1
}

