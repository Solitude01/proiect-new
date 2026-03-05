# Windows Server 桌面工具开发踩坑记录

> 基于「坤云平台定时清理 GUI 管理工具」开发经验整理，Python + tkinter + PyInstaller 技术栈。

---

## 1. 编码问题（最大的坑）

### 问题现象

Python subprocess 调用 PowerShell 脚本，GUI 日志显示全是 `����ģʽ` 乱码。

### 根因

中文 Windows Server 的控制台默认编码是 **GBK (cp936)**，不是 UTF-8。即使在 PowerShell 里设置了 `[Console]::OutputEncoding = UTF8`，在 `CREATE_NO_WINDOW` 无窗口模式下也**不生效**，输出仍然是 GBK。

### 踩过的弯路

| 尝试 | 结果 |
|------|------|
| `subprocess.Popen(encoding="utf-8")` | 乱码，GBK 字节按 UTF-8 解码失败 |
| `-Command` 前缀设置 `[Console]::OutputEncoding = UTF8` | 无窗口模式下无效，仍乱码 |
| `chcp 65001` | 这是 cmd 命令，PowerShell 里不适用 |

### 最终方案：读字节 + 自动检测

```python
def _decode_line(raw_line):
    """优先 UTF-8，失败回退 GBK"""
    try:
        return raw_line.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        pass
    try:
        return raw_line.decode("gbk")
    except (UnicodeDecodeError, AttributeError):
        pass
    return raw_line.decode("utf-8", errors="replace")

# subprocess 不指定 encoding，读原始字节
proc = subprocess.Popen(
    args,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    # 注意：不传 encoding 参数
    creationflags=subprocess.CREATE_NO_WINDOW,
)
for raw_line in proc.stdout:
    line = _decode_line(raw_line).rstrip("\n\r")
```

### 另外：config.json 的 BOM 问题

Windows 上很多编辑器（记事本、VS）保存 UTF-8 文件会带 BOM 头（`EF BB BF`），Python 的 `json.load` 用 `encoding="utf-8"` 会报错：

```
json.decoder.JSONDecodeError: Unexpected UTF-8 BOM
```

**解决：** 读 JSON 统一用 `encoding="utf-8-sig"`，自动处理有无 BOM 两种情况。

---

## 2. subprocess 调用 PowerShell

### `-File` vs `-Command`

| 方式 | 特点 |
|------|------|
| `-File script.ps1` | `$PSScriptRoot` 正确，但路径含中文时编码易出问题 |
| `-Command '& "script.ps1"'` | 更灵活，但 `$PSScriptRoot` 为空 |

普通 subprocess 调用推荐 `-Command`，路径传递更可靠：

```python
args = [
    "powershell.exe",
    "-ExecutionPolicy", "Bypass",
    "-NoProfile",
    "-Command",
    f'& "{script_path}" -ConfigPath "{config_path}"',
]
```

### 计划任务也必须用 `-Command`（大坑）

SYSTEM 账户 + `-File` + 中文路径会导致**脚本静默不执行**：PowerShell 进程启动并退出码 0，但脚本根本没跑，不报错、不写日志。任务计划程序显示"上次结果: 0 (成功)"，但实际什么都没做。

**原因：** SYSTEM 账户没有用户 profile，其代码页/编码环境与普通用户不同，`-File` 参数中的中文路径经过 Task Scheduler → powershell.exe 命令行传递时编码损坏。

**解决：** 计划任务的 Action 也改用 `-Command` 模式：

