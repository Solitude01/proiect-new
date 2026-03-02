# 坤云平台定时清理系统

自动清理坤云平台的图片、视频和日志文件，防止磁盘空间被占满。

## 运维速查

> 以下命令在服务器上以管理员 PowerShell 执行。

**查看定时任务是否正常**

```powershell
Get-ScheduledTask -TaskName "坤云平台定时清理" | Format-Table TaskName, State
```

输出 `State` 为 **Ready** 表示任务已注册且处于正常待触发状态。

**查看上次运行时间和结果**

```powershell
Get-ScheduledTask -TaskName "坤云平台定时清理" | Get-ScheduledTaskInfo
```

关注 `LastRunTime`（上次执行时间）和 `LastTaskResult`（`0` 表示成功）。

**查看最新一条运行日志**

```powershell
Get-ChildItem "C:\坤云平台定时处理\logs\cleanup_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

**手动触发一次执行**

```powershell
Start-ScheduledTask -TaskName "坤云平台定时清理"
```

## 当前配置概览

| 任务名 | 路径 | 模式 | 阈值 | 文件类型 |
|--------|------|------|------|----------|
| 图片清理 | `F:\坤云\webLocal\monitorUpload` | bySize | 166 GB | .jpg .jpeg .png .bmp .gif |
| 视频清理 | `D:\home\ruoyi\uploadPath\video` | bySize | 80 GB | .mp4 .avi .mov .mkv .flv |
| AI项目视频清理 | `D:\home\ruoyi\uploadPath\aiProject` | bySize | 80 GB | .mp4 .avi .mov .mkv .flv |
| 日志清理-E盘 | `E:\home\client\logs` | byDays | 60 天 | .log .txt |
| 日志清理-C盘 | `C:\home\client\logs` | byDays | 60 天 | .log .txt |

- 定时触发：每 **2 小时**执行一次，开机延迟 2 分钟也会触发
- 运行账户：SYSTEM
- 日志目录：`C:\坤云平台定时处理\logs`（保留 30 天）
- 模拟模式：`dryRun` 当前为 `false`（实际删除）

## 文件结构

```
坤云平台定时处理/
├── config.json      # 配置文件（清理任务、阈值、开关）
├── cleanup.ps1      # 主清理脚本
├── install.ps1      # 安装/卸载定时任务
└── README.md        # 本文档
```

## 快速开始

### 1. 配置清理规则

编辑 `config.json`，在 `cleanupTasks` 数组中添加或修改任务。

### 2. 测试运行

将 `config.json` 中 `settings.dryRun` 设为 `true`，然后执行：

```powershell
.\cleanup.ps1
```

查看控制台输出和日志，确认预期删除的文件列表无误后，再将 `dryRun` 改回 `false`。

### 3. 安装定时任务

```powershell
# 以管理员身份运行
.\install.ps1
```

## 配置说明

### 清理模式

| cleanupMode | 说明 | 必需参数 |
|-------------|------|----------|
| `byDays` | 删除超过指定天数的文件 | `retentionDays` |
| `bySize` | 目录超过指定大小时，从最早的文件开始删除 | `maxSizeGB` |

### 清理任务字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 任务名称，用于日志显示 |
| `enabled` | bool | 是否启用 |
| `path` | string | 要清理的目录路径 |
| `fileExtensions` | array | 文件扩展名列表 |
| `cleanupMode` | string | `byDays` 或 `bySize` |
| `retentionDays` | int | 保留天数（byDays 模式） |
| `maxSizeGB` | number | 最大目录大小 GB（bySize 模式） |

### 系统设置

| 字段 | 类型 | 说明 |
|------|------|------|
| `logDir` | string | 日志目录 |
| `logRetentionDays` | int | 日志保留天数 |
| `dryRun` | bool | `true` 时只模拟，不实际删除 |

## 任务管理

```powershell
# 停止正在运行的任务
Stop-ScheduledTask -TaskName "坤云平台定时清理"

# 卸载定时任务
.\install.ps1 -Uninstall
```

## 故障排查

### 任务未执行

```powershell
# 查看任务详情
Get-ScheduledTask -TaskName "坤云平台定时清理" | Get-ScheduledTaskInfo
# 手动测试脚本
.\cleanup.ps1
```

### 文件未被删除

检查：
- `dryRun` 是否仍为 `true`
- 文件是否被其他进程占用
- 路径和文件扩展名是否匹配
- 运行账户是否有删除权限

## 注意事项

1. **首次使用**先设 `dryRun: true` 测试，确认无误再改为 `false`
2. **路径格式**：JSON 中 Windows 路径用双反斜杠 `\\`
3. **权限**：安装脚本和清理脚本都需要管理员权限
4. **删除不可恢复**：请确保重要数据已备份
