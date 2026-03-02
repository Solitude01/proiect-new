# ====================================================================
# 坤云平台定时清理任务安装脚本
# 功能：自动创建Windows任务计划程序任务
# ====================================================================

# 需要管理员权限
#Requires -RunAsAdministrator

param(
    [string]$TaskName = "坤云平台定时清理",
    [string]$ScriptPath = "$PSScriptRoot\cleanup.ps1",
    [string]$ConfigPath = "$PSScriptRoot\config.json",
    [int]$IntervalHours = 2,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# ====================================================================
# 输出函数
# ====================================================================
function Write-Info {
    param([string]$Message)
    Write-Host "[信息] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[成功] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "[错误] $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[警告] $Message" -ForegroundColor Yellow
}

# ====================================================================
# 卸载任务
# ====================================================================
function Uninstall-Task {
    Write-Info "开始卸载任务..."

    try {
        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

        if ($existingTask) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Success "任务已成功卸载: $TaskName"
        }
        else {
            Write-Warning "任务不存在: $TaskName"
        }
    }
    catch {
        Write-Error "卸载任务失败: $_"
        exit 1
    }
}

# ====================================================================
# 安装任务
# ====================================================================
function Install-Task {
    Write-Info "=========================================="
    Write-Info "坤云平台定时清理任务安装程序"
    Write-Info "=========================================="

    # 检查脚本文件
    if (-not (Test-Path $ScriptPath)) {
        Write-Error "清理脚本不存在: $ScriptPath"
        exit 1
    }
    Write-Success "清理脚本: $ScriptPath"

    # 检查配置文件
    if (-not (Test-Path $ConfigPath)) {
        Write-Error "配置文件不存在: $ConfigPath"
        exit 1
    }
    Write-Success "配置文件: $ConfigPath"

    # 删除已存在的任务
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Warning "任务已存在，将删除旧任务"
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Success "旧任务已删除"
    }

    Write-Info "------------------------------------------"
    Write-Info "任务配置:"
    Write-Info "  任务名称: $TaskName"
    Write-Info "  执行间隔: 每 $IntervalHours 小时"
    Write-Info "  脚本路径: $ScriptPath"
    Write-Info "  配置文件: $ConfigPath"
    Write-Info "------------------------------------------"

    # 创建任务操作
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$ScriptPath`" -ConfigPath `"$ConfigPath`"" `
        -WorkingDirectory (Split-Path $ScriptPath -Parent)

    # 创建触发器1: 系统启动时（延迟2分钟）
    $trigger1 = New-ScheduledTaskTrigger -AtStartup
    $trigger1.Delay = "PT2M"  # 延迟2分钟

    # 创建触发器2: 每2小时重复执行（无限期）
    $trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) -RepetitionDuration (New-TimeSpan -Days 9999)

    # 创建任务设置
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    # 创建任务主体（使用SYSTEM账户运行）
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    try {
        # 注册任务
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger @($trigger1, $trigger2) `
            -Settings $settings `
            -Principal $principal `
            -Description "坤云平台自动清理图片、视频和日志文件，释放磁盘空间。每${IntervalHours}小时执行一次。" `
            -Force

        Write-Success "=========================================="
        Write-Success "任务安装成功！"
        Write-Success "=========================================="
        Write-Info ""
        Write-Info "任务详情:"
        Write-Info "  • 任务名称: $TaskName"
        Write-Info "  • 执行频率: 每 $IntervalHours 小时"
        Write-Info "  • 开机启动: 是（延迟2分钟）"
        Write-Info "  • 运行账户: SYSTEM"
        Write-Info ""
        Write-Info "管理命令:"
        Write-Info "  • 手动运行: Start-ScheduledTask -TaskName '$TaskName'"
        Write-Info "  • 停止运行: Stop-ScheduledTask -TaskName '$TaskName'"
        Write-Info "  • 查看状态: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
        Write-Info "  • 查看日志: 打开任务计划程序查看历史记录"
        Write-Info "  • 卸载任务: .\install.ps1 -Uninstall"
        Write-Info ""

        # 询问是否立即运行
        $response = Read-Host "是否立即运行一次任务测试？(Y/N)"
        if ($response -eq 'Y' -or $response -eq 'y') {
            Write-Info "正在启动任务..."
            Start-ScheduledTask -TaskName $TaskName
            Write-Success "任务已启动，请查看日志文件了解执行情况"

            # 显示配置文件中的日志路径
            try {
                $config = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $logPath = $config.settings.logFilePath
                Write-Info "日志文件位置: $logPath"
            }
            catch {
                Write-Warning "无法读取日志路径配置"
            }
        }
    }
    catch {
        Write-Error "任务注册失败: $_"
        Write-Error $_.ScriptStackTrace
        exit 1
    }
}

# ====================================================================
# 主流程
# ====================================================================
function Main {
    # 检查管理员权限
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if (-not $isAdmin) {
        Write-Error "此脚本需要管理员权限运行！"
        Write-Info "请右键点击PowerShell，选择'以管理员身份运行'，然后重新执行此脚本"
        exit 1
    }

    if ($Uninstall) {
        Uninstall-Task
    }
    else {
        Install-Task
    }
}

# 执行主函数
Main