```powershell
# 错误（SYSTEM + 中文路径 = 静默失败）
$arg = '-File "D:\坤云定时删除任务\cleanup.ps1" -ConfigPath "D:\坤云定时删除任务\config.json"'

# 正确
$arg = "-Command `"& 'D:\坤云定时删除任务\cleanup.ps1' -ConfigPath 'D:\坤云定时删除任务\config.json'`""
```

### `-Command` 模式下 `$PSScriptRoot` 为空（大坑）

用 `-Command` 调用脚本时，脚本内部的 `$PSScriptRoot` 是**空字符串**。如果脚本的默认参数依赖 `$PSScriptRoot`：

```powershell
param(
    [string]$ScriptPath = "$PSScriptRoot\cleanup.ps1"  # -Command 下变成 "\cleanup.ps1"
)
```

**解决：** 调用时显式传入所有路径参数，不依赖 `$PSScriptRoot` 默认值。

### 隐藏窗口

```python
creationflags=subprocess.CREATE_NO_WINDOW
```

不加这个，每次执行 PowerShell 都会闪一个黑色窗口。

### 返回码

PowerShell 脚本失败时返回码可能是很大的数字（如 `4294770688` = `0xFFFF0000`），不要只判断 `== 0`。

### stderr 合并

`run_ps_command` 要用 `stderr=subprocess.STDOUT` 合并错误输出，否则 PowerShell 的报错信息会丢失，调试时看到空的错误提示：

```python
result = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", cmd],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,  # 不要用 capture_output=True
    creationflags=subprocess.CREATE_NO_WINDOW,
)
```

---

## 3. UAC 提权 + 中文路径（第二大坑）

### 问题现象

`ShellExecuteW("runas")` 提权运行 PowerShell 脚本，中文路径无论用 `-File` 还是 `-Command` 都会编码损坏，脚本找不到文件、静默失败。

### 踩过的弯路

| 尝试 | 结果 |
|------|------|
| `-File "D:\中文路径\install.ps1"` | 路径乱码，脚本找不到 |
| `-Command "& 'D:\中文路径\install.ps1'"` | 同样乱码 |
| `-Command` + 显式传所有路径参数 | 路径还是乱码，参数全部损坏 |

根本原因：中文路径经过 `ShellExecuteW → UAC Consent.exe → powershell.exe` 的命令行传递链路，编码会被破坏。

### 最终方案：临时包装脚本

将命令写入 Temp 目录的临时 `.ps1` 文件，中文路径只出现在文件内容中，不经过命令行：

```python
import tempfile, ctypes, threading, os

def _run_elevated_script(ps_code, visible=True):
    # 1. 写临时 .ps1 到 Temp 目录（ASCII 路径）
    fd, wrapper = tempfile.mkstemp(suffix=".ps1", prefix="task_")
    with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
        f.write(ps_code)

    # 2. 用 -File 执行临时文件（路径纯 ASCII，不会乱码）
    params = f'-ExecutionPolicy Bypass -NoProfile -File "{wrapper}"'
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "powershell.exe", params,
        None, 1 if visible else 0
    )
    ok = ret > 32

    # 3. 延迟清理临时文件
    def cleanup():
        import time; time.sleep(60)
        try: os.remove(wrapper)
        except: pass
    threading.Thread(target=cleanup, daemon=True).start()
    return ok
```

调用示例：

```python
ps_code = (
    f'& "{install_script}" '
    f'-ScriptPath "{cleanup_script}" '
    f'-ConfigPath "{config_path}" '
    f'-IntervalHours {interval}\n'
    f'Read-Host "按回车键关闭此窗口"\n'
)
_run_elevated_script(ps_code)
```

**关键点：**
- 临时文件路径如 `C:\Users\ADMINI~1\AppData\Local\Temp\task_xxx.ps1`（纯 ASCII）
- 文件内容用 **UTF-8-BOM** 编码，PowerShell 正确读取中文路径
- 末尾加 `Read-Host` 防止窗口一闪而过，出错时能看到错误信息
- GUI 本身不需要管理员权限，仅在需要时按需 UAC 提权

---

## 4. tkinter 实时日志显示

### 核心模式：Thread + Queue + after 轮询

GUI 线程不能阻塞，所以 subprocess 必须在子线程运行，通过 Queue 传递数据：

```
子线程: subprocess 逐行读取 → queue.put(line)
主线程: root.after(100ms) → queue.get_nowait() → Text.insert()
```

### 关键细节

- `Text` 控件必须 `state=DISABLED` 防止用户编辑，插入前临时改为 `NORMAL`
- 插入后调用 `text.see(tk.END)` 自动滚动到底部
- 用 `None` 作为 sentinel 值标记子线程结束

---

## 5. PyInstaller 打包

### 路径解析

打包后 `__file__` 指向临时解压目录 `_MEIPASS`，不是 exe 所在目录：

```python
def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # exe 所在目录
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

### `--add-data` 的坑

`--add-data "config.json;."` 会把文件打包进 exe 内部（解压到 `_MEIPASS`），但如果这些文件需要用户编辑或被外部程序读取（如 PowerShell 脚本），应该放在 exe 旁边，代码里用 `sys.executable` 定位，而不是从 `_MEIPASS` 读。

### 在干净虚拟环境中打包

避免把开发环境的多余依赖打进去，减小体积：

```bat
python -m venv .build_venv
.build_venv\Scripts\pip install pyinstaller
.build_venv\Scripts\pyinstaller --onefile --windowed gui/main.py
rmdir /s /q .build_venv
```

