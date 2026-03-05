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
    [int]$IntervalMinutes = 0,  # 如果设置此参数，优先使用分钟（用于快速测试）
    [switch]$Uninstall
)

# 不设置 $ErrorActionPreference = "Stop"
# 原因：Windows Server 2012 R2 的 PowerShell 5.x 会把 schtasks.exe 的 stderr
# 当成终止错误抛出，即使用了 2>&1 重定向也拦不住
# 改为手动检查每步操作的返回值

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
        # 2>&1 合并 stderr 到 stdout，避免 $ErrorActionPreference=Stop 把 schtasks 的 stderr 当终止错误
        $null = schtasks.exe /query /tn $TaskName 2>&1
        if ($LASTEXITCODE -eq 0) {
            $null = schtasks.exe /delete /tn $TaskName /f 2>&1
            Write-Success "任务已成功卸载: $TaskName"
        }
        else {
            Write-Warning "任务不存在: $TaskName"
        }

        # 清理启动脚本
        $launcherPath = "C:\ky_cleanup_launcher.ps1"
        if (Test-Path $launcherPath) {
            Remove-Item -Path $launcherPath -Force -ErrorAction SilentlyContinue
            Write-Success "启动脚本已清理: $launcherPath"
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
    $null = schtasks.exe /query /tn $TaskName 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Warning "任务已存在，将删除旧任务"
        $null = schtasks.exe /delete /tn $TaskName /f 2>&1
        Write-Success "旧任务已删除"
    }

    Write-Info "------------------------------------------"
    Write-Info "任务配置:"
    Write-Info "  任务名称: $TaskName"
    Write-Info "  执行间隔: $intervalDisplay"
    Write-Info "  脚本路径: $ScriptPath"
    Write-Info "  配置文件: $ConfigPath"
    Write-Info "------------------------------------------"

    # 构建启动脚本：写到 ASCII 路径，中文路径只在文件内容中（UTF-8-BOM）
    $launcherPath = "C:\ky_cleanup_launcher.ps1"

    # 踩坑记录: SYSTEM 账户 + -File + 中文路径 = 静默失败
    # 虽然 launcherPath 是 ASCII 路径，但为了保险起见，我们将所有参数都写死在 launcher 中
    # 避免任何通过命令行传递中文参数的情况
    $launcherContent = @"
# KunYun Cleanup Launcher Script (Auto-generated)
# This script avoids Chinese path issues by hardcoding all paths
`$ErrorActionPreference = "Stop"

# Execute cleanup script with config
try {
    & '$ScriptPath' -ConfigPath '$ConfigPath'
} catch {
    `$msg = "ERROR: `$_"
    Add-Content -Path "C:\ky_cleanup_error.log" -Value "`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - `$msg"
    throw
}
"@
    Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8 -Force
    Write-Success "启动脚本已生成: $launcherPath"

    # 使用 XML 注册任务（最可靠的方式，跨 Windows Server 版本兼容）
    # 踩坑记录: New-ScheduledTaskTrigger 的 -Repetition 参数在旧版 Server 上会静默失效
    # XML 是 Task Scheduler 2.0 原生格式，所有版本行为一致

    # 如果指定了 IntervalMinutes 参数，优先使用（用于快速测试）
    if ($IntervalMinutes -gt 0) {
        $intervalMinutes = $IntervalMinutes
        $intervalDisplay = "$IntervalMinutes 分钟"
        $intervalDesc = "每 $IntervalMinutes 分钟"
    }
    else {
        $intervalMinutes = $IntervalHours * 60
        $intervalDisplay = "$IntervalHours 小时"
        $intervalDesc = "每 $IntervalHours 小时"
    }

    Write-Info "正在注册计划任务..."
    Write-Info "执行间隔: $intervalDisplay"

    # 生成任务 XML（包含开机启动触发器 + 定时重复触发器）
    # 使用 schtasks.exe /xml 方式注册，兼容性最好
    # 修复：使用 -File 模式代替 -Command 模式，避免 &amp; XML实体解码问题
    $startBoundary = (Get-Date -Format "yyyy-MM-dd") + "T00:00:00"
    $taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>坤云平台定时清理任务 - $intervalDesc 执行一次</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT2M</Delay>
    </BootTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT${intervalMinutes}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -NoProfile -Command "&amp; '$launcherPath'"</Arguments>
      <WorkingDirectory>C:\</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

    # 将 XML 写入临时文件（避免命令行编码问题）
    $xmlPath = "C:\ky_cleanup_task.xml"
    Set-Content -Path $xmlPath -Value $taskXml -Encoding Unicode -Force

    # 使用 schtasks.exe 导入 XML 创建任务
    $result = schtasks.exe /create /tn $TaskName /xml $xmlPath /f 2>&1
    Remove-Item -Path $xmlPath -Force -ErrorAction SilentlyContinue

    if ($LASTEXITCODE -ne 0) {
        Write-Error "任务注册失败: $result"
        exit 1
    }
    Write-Success "定时触发器已创建: $intervalDisplay"
    Write-Success "已添加开机启动触发器（延迟2分钟执行）"

    # 安装后验证
    $null = schtasks.exe /query /tn $TaskName 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "安装后验证失败：任务不存在"
        exit 1
    }
    Write-Success "安装后验证通过：任务已注册"

    # 显示任务详情
    Write-Info ""
    Write-Info "注册的任务详情:"
    $taskInfo = schtasks.exe /query /tn $TaskName /v /fo list 2>&1
    $taskInfo | ForEach-Object { Write-Info "  $_" }

    Write-Success "=========================================="
    Write-Success "任务安装成功！"
    Write-Success "=========================================="
    Write-Info ""
    Write-Info "任务详情:"
    Write-Info "  • 任务名称: $TaskName"
    Write-Info "  • 执行频率: $intervalDisplay"
    Write-Info "  • 运行账户: SYSTEM"
    Write-Info "  • 启动脚本: $launcherPath"
    Write-Info ""

    # 询问是否立即运行
    $response = Read-Host "是否立即运行一次任务测试？(Y/N)"
    if ($response -eq 'Y' -or $response -eq 'y') {
        Write-Info "正在启动任务..."
        $null = schtasks.exe /run /tn $TaskName 2>&1
        Write-Success "任务已启动"
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
