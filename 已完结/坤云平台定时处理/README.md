# 坤云平台定时清理系统

> 自动清理坤云平台的图片、视频和日志文件，防止磁盘空间被占满。
> 
> **适用于：Windows Server 2012 R2 / PowerShell 4.0**

---

## ⚠️ 重要说明

**当前服务器环境存在严重兼容性问题**（Windows Server 2012 R2 + PowerShell 4.0）：
- 所有 PowerShell 脚本创建定时任务的方式都会失败
- `schtasks.exe` 命令行工具存在引号/路径解析 Bug
- 唯一可靠方式：**使用 CMD 批处理创建任务**

---

## 🚀 快速开始（已配置完成）

当前任务状态：
- **任务名称**: `KY`
- **执行频率**: 每 2 小时
- **执行命令**: `D:\dist\run_ky.cmd`
- **运行账户**: SYSTEM
- **日志目录**: `D:\dist\logs`

### 检查任务状态
```powershell
Get-ScheduledTask -TaskName "KY" | Get-ScheduledTaskInfo
```

### 查看最近日志
```powershell
Get-ChildItem "D:\dist\logs\cleanup_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 20
```

### 手动触发任务
```powershell
Start-ScheduledTask -TaskName "KY"
```

---

## 📋 如果任务需要重建

在服务器上执行以下 CMD 命令：

```cmd
schtasks.exe /delete /tn "KY" /f
schtasks.exe /create /tn "KY" /tr "D:\dist\run_ky.cmd" /sc hourly /mo 2 /ru SYSTEM /f
```

---

## 🔧 配置文件

`config.json`：
```json
{
  "cleanupTasks": [
    {
      "name": "图片清理任务",
      "enabled": true,
      "path": "G:\\NewWeb\\monitorUpload",
      "fileExtensions": [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"],
      "cleanupMode": "bySize",
      "maxSizeGB": 700.0
    }
  ],
  "settings": {
    "logDir": "D:\\dist\\logs",
    "logRetentionDays": 30,
    "dryRun": false
  }
}
```

---

## 🐛 已知问题与踩坑记录

### 1. Windows Server 2012 R2 兼容性问题

**问题现象**：
- PowerShell 脚本创建任务失败
- `schtasks.exe` 报错："文件名、目录名或卷标语法不正确"
- 中文任务名称导致编码错误

**根本原因**：
- Windows Server 2012 R2 的 PowerShell 4.0 存在严重兼容性差异
- `schtasks.exe` 命令解析器对引号和中文支持不佳
- SYSTEM 账户在某些情况下权限受限

**解决方案**：
- 使用 **CMD 批处理** 创建任务（而非 PowerShell）
- 使用 **英文任务名称**（如 `KY` 而非中文）
- 使用 **CMD 包装器** 调用 PowerShell 脚本

### 2. 清理模式

- `bySize`: 目录超过指定大小时，从最早的文件开始删除
- `byDays`: 删除超过指定天数的文件（未配置）

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `cleanup.ps1` | 主清理脚本 |
| `config.json` | 清理配置 |
| `run_ky.cmd` | CMD 包装器（任务实际执行的文件）|
| `logs/` | 日志目录 |
| `坤云清理管理工具.exe` | GUI 管理工具（可选）|

---

## ✅ 验证任务正常

1. 检查任务存在：
   ```powershell
   Get-ScheduledTask -TaskName "KY"
   ```

2. 检查下次运行时间：
   ```powershell
   (Get-ScheduledTask -TaskName "KY" | Get-ScheduledTaskInfo).NextRunTime
   ```

3. 检查最近执行结果：
   ```powershell
   (Get-ScheduledTask -TaskName "KY" | Get-ScheduledTaskInfo).LastTaskResult
   # 0 = 成功，非0 = 失败
   ```

4. 查看清理效果：
   ```powershell
   # 查看最新日志
   Get-Content (Get-ChildItem "D:\dist\logs\cleanup_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 10
   ```

---

## 📝 历史记录

- **2026-03-07**: 修复定时任务创建问题，从 PowerShell 方式改为 CMD 方式
- **配置**: 每2小时清理一次，保持 G:\NewWeb\monitorUpload 不超过 700GB

---

**维护人员**: 张旭阳