### 代理导致 pip 失败

如果开发机开了代理，venv 里的 pip 可能继承代理设置导致 `Failed to parse` 错误。解决：

```bash
# bash 环境
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
pip install pyinstaller

# 或 cmd
set HTTP_PROXY=
set HTTPS_PROXY=
pip install pyinstaller
```

---

## 6. Windows Server 兼容性

### ScheduledTask API 差异（大坑）

不同 Windows Server 版本的 `ScheduledTasks` PowerShell 模块存在严重差异：

**问题1：触发器属性不支持**
```powershell
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT2M"  # Windows Server 2012 R2 报错：找不到属性 "Delay"
```

**问题2：-Once 重复触发器静默失效（最严重的坑）**
```powershell
# 在旧版 Windows Server 上，这行不报错，但触发器实际无效！
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Days 9999)
```
表现为：任务注册"成功"、状态显示 Ready、上次结果 0（成功），但**一晚上一次都没自动执行**，没有任何清理日志生成。因为 `-RepetitionDuration (New-TimeSpan -Days 9999)` 在旧版上可能生成无效配置，触发器被静默忽略。

**最终方案：** 用 **XML 注册任务**，绕过 PowerShell cmdlet 的版本差异。XML 是 Task Scheduler 2.0 的原生格式，所有 Windows Server 版本行为一致：

```powershell
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT2M</Delay>
    </BootTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT2H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  ...
</Task>
"@
Register-ScheduledTask -Xml $taskXml -TaskName $TaskName -User "SYSTEM" -Force
```

**关键点：**
- `<Repetition>` 不设 `<Duration>` = 无限期重复（等效于 indefinitely）
- `<StartBoundary>` 设过去的固定日期，确保触发器立即生效
- `<StopAtDurationEnd>false</StopAtDurationEnd>` 确保不会自动停止
- 不再依赖 `New-ScheduledTaskTrigger` 的参数兼容性

### 需要管理员权限的操作

| 操作 | 是否需要管理员 |
|------|:---:|
| `Get-ScheduledTask` 查询状态 | 否 |
| `Start-ScheduledTask` 触发 | 是 |
| `Stop-ScheduledTask` 停止 | 是 |
| `Register-ScheduledTask` 安装 | 是 |
| `Unregister-ScheduledTask` 卸载 | 是 |

不要让整个 GUI 以管理员运行，否则拖拽文件等功能会受 UIPI 限制。

---

## 7. 项目结构建议

```
项目根目录/
├── 核心脚本 (.ps1/.bat)      # 实际业务逻辑
├── config.json               # 外部可编辑配置
├── gui/
│   ├── main.py               # 入口 + 主窗口
│   ├── tab_xxx.py            # 每个功能一个标签页模块
│   ├── utils.py              # subprocess、配置读写、路径
│   └── widgets.py            # 复用组件
└── build.bat                 # 一键打包
```

**核心原则：** GUI 只做展示和调度，通过 subprocess 调用现有脚本，不重复实现业务逻辑。这样脚本可以独立在命令行跑，GUI 只是加了一层壳。

---

## 速查清单

开发 Windows Server 桌面工具前过一遍：

- [ ] subprocess 读输出用**原始字节 + 自动解码**（UTF-8 → GBK fallback）
- [ ] 读 JSON 文件用 `utf-8-sig` 编码
- [ ] subprocess 普通调用用 `-Command`，显式传入所有路径参数
- [ ] subprocess 加 `CREATE_NO_WINDOW` 避免弹窗
- [ ] subprocess 用 `stderr=STDOUT` 合并错误输出，别丢了报错信息
- [ ] UAC 提权通过**临时包装脚本**传递中文路径，不要直接写在命令行参数里
- [ ] UAC 提权窗口末尾加 `Read-Host`，出错时能看到信息不会一闪而过
- [ ] `-Command` 模式下 `$PSScriptRoot` 为空，必须显式传路径
- [ ] PyInstaller 路径用 `sys.executable` 而非 `__file__`
- [ ] 需要用户编辑的文件放 exe 旁边，不要打包进 exe
- [ ] 在干净 venv 中打包
- [ ] 不要整体提权，仅在需要时按需 UAC 提权
- [ ] 长任务放子线程，Queue + after 轮询更新 GUI
- [ ] **ScheduledTask 用 XML 注册**，不要用 `New-ScheduledTaskTrigger` 的重复参数（旧版 Server 静默失效）
